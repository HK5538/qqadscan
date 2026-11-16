"""排除规则：把「明显不是群号」的候选过滤掉。

每条规则都有三档，可在 config.json 的 ``rules`` 里单独设置：

* ``off``    —— 不启用
* ``smart``  —— 只有当号码附近没有任何群关键词时才排除（推荐，误伤最少）
* ``always`` —— 一律排除

已内置的规则：

============  ==========================================================
纯阿拉伯数字    ``123456789`` 这种没有任何伪装的号码
纯中文数字      ``一百二十三`` 这种全中文写法
量词            ``10元`` ``一百块`` ``99折`` 这类价格/数量
时间            ``下午一点`` ``18:10`` ``23:59:59``
日期            ``2026-11-17`` ``2026年11月``
电话            中国大陆手机号 / 座机号
============  ==========================================================
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import Config
from .decoder import Candidate
from .lexicon import Lexicon

#: 价格前缀符号
PRICE_PREFIXES = "¥￥$€£"

#: 常见量词（词库之外的内置兜底，用户可在 lexicon/90_quantifiers.tsv 增删）
DEFAULT_QUANTIFIERS = (
    "元",
    "块",
    "圆",
    "角",
    "毛",
    "分",
    "万",
    "千",
    "百",
    "米",
    "岁",
    "折",
    "个",
    "件",
    "只",
    "套",
    "台",
    "部",
    "次",
    "人",
    "位",
    "张",
    "瓶",
    "包",
    "袋",
    "箱",
    "盒",
    "斤",
    "克",
    "吨",
    "升",
    "度",
    "天",
    "年",
    "月",
    "日",
    "小时",
    "分钟",
    "秒",
    "公里",
    "千米",
    "厘米",
    "毫米",
    "GB",
    "MB",
    "TB",
    "g",
    "kg",
    "ml",
    "cm",
    "mm",
    "km",
    "%",
    "％",
)

_RE_TIME_CLOCK = re.compile(r"\d{1,2}\s*[:：]\s*\d{2}(?:\s*[:：]\s*\d{2})?")
_RE_TIME_HALF = re.compile(r"\d{1,2}\s*[点點时時]\s*半")
_RE_TIME_POINT = re.compile(
    r"(?:上午|下午|中午|晚上|凌晨|早上|傍晚|深夜|半夜|今早|今晚)?\s*"
    r"[0-9〇零一二三四五六七八九十两]{1,3}\s*[点點时時]"
    r"(?:\s*(?:半|[0-9〇零一二三四五六七八九十]{1,3}\s*分?))?"
)
_RE_TIME_PERIOD = re.compile(r"(?:上午|下午|中午|晚上|凌晨|早上|傍晚|深夜|半夜)")
_RE_DATE_FULL = re.compile(r"\d{4}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}\s*[日号]?")
_RE_DATE_SHORT = re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]")
_RE_YEAR = re.compile(r"(?:19|20)\d{2}\s*年")
_RE_PHONE = re.compile(r"1[3-9]\d{9}")
_RE_LANDLINE = re.compile(r"0\d{2,3}[-\s]?\d{7,8}")
_RE_ID_LIKE = re.compile(r"(?:ID|id|编号|序号|订单号|身份证|卡号|流水号)\s*[:：]?\s*$")


@dataclass
class RuleHit:
    code: str
    label: str
    action: str  # skip | penalty | note
    penalty: float = 0.0
    detail: str = ""

    @property
    def is_skip(self) -> bool:
        return self.action == "skip"


@dataclass
class RuleEvaluation:
    hits: list[RuleHit] = field(default_factory=list)

    @property
    def skipped(self) -> bool:
        return any(hit.is_skip for hit in self.hits)

    @property
    def penalty(self) -> float:
        return sum(hit.penalty for hit in self.hits if hit.action == "penalty")

    @property
    def labels(self) -> list[str]:
        return [hit.label for hit in self.hits if hit.action != "note"]

    def add(self, hit: RuleHit) -> None:
        self.hits.append(hit)


class RuleEngine:
    """规则引擎。"""

    def __init__(self, config: Config, lexicon: Lexicon) -> None:
        self.config = config
        self.lexicon = lexicon
        quantifiers = list(DEFAULT_QUANTIFIERS) + list(lexicon.quantifiers.keys())
        # 长词优先，避免「分钟」被「分」抢先匹配
        self.quantifiers = sorted({q for q in quantifiers if q}, key=len, reverse=True)

    # ------------------------------------------------------------------
    def evaluate(self, candidate: Candidate, *, has_group_evidence: bool) -> RuleEvaluation:
        result = RuleEvaluation()
        weights = self.config.weights

        self._check_pure_arabic(candidate, has_group_evidence, weights, result)
        self._check_pure_chinese(candidate, has_group_evidence, weights, result)
        self._check_quantifier(candidate, has_group_evidence, weights, result)
        self._check_time(candidate, has_group_evidence, weights, result)
        self._check_date(candidate, has_group_evidence, weights, result)
        self._check_phone(candidate, has_group_evidence, weights, result)
        self._check_id_context(candidate, weights, result)
        return result

    # ------------------------------------------------------------------
    def _mode(self, name: str) -> str:
        return self.config.rule_mode(name)

    @staticmethod
    def _skip_or_penalty(
        mode: str,
        has_evidence: bool,
        penalty: float,
    ) -> tuple[str, float]:
        if mode == "off":
            return "none", 0.0
        if mode == "always":
            return "skip", 0.0
        # smart
        if has_evidence:
            return "penalty", penalty * 0.35
        return "skip", 0.0

    def _check_pure_arabic(
        self,
        candidate: Candidate,
        has_evidence: bool,
        weights: dict[str, float],
        result: RuleEvaluation,
    ) -> None:
        if not candidate.plain_ascii:
            return
        mode = self._mode("pure_arabic")
        action, penalty = self._skip_or_penalty(mode, has_evidence, weights["penalty_pure_arabic"])
        if action == "skip":
            result.add(
                RuleHit(
                    "pure_arabic",
                    "排除：纯阿拉伯数字",
                    "skip",
                    detail="没有任何伪装迹象，且附近没有群关键词（可在 config.json 改为 off/always）",
                )
            )
        elif action == "penalty":
            result.add(
                RuleHit("pure_arabic", "纯阿拉伯数字", "penalty", penalty, "号码完全由普通数字写成")
            )

    def _check_pure_chinese(
        self,
        candidate: Candidate,
        has_evidence: bool,
        weights: dict[str, float],
        result: RuleEvaluation,
    ) -> None:
        if not candidate.plain_cjk:
            return
        mode = self._mode("pure_chinese")
        action, penalty = self._skip_or_penalty(mode, has_evidence, weights["penalty_pure_chinese"])
        if action == "skip":
            result.add(
                RuleHit(
                    "pure_chinese",
                    "排除：纯中文数字",
                    "skip",
                    detail="全部是中文数字写法，且附近没有群关键词",
                )
            )
        elif action == "penalty":
            result.add(
                RuleHit("pure_chinese", "纯中文数字", "penalty", penalty, "全中文数字写法")
            )

    # ------------------------------------------------------------------
    def _check_quantifier(
        self,
        candidate: Candidate,
        has_evidence: bool,
        weights: dict[str, float],
        result: RuleEvaluation,
    ) -> None:
        if candidate.obfuscation > 0.05:
            return
        tail = candidate.text[candidate.end : candidate.end + 12]
        tail_stripped = tail.lstrip(" \t　")
        matched = ""
        for quantifier in self.quantifiers:
            if tail_stripped.lower().startswith(quantifier.lower()):
                matched = quantifier
                break

        head = candidate.text[max(0, candidate.start - 4) : candidate.start]
        head_stripped = head.rstrip(" \t　")
        has_price_prefix = bool(head_stripped) and head_stripped[-1] in PRICE_PREFIXES
        has_price_word = head_stripped.endswith(("售价", "价格", "单价", "总价", "原价", "现价"))

        if not (matched or has_price_prefix or has_price_word):
            return

        mode = self._mode("quantifier")
        action, penalty = self._skip_or_penalty(mode, has_evidence, weights["penalty_quantifier"])
        detail = (
            f"号码后面紧跟「{matched}」" if matched else "号码前面有价格符号/价格词"
        )
        if action == "skip":
            result.add(RuleHit("quantifier", "排除：数量/价格", "skip", detail=detail))
        elif action == "penalty":
            result.add(RuleHit("quantifier", "疑似数量/价格", "penalty", penalty, detail))

    def _check_time(
        self,
        candidate: Candidate,
        has_evidence: bool,
        weights: dict[str, float],
        result: RuleEvaluation,
    ) -> None:
        window, offset = self._window(candidate, 20)
        match_text = ""
        for pattern in (_RE_TIME_CLOCK, _RE_TIME_HALF, _RE_TIME_POINT):
            for match in pattern.finditer(window):
                start = match.start() + offset
                end = match.end() + offset
                if start < candidate.end and end > candidate.start:
                    match_text = match.group(0)
                    break
            if match_text:
                break
        if not match_text:
            return

        mode = self._mode("time")
        action, penalty = self._skip_or_penalty(mode, has_evidence, weights["penalty_time"])
        if action == "skip":
            result.add(RuleHit("time", "排除：时间", "skip", detail=f"命中时间写法「{match_text.strip()}」"))
        elif action == "penalty":
            result.add(
                RuleHit("time", "疑似时间", "penalty", penalty, f"命中时间写法「{match_text.strip()}」")
            )

    def _check_date(
        self,
        candidate: Candidate,
        has_evidence: bool,
        weights: dict[str, float],
        result: RuleEvaluation,
    ) -> None:
        window, offset = self._window(candidate, 24)
        matched = ""
        for pattern in (_RE_DATE_FULL, _RE_DATE_SHORT):
            for match in pattern.finditer(window):
                start = match.start() + offset
                end = match.end() + offset
                if start < candidate.end and end > candidate.start:
                    matched = match.group(0)
                    break
            if matched:
                break
        if not matched:
            for match in _RE_YEAR.finditer(window):
                start = match.start() + offset
                end = match.end() + offset
                if start <= candidate.start and end >= candidate.end:
                    matched = match.group(0)
                    break
        if not matched:
            return

        mode = self._mode("date")
        action, penalty = self._skip_or_penalty(mode, has_evidence, weights["penalty_date"])
        if action == "skip":
            result.add(RuleHit("date", "排除：日期/年份", "skip", detail=f"命中日期写法「{matched.strip()}」"))
        elif action == "penalty":
            result.add(
                RuleHit("date", "疑似日期/年份", "penalty", penalty, f"命中日期写法「{matched.strip()}」")
            )

    def _check_phone(
        self,
        candidate: Candidate,
        has_evidence: bool,
        weights: dict[str, float],
        result: RuleEvaluation,
    ) -> None:
        digits = candidate.digits
        if not (candidate.plain_ascii and (_RE_PHONE.fullmatch(digits) or _RE_LANDLINE.fullmatch(digits))):
            return
        mode = self._mode("phone")
        action, penalty = self._skip_or_penalty(mode, has_evidence, weights["penalty_phone"])
        if action == "skip":
            result.add(RuleHit("phone", "排除：电话号码", "skip", detail="号码符合手机号/座机号格式"))
        elif action == "penalty":
            result.add(RuleHit("phone", "疑似电话号码", "penalty", penalty, "号码符合手机号/座机号格式"))

    def _check_id_context(
        self,
        candidate: Candidate,
        weights: dict[str, float],
        result: RuleEvaluation,
    ) -> None:
        head = candidate.text[max(0, candidate.start - 12) : candidate.start]
        if _RE_ID_LIKE.search(head):
            result.add(
                RuleHit(
                    "id_like",
                    "疑似编号/ID",
                    "penalty",
                    weights["penalty_pure_arabic"] * 0.6,
                    "号码前面是「ID/编号/订单号」等字样",
                )
            )

    # ------------------------------------------------------------------
    @staticmethod
    def _window(candidate: Candidate, radius: int) -> tuple[str, int]:
        start = max(0, candidate.start - radius)
        end = min(len(candidate.text), candidate.end + radius)
        return candidate.text[start:end], start
