"""命令行入口。

用法示例::

    python -m qqadscan                       # 打开图形界面
    python -m qqadscan scan D:\\logs          # 扫描目录
    python -m qqadscan scan a.txt --min-score 50 --formats txt,csv
    python -m qqadscan decode "㈡〔〔氿▲4⊥〖婈４□（叁5〓>⒍思蒐←索≌q羣："
    python -m qqadscan lexicon               # 查看词库统计
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .config import Config
from .core.decoder import KIND_LABELS, decode_line
from .core.lexicon import Lexicon
from .core.report import print_summary, write_reports
from .core.scanner import ScanOptions, Scanner
from .paths import get_paths
from .plugins.loader import PluginManager


def _build_lexicon(config: Config, lexicon_dir: Path | None) -> Lexicon:
    paths = get_paths()
    primary = lexicon_dir or paths.lexicon
    return Lexicon.load(primary)


def _make_scanner(config: Config, lexicon: Lexicon, use_plugins: bool, verbose: bool):
    paths = get_paths()
    manager = None
    if use_plugins and config.plugins_enabled:
        manager = PluginManager(config=config, lexicon=lexicon, paths=paths)
        manager.load()
    return Scanner(config, lexicon, manager)


def cmd_scan(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.config) if args.config else None)
    for warning in config.warnings:
        print(f"[配置] {warning}", file=sys.stderr)
    lexicon = _build_lexicon(config, Path(args.lexicon) if args.lexicon else None)
    scanner = _make_scanner(config, lexicon, not args.no_plugins, args.verbose)

    paths_to_scan = [Path(p) for p in args.paths]
    missing = [p for p in paths_to_scan if not p.exists()]
    for item in missing:
        print(f"[错误] 路径不存在：{item}", file=sys.stderr)
    paths_to_scan = [p for p in paths_to_scan if p.exists()]
    if not paths_to_scan:
        return 2

    options = ScanOptions(
        paths=paths_to_scan,
        recursive=None if args.recursive is None else args.recursive,
        min_score=args.min_score,
        max_entries=args.max_entries,
    )

    if config.warnings:
        print(f"[词库] {'；'.join(lexicon.warnings[:3])}", file=sys.stderr)

    def on_progress(event):
        if not args.verbose:
            return
        if event.phase == "file":
            print(f"  [{event.files_done}/{event.files_total}] {event.current_file}", file=sys.stderr)
        elif event.phase == "progress":
            print(
                f"\r  已扫 {event.lines_done} 行，命中 {event.hits} 条",
                end="",
                file=sys.stderr,
                flush=True,
            )

    result = scanner.scan(options, progress=on_progress)
    if args.verbose:
        print("", file=sys.stderr)
    print(print_summary(result))

    out_dir = Path(args.out) if args.out else get_paths().reports
    formats = [f.strip() for f in (args.formats or "txt,csv,json").split(",") if f.strip()]
    written = write_reports(
        result,
        out_dir,
        formats=formats,
        include_low=not args.no_low,
        basename=args.name,
    )
    print("报告已生成：")
    for path in written:
        print(f"  {path}")
    if result.entries and not args.no_console:
        print("\n高分条目（前 10 条）：")
        for entry in result.entries[:10]:
            print(
                f"  {entry.score:3d} {entry.band_text}  {entry.candidate.file}:"
                f"{entry.candidate.line_no}  {entry.candidate.digits}"
            )
            print(f"       {entry.candidate.marked(radius=30)}")
    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.config) if args.config else None)
    lexicon = _build_lexicon(config, Path(args.lexicon) if args.lexicon else None)
    scanner = _make_scanner(config, lexicon, False, False)
    text = args.text
    candidates = decode_line(
        text,
        lexicon,
        min_digits=args.min_digits or config.min_digits,
        max_digits=config.max_digits,
        max_gap=config.max_gap,
        boundaries=config.boundary_chars,
        noise_precedence=config.noise_precedence,
        place_value=config.chinese_place_value,
    )
    print(f"原文：{text}")
    print(f"词库：{lexicon.describe()}")
    if not candidates:
        print("结果：没有识别到候选号码")
        return 1
    for index, candidate in enumerate(candidates, 1):
        analysis = scanner.scorer.analyze(candidate)
        rules = scanner.rules.evaluate(candidate, has_group_evidence=analysis.has_group_evidence)
        score = scanner.scorer.score(candidate, analysis, rules)
        print("")
        print(f"[{index}] 解密号码：{candidate.digits}   分数 {score.score}（{score.band_text}）")
        print(f"    片段：{candidate.marked(radius=20)}")
        print(f"    类型：{candidate.kind_summary}；噪音 {candidate.noise_count} 个")
        if analysis.group_tokens:
            print(f"    群词：{'、'.join(analysis.group_tokens)}")
        if analysis.ad_tokens:
            print(f"    广告：{'、'.join(analysis.ad_tokens)}")
        steps = candidate.decode_steps()
        if steps:
            print("    解码：" + " ".join(steps))
        for reason in score.reasons:
            print(f"      {reason.label:<10}{reason.delta:+6.1f}  {reason.detail}")
    return 0


def cmd_lexicon(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.config) if args.config else None)
    lexicon = _build_lexicon(config, Path(args.lexicon) if args.lexicon else None)
    print(f"{APP_NAME} v{__version__}")
    print(f"词库目录：{get_paths().lexicon}")
    print(lexicon.describe())
    print("")
    if args.dump:
        for token, item in sorted(lexicon.digits.items(), key=lambda kv: (kv[1].digit, len(kv[0]))):
            print(f"  {item.digit}  {token:<6} {KIND_LABELS.get(item.kind, item.kind):<8} {item.weight:.2f}  {item.note}")
    if lexicon.warnings:
        print("")
        print("问题：")
        for warning in lexicon.warnings[:30]:
            print(f"  ! {warning}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qqadscan",
        description=f"{APP_NAME} —— 只读扫描 txt 中的伪装 QQ 群广告并评分",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="扫描文件或目录")
    scan.add_argument("paths", nargs="+", help="文件或目录")
    scan.add_argument("--min-score", type=int, default=0, help="只输出不低于该分数的条目")
    scan.add_argument("--max-entries", type=int, default=0, help="最多输出多少条（0=不限）")
    scan.add_argument("--formats", default="txt,csv,json", help="报告格式，逗号分隔")
    scan.add_argument("--out", default="", help="报告输出目录")
    scan.add_argument("--name", default="", help="报告文件名前缀")
    scan.add_argument("--no-low", action="store_true", help="报告里不包含 D 级（低）条目")
    scan.add_argument("--no-plugins", action="store_true", help="禁用插件")
    scan.add_argument("--no-console", action="store_true", help="不打印高分条目")
    scan.add_argument("--recursive", dest="recursive", action="store_true", default=None)
    scan.add_argument("--no-recursive", dest="recursive", action="store_false")
    scan.add_argument("--config", default="", help="指定 config.json")
    scan.add_argument("--lexicon", default="", help="指定词库目录")
    scan.add_argument("-v", "--verbose", action="store_true")
    scan.set_defaults(func=cmd_scan)

    decode = sub.add_parser("decode", help="解码一行文本，看看能还原出什么")
    decode.add_argument("text", help="要解码的文本")
    decode.add_argument("--min-digits", type=int, default=0)
    decode.add_argument("--config", default="")
    decode.add_argument("--lexicon", default="")
    decode.set_defaults(func=cmd_decode)

    lexicon_cmd = sub.add_parser("lexicon", help="查看词库统计")
    lexicon_cmd.add_argument("--dump", action="store_true", help="列出全部数字映射")
    lexicon_cmd.add_argument("--config", default="")
    lexicon_cmd.add_argument("--lexicon", default="")
    lexicon_cmd.set_defaults(func=cmd_lexicon)

    return parser


def _configure_stdio() -> None:
    """管道/重定向时改用 UTF-8 输出，避免中文在非 UTF-8 环境里乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            if not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=logging.INFO if ("-v" in argv or "--verbose" in argv) else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not argv:
        try:
            from .gui.app import run_gui
        except Exception as exc:  # noqa: BLE001 - 例如精简版 Python 没有 tkinter
            print(f"无法加载图形界面（{exc}）。", file=sys.stderr)
            print("可以改用命令行，例如：python -m qqadscan scan D:\\logs", file=sys.stderr)
            return 1
        return run_gui()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
