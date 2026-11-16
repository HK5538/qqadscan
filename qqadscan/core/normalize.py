"""文本归一化工具。

这里只做「不改变字符数量」的归一化，保证归一化后的下标可以直接映射回原文，
这样报告里的高亮位置才不会错位。
"""

from __future__ import annotations

import re

#: 零宽字符：常被用来切断数字串，肉眼看不见。保留占位（当成噪音字符）。
ZERO_WIDTH_CHARS = "\u200b\u200c\u200d\u2060\ufeff\u00ad"

#: 常见繁体/异体字 -> 简体（仅用于关键词匹配，长度一一对应）
T2S_MAP = {
    "羣": "群",
    "群": "群",
    "號": "号",
    "費": "费",
    "視": "视",
    "頻": "频",
    "資": "资",
    "進": "进",
    "聯": "联",
    "繫": "系",
    "係": "系",
    "領": "领",
    "幣": "币",
    "賺": "赚",
    "錢": "钱",
    "帶": "带",
    "開": "开",
    "關": "关",
    "註": "注",
    "冊": "册",
    "軟": "软",
    "體": "体",
    "網": "网",
    "盤": "盘",
    "鏈": "链",
    "結": "结",
    "給": "给",
    "個": "个",
    "們": "们",
    "這": "这",
    "來": "来",
    "時": "时",
    "間": "间",
    "點": "点",
    "現": "现",
    "場": "场",
    "電": "电",
    "話": "话",
    "機": "机",
    "視頻": "视频",
    "劇": "剧",
    "動": "动",
    "漫": "漫",
    "劃": "划",
    "遊": "游",
    "戲": "戏",
    "種": "种",
    "子": "子",
    "無": "无",
    "碼": "码",
    "專": "专",
    "業": "业",
    "團": "团",
    "隊": "队",
    "優": "优",
    "惠": "惠",
    "券": "券",
    "賺錢": "赚钱",
    "寶": "宝",
    "貝": "贝",
    "護": "护",
    "師": "师",
    "學": "学",
    "習": "习",
    "員": "员",
    "會": "会",
    "員": "员",
    "麼": "么",
    "樣": "样",
    "讓": "让",
    "還": "还",
    "說": "说",
    "謝": "谢",
    "請": "请",
    "歡": "欢",
    "迎": "迎",
}

_ASCII_LOWER = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"
)


def fold(text: str) -> str:
    """生成用于关键词比较的折叠文本（长度与原文一致）。

    * ASCII 大写转小写；
    * 常见繁体/异体字转简体；
    * 其它字符原样保留。
    """
    if not text:
        return ""
    folded = text.translate(_ASCII_LOWER)
    if any(ch in T2S_MAP for ch in folded):
        folded = "".join(T2S_MAP.get(ch, ch) for ch in folded)
    return folded


def fold_char(ch: str) -> str:
    """单字符折叠，用于词库录入时的规范化。"""
    return fold(ch)


def is_zero_width(ch: str) -> bool:
    return ch in ZERO_WIDTH_CHARS


def is_latin_letter(ch: str) -> bool:
    return ch.isascii() and ch.isalpha()


def is_ascii_digit(ch: str) -> bool:
    return ch.isascii() and ch.isdigit()


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_PUNCT_RE = re.compile(r"[\W_]", re.UNICODE)


def is_cjk(ch: str) -> bool:
    return bool(_CJK_RE.match(ch))


def is_symbol_like(ch: str) -> bool:
    """是否是「符号类」字符（非文字、非空白、非数字）。"""
    if ch.isalnum() or ch.isspace():
        return False
    return bool(_PUNCT_RE.match(ch))


def visual_width(text: str) -> int:
    """估算显示宽度（中日韩字符按 2 计）。"""
    width = 0
    for ch in text:
        width += 2 if (is_cjk(ch) or ord(ch) > 0x1F000) else 1
    return width


def truncate_display(text: str, max_width: int = 80, ellipsis: str = "…") -> str:
    """按显示宽度截断文本。"""
    if visual_width(text) <= max_width:
        return text
    out = []
    width = 0
    for ch in text:
        w = 2 if (is_cjk(ch) or ord(ch) > 0x1F000) else 1
        if width + w > max_width - 1:
            break
        out.append(ch)
        width += w
    return "".join(out) + ellipsis
