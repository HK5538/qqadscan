"""生成 lexicon/20_digits_symbol.tsv。

圈号、括号号、实心号、罗马数字、上下标、全角、骰子、键帽等「看着就是数字」的符号。
改完这个脚本后运行 ``python tools/gen_symbol_lexicon.py`` 即可重新生成。

用法：
    python tools/gen_symbol_lexicon.py [输出路径]
"""

from __future__ import annotations

import sys
from pathlib import Path

HEADER = "token\tcategory\tvalue\tkind\tweight\tnote\n"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "lexicon" / "20_digits_symbol.tsv"


def build_rows() -> list[tuple[str, int, str, float, str]]:
    rows: list[tuple[str, int, str, float, str]] = []

    def add(chars: str, weight: float, note: str, start: int = 1) -> None:
        for offset, char in enumerate(chars):
            digit = start + offset
            if 0 <= digit <= 9:
                rows.append((char, digit, "symbol", weight, note))

    # ①..⑨（1-9）
    add("".join(chr(0x2460 + i) for i in range(9)), 0.95, "圈号数字")
    # ⓪（0）、⑩ 以上不用
    rows.append((chr(0x24EA), 0, "symbol", 0.95, "圈号数字"))
    # ⑴..⑼
    add("".join(chr(0x2474 + i) for i in range(9)), 0.95, "括号数字")
    # ⒈..⒐
    add("".join(chr(0x2488 + i) for i in range(9)), 0.9, "点号数字")
    # ❶..❾
    add("".join(chr(0x2776 + i) for i in range(9)), 0.95, "实心圈数字")
    # ➀..➈
    add("".join(chr(0x2780 + i) for i in range(9)), 0.95, "实心圈数字")
    # ➊..➒
    add("".join(chr(0x278A + i) for i in range(9)), 0.95, "实心圈数字")
    # ⓵..⓽
    add("".join(chr(0x24F5 + i) for i in range(9)), 0.9, "双圈数字")
    # ㈠..㈨
    add("".join(chr(0x3220 + i) for i in range(9)), 0.95, "中文括号数字")
    # ㊀..㊈
    add("".join(chr(0x3280 + i) for i in range(9)), 0.95, "中文圈号数字")
    # Ⅰ..Ⅸ / ⅰ..ⅸ
    add("".join(chr(0x2160 + i) for i in range(9)), 0.75, "罗马数字")
    add("".join(chr(0x2170 + i) for i in range(9)), 0.75, "罗马数字")
    # 全角 １..９（０单独）
    add("".join(chr(0xFF11 + i) for i in range(9)), 0.60, "全角数字")
    rows.append((chr(0xFF10), 0, "symbol", 0.60, "全角数字"))
    # 上标 ⁰¹²³⁴⁵⁶⁷⁸⁹
    superscripts = "⁰¹²³⁴⁵⁶⁷⁸⁹"
    for digit, char in enumerate(superscripts):
        rows.append((char, digit, "symbol", 0.7, "上标数字"))
    # 下标 ₀..₉
    add("".join(chr(0x2080 + i) for i in range(9)), 0.7, "下标数字", start=0)
    # 骰子 ⚀..⚅
    add("".join(chr(0x2680 + i) for i in range(6)), 0.5, "骰子点数")
    # 键帽 0️⃣..9️⃣
    for digit in range(10):
        rows.append((f"{digit}\ufe0f\u20e3", digit, "symbol", 0.9, "键帽 emoji"))
    return rows


def render() -> str:
    lines = [
        "# 圈号 / 符号数字映射（自动生成，请勿手工编辑；改 tools/gen_symbol_lexicon.py 后重新生成）",
        "# 格式：token <TAB> category <TAB> value <TAB> kind <TAB> weight <TAB> note",
        HEADER.rstrip("\n"),
    ]
    seen: set[str] = set()
    for token, digit, kind, weight, note in build_rows():
        if token in seen:
            continue
        seen.add(token)
        lines.append(f"{token}\tdigit\t{digit}\t{kind}\t{weight:.2f}\t{note}")
    return "\n".join(lines) + "\n"


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(), encoding="utf-8")
    print(f"已生成 {output}（{output.read_text(encoding='utf-8').count(chr(10)) - 4} 条映射）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
