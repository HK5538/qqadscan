"""报告导出：TXT（人看）/ CSV（Excel）/ JSON（程序读）。"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .. import APP_NAME, __version__
from .scanner import ScanResult

BAND_ORDER = ("A", "B", "C", "D")


def _timestamp(moment: datetime | None = None) -> str:
    return (moment or datetime.now()).strftime("%Y%m%d_%H%M%S")


def default_basename(result: ScanResult) -> str:
    stamp = _timestamp(result.started_at)
    return f"扫描报告_{stamp}"


def _band_counts_line(result: ScanResult) -> str:
    counts = result.band_counts()
    return " / ".join(f"{band} {label} {counts.get(band, 0)}" for band, label in
                      (("A", "高危"), ("B", "可疑"), ("C", "关注"), ("D", "低")))


def _header_lines(result: ScanResult) -> list[str]:
    lines = [
        "=" * 78,
        f"{APP_NAME} 扫描报告  v{__version__}",
        "=" * 78,
        f"生成时间 : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"耗时     : {result.duration:.2f} 秒",
        f"扫描范围 :",
    ]
    for root in result.roots:
        lines.append(f"  - {root}")
    lines += [
        f"文件     : 扫描 {result.files_scanned} / 共 {len(result.files)} 个，"
        f"共 {result.lines_scanned} 行",
        f"命中     : {result.total_hits} 条（{_band_counts_line(result)}）",
        f"词库     : {result.lexicon_stats.get('digit_mappings', 0)} 条数字映射 / "
        f"{result.lexicon_stats.get('group_keywords', 0)} 个群关键词 / "
        f"{result.lexicon_stats.get('ad_keywords', 0)} 个广告词",
    ]
    if result.plugin_names:
        lines.append(f"插件     : {', '.join(result.plugin_names)}")
    for note in result.plugin_notes:
        lines.append(f"插件说明 : {note}")
    lines.append("")
    lines.append("※ 扫描过程只读；删除需要用户在界面里手动标记并输出，不会自动改动原文件。")
    if result.cancelled:
        lines.append("※ 本次扫描被用户中途取消，结果可能不完整。")
    if result.errors:
        lines.append("")
        lines.append("警告：")
        for error in result.errors[:20]:
            lines.append(f"  ! {error}")
    if result.plugin_errors:
        lines.append("")
        lines.append("插件问题：")
        for error in result.plugin_errors[:20]:
            lines.append(f"  ! {error}")
    lines.append("")
    return lines


def _entry_block(index: int, entry, width: int = 78) -> list[str]:
    candidate = entry.candidate
    lines = ["-" * width]
    lines.append(
        f"[{index:03d}] 分数 {entry.score:3d}  {entry.band_text:<6} "
        f"{candidate.file}:{candidate.line_no}"
    )
    lines.append("-" * width)
    lines.append(f"解密号码 : {candidate.digits}")
    meta = [f"{len(candidate.digits)} 位"]
    if candidate.numeric_value is not None:
        meta.append(f"中文数字换算值 {candidate.numeric_value}")
    meta.append(f"伪装类型：{candidate.kind_summary}")
    meta.append(f"噪音字符 {candidate.noise_count} 个")
    lines.append("号码信息 : " + "；".join(meta))
    if entry.group_tokens:
        best = entry.analysis.best_group
        distance = f"（最近距离 {best.distance} 字）" if best else ""
        lines.append(f"群关键词 : {'、'.join(entry.group_tokens[:6])}{distance}")
    if entry.ad_tokens:
        lines.append(f"广告词   : {'、'.join(entry.ad_tokens[:8])}")
    if entry.rule_labels:
        lines.append(f"规则提示 : {'、'.join(entry.rule_labels)}")
    lines.append(f"原文     : {candidate.marked(radius=40)}")
    lines.append(f"完整行   : {candidate.text.strip()}")
    lines.append("解码过程 :")
    for step in candidate.decode_steps()[:24]:
        lines.append(f"    {step}")
    lines.append("评分明细 :")
    for reason in entry.reasons:
        detail = f"（{reason.detail}）" if reason.detail else ""
        lines.append(f"    {reason.label:<10} {reason.delta:+6.1f}{detail}")
    lines.append("")
    return lines


def export_txt(result: ScanResult, path: Path, *, include_low: bool = True) -> Path:
    lines = _header_lines(result)
    entries = [e for e in result.entries if include_low or e.band != "D"]
    if not entries:
        lines.append("没有命中任何条目。")
    else:
        for index, entry in enumerate(entries, 1):
            lines.extend(_entry_block(index, entry))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


CSV_HEADER = [
    "序号",
    "分数",
    "等级",
    "文件",
    "行号",
    "解密号码",
    "号码位数",
    "伪装类型",
    "群关键词",
    "广告词",
    "规则提示",
    "原文",
    "上下文",
    "评分明细",
]


def export_csv(result: ScanResult, path: Path, *, include_low: bool = True) -> Path:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    index = 0
    for entry in result.entries:
        if not include_low and entry.band == "D":
            continue
        index += 1
        candidate = entry.candidate
        writer.writerow(
            [
                index,
                entry.score,
                entry.band_text,
                candidate.file,
                candidate.line_no,
                candidate.digits,
                len(candidate.digits),
                candidate.kind_summary,
                "、".join(entry.group_tokens),
                "、".join(entry.ad_tokens),
                "、".join(entry.rule_labels),
                candidate.text.strip(),
                candidate.marked(radius=30),
                " | ".join(reason.format() for reason in entry.reasons),
            ]
        )
    path.write_text("\ufeff" + buffer.getvalue(), encoding="utf-8", newline="")
    return path


def export_json(result: ScanResult, path: Path, *, include_low: bool = True) -> Path:
    payload = {
        "app": APP_NAME,
        "version": __version__,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": result.started_at.isoformat(timespec="seconds"),
        "duration_seconds": round(result.duration, 3),
        "roots": result.roots,
        "files": [
            {
                "path": item.display,
                "encoding": item.encoding,
                "size": item.size,
                "lines": item.lines,
                "hits": item.hits,
                "error": item.error,
            }
            for item in result.files
        ],
        "summary": {
            "files_scanned": result.files_scanned,
            "lines_scanned": result.lines_scanned,
            "total_hits": result.total_hits,
            "bands": result.band_counts(),
            "cancelled": result.cancelled,
            "lexicon": result.lexicon_stats,
            "plugins": result.plugin_names,
        },
        "errors": result.errors,
        "plugin_errors": result.plugin_errors,
        "entries": [
            {
                "score": entry.score,
                "band": entry.band,
                "band_label": entry.band_label,
                "file": entry.candidate.file,
                "line": entry.candidate.line_no,
                "digits": entry.candidate.digits,
                "span": list(entry.candidate.span),
                "raw": entry.candidate.raw,
                "text": entry.candidate.text,
                "kinds": entry.candidate.kinds,
                "obfuscation": round(entry.candidate.obfuscation, 3),
                "noise_count": entry.candidate.noise_count,
                "group_keywords": entry.group_tokens,
                "ad_keywords": entry.ad_tokens,
                "rule_hits": [asdict(hit) for hit in entry.rules.hits],
                "reasons": [asdict(reason) for reason in entry.reasons],
                "steps": entry.candidate.decode_steps(),
                "atoms": [
                    {
                        "token": atom.token,
                        "digit": atom.digit,
                        "kind": atom.kind,
                        "start": atom.start,
                        "end": atom.end,
                        "weight": atom.weight,
                    }
                    for atom in entry.candidate.atoms
                ],
            }
            for entry in result.entries
            if include_low or entry.band != "D"
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_reports(
    result: ScanResult,
    out_dir: Path,
    *,
    formats: list[str] | tuple[str, ...] = ("txt", "csv", "json"),
    include_low: bool = True,
    basename: str | None = None,
) -> list[Path]:
    """按格式导出报告，返回生成的文件列表。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    base = basename or default_basename(result)
    written: list[Path] = []
    for fmt in formats:
        fmt = fmt.lower().strip()
        if fmt == "txt":
            written.append(export_txt(result, out_dir / f"{base}.txt", include_low=include_low))
        elif fmt == "csv":
            written.append(export_csv(result, out_dir / f"{base}.csv", include_low=include_low))
        elif fmt == "json":
            written.append(export_json(result, out_dir / f"{base}.json", include_low=include_low))
    return written


def print_summary(result: ScanResult) -> str:
    counts = result.band_counts()
    lines = [
        f"扫描完成：{result.files_scanned} 个文件 / {result.lines_scanned} 行，"
        f"用时 {result.duration:.2f} 秒",
        f"命中 {result.total_hits} 条："
        f"A 高危 {counts['A']}、B 可疑 {counts['B']}、C 关注 {counts['C']}、D 低 {counts['D']}",
    ]
    if result.entries:
        top = result.entries[:5]
        lines.append("高分条目：")
        for entry in top:
            lines.append(
                f"  {entry.score:3d} {entry.band_text} {entry.candidate.file}:"
                f"{entry.candidate.line_no} -> {entry.candidate.digits}"
            )
    return "\n".join(lines)
