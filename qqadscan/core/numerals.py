"""中文数字解析：把「一百二十三」「二〇二六」这类写法还原成数值。

仅在候选号码完全由中文数字组成时使用，用于校正显示值（例如「二十五」应显示 25
而不是把每个字面数字拼成 205）。
"""

from __future__ import annotations

CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "壹": 1,
    "二": 2,
    "贰": 2,
    "貳": 2,
    "两": 2,
    "兩": 2,
    "俩": 2,
    "仨": 3,
    "三": 3,
    "叁": 3,
    "參": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陆": 6,
    "陸": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
}

CN_UNITS = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000}
CN_BIG_UNITS = {"万": 10_000, "萬": 10_000, "亿": 100_000_000, "億": 100_000_000}

#: 中文数字字符集合（用于判断「纯中文数字」）
CN_NUMERAL_CHARS = set(CN_DIGITS) | set(CN_UNITS) | set(CN_BIG_UNITS)


def is_cn_numeral_text(text: str) -> bool:
    return bool(text) and all(ch in CN_NUMERAL_CHARS for ch in text)


def cn_to_int(text: str) -> int | None:
    """把中文数字转成整数；无法解析时返回 None。"""
    text = (text or "").strip()
    if not text or not is_cn_numeral_text(text):
        return None

    # 没有单位词时按「逐位读法」处理：二〇二六 -> 2026
    if not any(ch in CN_UNITS or ch in CN_BIG_UNITS for ch in text):
        digits = "".join(str(CN_DIGITS[ch]) for ch in text)
        try:
            return int(digits)
        except ValueError:
            return None

    total = 0
    section = 0
    number = 0
    for ch in text:
        if ch in CN_DIGITS:
            number = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            unit = CN_UNITS[ch]
            if number == 0:
                number = 1  # 「十五」的十前面省略了一
            section += number * unit
            number = 0
        elif ch in CN_BIG_UNITS:
            unit = CN_BIG_UNITS[ch]
            section += number
            if unit >= 100_000_000:
                total = (total + section) * unit
            else:
                total += section * unit
            section = 0
            number = 0
        else:
            return None
    return total + section + number


def int_to_cn(value: int) -> str:
    """把整数转成中文读法（仅用于报告展示，0-99999999）。"""
    if value < 0:
        return str(value)
    if value == 0:
        return "零"
    digits = "零一二三四五六七八九"
    units = ["", "十", "百", "千"]
    big_units = ["", "万", "亿"]
    result = ""
    group_index = 0
    number = value
    while number > 0:
        group = number % 10000
        if group:
            group_text = ""
            zero_flag = False
            for index, unit in enumerate(units):
                digit = group // (10**index) % 10
                if digit == 0:
                    if group_text:
                        zero_flag = True
                    continue
                if zero_flag:
                    group_text = "零" + group_text
                    zero_flag = False
                group_text = digits[digit] + unit + group_text
            result = group_text + big_units[group_index] + result
        else:
            if result and not result.startswith("零"):
                result = "零" + result
        group_index += 1
        number //= 10000
    result = result.replace("零十", "零一十")
    if result.startswith("一十"):
        result = result[1:]
    return result
