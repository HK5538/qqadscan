"""扫描流程：遍历文件 -> 解码 -> 过滤 -> 评分 -> 汇总。"""

from __future__ import annotations

import logging
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from ..config import Config
from ..paths import relative_path
from ..plugins.loader import PluginManager
from .decoder import decode_line
from .lexicon import Lexicon
from .rules import RuleEngine
from .scorer import KeywordAnalysis, Reason, ScoredCandidate, Scorer
from .textio import SKIP_DIRS, FileTooLarge, read_text_file

LOGGER = logging.getLogger(__name__)

ProgressCallback = Callable[["ProgressEvent"], None]
StopCallback = Callable[[], bool]


@dataclass
class ScanOptions:
    paths: list[Path] = field(default_factory=list)
    recursive: bool | None = None
    extensions: tuple[str, ...] | None = None
    min_score: int = 0
    max_entries: int = 0


@dataclass
class ProgressEvent:
    phase: str
    current_file: str = ""
    files_done: int = 0
    files_total: int = 0
    lines_done: int = 0
    hits: int = 0
    message: str = ""


@dataclass
class ScannedFile:
    path: Path
    display: str
    encoding: str = ""
    size: int = 0
    lines: int = 0
    hits: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class ScanResult:
    entries: list[ScoredCandidate] = field(default_factory=list)
    files: list[ScannedFile] = field(default_factory=list)
    lines_scanned: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    cancelled: bool = False
    errors: list[str] = field(default_factory=list)
    plugin_notes: list[str] = field(default_factory=list)
    plugin_names: list[str] = field(default_factory=list)
    plugin_errors: list[str] = field(default_factory=list)
    lexicon_stats: dict[str, int] = field(default_factory=dict)
    roots: list[str] = field(default_factory=list)
    config_warnings: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        end = self.finished_at or datetime.now()
        return max(0.0, (end - self.started_at).total_seconds())

    @property
    def files_scanned(self) -> int:
        return sum(1 for item in self.files if item.ok)

    @property
    def total_hits(self) -> int:
        return len(self.entries)

    def band_counts(self) -> dict[str, int]:
        counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for entry in self.entries:
            counts[entry.band] = counts.get(entry.band, 0) + 1
        return counts


def collect_files(
    paths: Iterable[Path],
    *,
    extensions: tuple[str, ...] = (".txt",),
    recursive: bool = True,
    skip_hidden: bool = True,
) -> list[Path]:
    """展开文件列表，过滤扩展名与常见无关目录。"""
    result: list[Path] = []
    seen: set[str] = set()
    wanted = tuple(ext.lower() for ext in extensions)

    def add(path: Path) -> None:
        key = str(path.resolve()).lower()
        if key in seen:
            return
        seen.add(key)
        result.append(path)

    for raw in paths:
        path = Path(raw)
        if path.is_file():
            if path.suffix.lower() in wanted or not wanted:
                add(path)
            continue
        if not path.is_dir():
            continue
        if recursive:
            for root, dirs, files in os.walk(path):
                dirs[:] = [
                    d
                    for d in dirs
                    if d.lower() not in SKIP_DIRS and not (skip_hidden and d.startswith("."))
                ]
                for name in files:
                    if skip_hidden and name.startswith("."):
                        continue
                    item = Path(root) / name
                    if item.suffix.lower() in wanted:
                        add(item)
        else:
            for item in sorted(path.iterdir()):
                if item.is_file() and item.suffix.lower() in wanted:
                    if skip_hidden and item.name.startswith("."):
                        continue
                    add(item)
    return result


def _display_path(path: Path, roots: list[Path]) -> str:
    for root in roots:
        base = Path(root)
        # 直接扫描单个文件时，以它所在的目录为基准，只显示文件名
        base = base.parent if base.is_file() else base
        try:
            return str(path.resolve().relative_to(base.resolve()))
        except (ValueError, OSError):
            continue
    return path.name


class Scanner:
    """扫描器。"""

    def __init__(
        self,
        config: Config,
        lexicon: Lexicon,
        plugins: PluginManager | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.lexicon = lexicon
        self.plugins = plugins
        self.logger = logger or LOGGER
        self.scorer = Scorer(config, lexicon)
        self.rules = RuleEngine(config, lexicon)

    # ------------------------------------------------------------------
    def scan(
        self,
        options: ScanOptions,
        progress: ProgressCallback | None = None,
        should_stop: StopCallback | None = None,
    ) -> ScanResult:
        result = ScanResult(roots=[relative_path(p) for p in options.paths])
        result.lexicon_stats = self.lexicon.stats()
        result.config_warnings = list(self.config.warnings)

        extensions = options.extensions or self.config.extensions
        recursive = self.config.recursive if options.recursive is None else options.recursive
        files = collect_files(
            options.paths,
            extensions=extensions,
            recursive=recursive,
            skip_hidden=bool(self.config.get("scan", "skip_hidden", default=True)),
        )

        if self.plugins:
            self.plugins.on_lexicon_ready()
            result.plugin_names = self.plugins.names

        if not files:
            result.finished_at = datetime.now()
            result.errors.append("没有找到可扫描的文件（检查扩展名/目录设置）")
            self._emit(progress, ProgressEvent("done", message="没有找到文件"))
            return result

        self._emit(
            progress,
            ProgressEvent(
                "start", files_total=len(files), message=f"共 {len(files)} 个文件"
            ),
        )

        best: dict[tuple, ScoredCandidate] = {}
        lines_scanned = 0
        hits = 0
        last_report = 0.0

        for index, path in enumerate(files, 1):
            if should_stop and should_stop():
                result.cancelled = True
                break
            display = _display_path(path, options.paths)
            info = ScannedFile(path=path, display=display)
            self._emit(
                progress,
                ProgressEvent(
                    "file",
                    current_file=display,
                    files_done=index - 1,
                    files_total=len(files),
                    lines_done=lines_scanned,
                    hits=hits,
                ),
            )
            try:
                doc = read_text_file(
                    path,
                    max_bytes=self.config.max_file_bytes,
                    encodings=self.config.encodings,
                )
            except FileTooLarge as exc:
                info.error = str(exc)
                result.errors.append(str(exc))
                result.files.append(info)
                continue
            except OSError as exc:
                info.error = f"读取失败：{exc}"
                result.errors.append(f"{display}: 读取失败（{exc}）")
                result.files.append(info)
                continue

            info.encoding = doc.encoding
            info.size = doc.size
            text = doc.text
            file_lines = text.splitlines()
            info.lines = len(file_lines)

            for line_no, line in enumerate(file_lines, 1):
                lines_scanned += 1
                if should_stop and line_no % 500 == 0 and should_stop():
                    result.cancelled = True
                    break
                try:
                    entries = self._scan_line(
                        line,
                        line_no,
                        display,
                        path,
                        info.encoding,
                        best,
                        options.min_score,
                    )
                    hits += entries
                except Exception as exc:  # noqa: BLE001 - 单行失败不影响整体
                    self.logger.exception("扫描第 %s 行失败：%s", line_no, exc)
                    result.errors.append(f"{display}:{line_no} 处理失败（{exc}）")

                now = time.monotonic()
                if progress and (now - last_report > 0.15):
                    last_report = now
                    self._emit(
                        progress,
                        ProgressEvent(
                            "progress",
                            current_file=display,
                            files_done=index - 1,
                            files_total=len(files),
                            lines_done=lines_scanned,
                            hits=len(best),
                        ),
                    )

            result.files.append(info)
            if result.cancelled:
                break

        result.lines_scanned = lines_scanned
        file_hits = Counter(entry.candidate.file for entry in best.values())
        for info in result.files:
            info.hits = file_hits.get(info.display, 0)
        entries = sorted(
            best.values(),
            key=lambda item: (-item.score, item.candidate.file, item.candidate.line_no),
        )
        if options.max_entries and options.max_entries > 0:
            entries = entries[: options.max_entries]
        result.entries = entries
        result.finished_at = datetime.now()
        if self.plugins:
            result.plugin_notes = self.plugins.report_notes
            result.plugin_errors = list(self.plugins.errors)
            self.plugins.teardown()
        self._emit(
            progress,
            ProgressEvent(
                "done",
                files_done=len(files),
                files_total=len(files),
                lines_done=lines_scanned,
                hits=len(entries),
                message=("已取消" if result.cancelled else "扫描完成"),
            ),
        )
        return result

    # ------------------------------------------------------------------
    def _scan_line(
        self,
        line: str,
        line_no: int,
        display: str,
        source_path: Path,
        encoding: str,
        best: dict[tuple, ScoredCandidate],
        min_score: int,
    ) -> int:
        if not line.strip():
            return 0
        text = line
        if self.plugins:
            transformed = self.plugins.before_line(line, display)
            if transformed is None:
                return 0
            text = transformed

        candidates = decode_line(
            text,
            self.lexicon,
            min_digits=self.config.min_digits,
            max_digits=self.config.max_digits,
            max_gap=self.config.max_gap,
            boundaries=self.config.boundary_chars,
            noise_precedence=self.config.noise_precedence,
            place_value=self.config.chinese_place_value,
            line_no=line_no,
            file=display,
        )
        if not candidates:
            return 0
        if self.plugins:
            self.plugins.after_decode(candidates, display)

        added = 0
        for candidate in candidates:
            analysis = self.scorer.analyze(candidate)
            rule_eval = self.rules.evaluate(
                candidate, has_group_evidence=analysis.has_group_evidence
            )
            if rule_eval.skipped:
                continue

            extra: list[Reason] = []
            if self.plugins:
                for delta in self.plugins.adjust_score(candidate, analysis):
                    if abs(delta.delta) < 0.01:
                        continue
                    extra.append(Reason(delta.label, delta.delta, delta.detail))

            score = self.scorer.score(candidate, analysis, rule_eval, extra)
            if score.score < min_score:
                continue

            entry = ScoredCandidate(
                candidate=candidate,
                analysis=analysis,
                rules=rule_eval,
                score=score.score,
                band=score.band,
                reasons=score.reasons,
                plugin_notes=[reason.label for reason in extra],
                source_path=source_path,
                source_encoding=encoding,
            )
            key = (candidate.file, candidate.line_no, candidate.digits, candidate.start)
            previous = best.get(key)
            if previous is None or entry.score > previous.score:
                best[key] = entry
                added += 1
        return added

    # ------------------------------------------------------------------
    @staticmethod
    def _emit(progress: ProgressCallback | None, event: ProgressEvent) -> None:
        if progress is None:
            return
        try:
            progress(event)
        except Exception:  # noqa: BLE001 - 进度回调不应影响扫描
            LOGGER.exception("进度回调出错")


def keyword_analysis_summary(analysis: KeywordAnalysis) -> str:
    """给报告用的一句话摘要。"""
    parts = []
    if analysis.group_tokens:
        parts.append("群关键词：" + "、".join(analysis.group_tokens[:4]))
    if analysis.ad_tokens:
        parts.append("广告词：" + "、".join(analysis.ad_tokens[:6]))
    return "；".join(parts)
