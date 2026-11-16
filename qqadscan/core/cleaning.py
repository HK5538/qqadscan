"""删除与输出：按用户勾选的行，生成「清理后」的新文件。

设计原则：

* **绝不悄悄改原文件**。默认输出到独立目录，文件名加后缀；
* 只有用户显式勾选「覆盖原文件」时才会写回，且自动生成 ``.bak`` 备份；
* 保留原文件的编码、BOM 和换行风格；
* 写文件用「临时文件 + 替换」，避免中途失败留下半个文件；
* 同时生成一份删除记录，方便事后核对删掉了什么。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from .textio import decode_bytes

DEFAULT_SUFFIX = "_已清理"
AUDIT_NAME = "_删除记录.txt"


@dataclass
class CleanPlan:
    """待删除的行，按文件分组。"""

    files: dict[Path, set[int]] = field(default_factory=dict)
    entries: list = field(default_factory=list)

    @property
    def total_lines(self) -> int:
        return sum(len(lines) for lines in self.files.values())

    @property
    def total_files(self) -> int:
        return len(self.files)

    def add(self, source: Path, line_no: int, entry=None) -> None:
        self.files.setdefault(Path(source), set()).add(int(line_no))
        if entry is not None:
            self.entries.append(entry)

    def empty(self) -> bool:
        return not self.files


@dataclass
class CleanOutcome:
    """单个文件的处理结果。"""

    source: Path
    target: Path
    removed: int = 0
    kept: int = 0
    backup: Path | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def build_plan(entries: Iterable, source_of=None) -> CleanPlan:
    """从扫描结果构建删除计划。

    ``entries`` 是 :class:`~qqadscan.core.scorer.ScoredCandidate`；
    ``source_of`` 用于取真实文件路径（默认读 ``entry.source_path``）。
    """
    plan = CleanPlan()
    for entry in entries:
        if source_of is not None:
            source = source_of(entry)
        else:
            source = getattr(entry, "source_path", None)
        if not source:
            continue
        plan.add(Path(source), entry.candidate.line_no, entry)
    return plan


def _read_lines(path: Path) -> tuple[list[str], str]:
    raw = path.read_bytes()
    text, encoding = decode_bytes(raw)
    return text.splitlines(keepends=True), encoding


def _unique_backup(path: Path) -> Path:
    candidate = path.with_name(path.name + ".bak")
    index = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak{index}")
        index += 1
    return candidate


def _atomic_write(target: Path, data: bytes) -> None:
    temp = target.with_name(target.name + ".tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, target)
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass


def clean_file(
    source: Path,
    target: Path,
    drop_lines: Iterable[int],
    *,
    overwrite: bool = False,
    backup: bool = True,
) -> CleanOutcome:
    """把 ``source`` 去掉指定行后写到 ``target``。

    ``overwrite=True`` 时 ``target`` 通常等于 ``source``，会先复制一份 ``.bak``。
    """
    source = Path(source)
    target = Path(target)
    drop = {int(item) for item in drop_lines}

    try:
        lines, encoding = _read_lines(source)
    except OSError as exc:
        return CleanOutcome(source, target, error=f"读取失败：{exc}")

    total = len(lines)
    kept_lines = [line for index, line in enumerate(lines, 1) if index not in drop]
    removed = total - len(kept_lines)

    write_encoding = encoding
    if encoding.endswith("(replace)"):
        write_encoding = "utf-8"

    try:
        data = "".join(kept_lines).encode(write_encoding, errors="replace")
    except (LookupError, UnicodeEncodeError) as exc:
        return CleanOutcome(source, target, error=f"编码失败：{exc}")

    backup_path: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if Path(target).resolve() == Path(source).resolve():
            if not overwrite:
                return CleanOutcome(source, target, error="目标与原文件相同，但未开启覆盖")
            if backup:
                backup_path = _unique_backup(source)
                shutil.copy2(source, backup_path)
        _atomic_write(target, data)
    except OSError as exc:
        return CleanOutcome(source, target, error=f"写入失败：{exc}")

    return CleanOutcome(
        source=source,
        target=target,
        removed=removed,
        kept=len(kept_lines),
        backup=backup_path,
    )


def _target_for(source: Path, base: Path, out_dir: Path, suffix: str) -> Path:
    """按相对结构生成输出路径，重名时自动加序号。"""
    try:
        relative = source.resolve().relative_to(base.resolve())
        candidate = out_dir / relative.parent / f"{relative.stem}{suffix}{relative.suffix}"
    except (ValueError, OSError):
        candidate = out_dir / f"{source.stem}{suffix}{source.suffix}"

    if not candidate.exists():
        return candidate
    index = 2
    while True:
        alternative = candidate.with_name(f"{candidate.stem}_{index}{candidate.suffix}")
        if not alternative.exists():
            return alternative
        index += 1


def run_plan(
    plan: CleanPlan,
    out_dir: Path,
    *,
    suffix: str = DEFAULT_SUFFIX,
    overwrite: bool = False,
    backup: bool = True,
    audit: bool = True,
) -> list[CleanOutcome]:
    """执行删除计划，返回每个文件的结果。"""
    out_dir = Path(out_dir)
    sources = list(plan.files)
    if not sources:
        return []

    base = Path(os.path.commonpath([str(item.resolve().parent) for item in sources]))
    outcomes: list[CleanOutcome] = []

    for source, lines in plan.files.items():
        if overwrite:
            target = source
        else:
            target = _target_for(source, base, out_dir, suffix)
        outcomes.append(
            clean_file(source, target, lines, overwrite=overwrite, backup=backup)
        )

    if audit:
        _write_audit(plan, outcomes, out_dir if not overwrite else Path(sources[0]).parent)
    return outcomes


def _write_audit(plan: CleanPlan, outcomes: Sequence[CleanOutcome], out_dir: Path) -> None:
    """写一份人类可读的删除记录，便于核对。"""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "删除记录",
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"删除行数：{plan.total_lines}，涉及文件：{plan.total_files}",
            "",
        ]
        for entry in sorted(
            plan.entries, key=lambda item: (str(getattr(item, "source_path", "")), item.candidate.line_no)
        ):
            candidate = entry.candidate
            lines.append(
                f"{candidate.file}:{candidate.line_no}\t{entry.score} 分 {entry.band_text}\t"
                f"{candidate.digits}\t{candidate.text.strip()}"
            )
        lines.append("")
        lines.append("输出文件：")
        for outcome in outcomes:
            status = "失败：" + outcome.error if outcome.error else f"已删除 {outcome.removed} 行"
            lines.append(f"  {outcome.source} -> {outcome.target}（{status}）")
        _atomic_write(out_dir / AUDIT_NAME, ("\n".join(lines) + "\n").encode("utf-8-sig"))
    except OSError:
        pass
