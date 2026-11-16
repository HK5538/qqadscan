"""评分器：把各种信号折算成 0-100 的「疑似广告」分数，并给出可解释的理由。

评分是可解释的：每条加减分都会记录成一条 ``Reason``，报告和界面里都能看到。

分数分档（可在 config.json 的 ``score.thresholds`` 调整）：

* **A 高危** ≥ 75 —— 强烈建议人工确认
* **B 可疑** ≥ 50 —— 有明显广告特征
* **C 关注** ≥ 30 —— 有部分特征，可能是误伤
* **D 低**   < 30 —— 基本可以忽略
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..config import Config
from .decoder import Candidate, OBFUSCATED_KIND_ORDER
from .lexicon import Keyword, Lexicon, iter_keyword_hits
from .normalize import fold
from .rules import RuleEvaluation

BAND_LABELS = {
    "A": "高危",
    "B": "可疑",
    "C": "关注",
    "D": "低",
}

BAND_COLORS = {
    "A": "#c62828",
    "B": "#e65100",
    "C": "#b58900",
    "D": "#6b7280",
}


@dataclass
class Reason:
    label: str
    delta: float
    detail: str = ""

    def format(self) -> str:
        sign = "+" if self.delta >= 0 else "−"
        value = abs(self.delta)
        text = f"{self.label} {sign}{value:.0f}"
        if self.detail:
            text += f"（{self.detail}）"
        return text


@dataclass
class KeywordHit:
    keyword: Keyword
    start: int
    end: int
    distance: int

    @property
    def token(self) -> str:
        return self.keyword.token


@dataclass
class KeywordAnalysis:
    group_hits: list[KeywordHit] = field(default_factory=list)
    ad_hits: list[KeywordHit] = field(default_factory=list)
    best_group: KeywordHit | None = None
    group_strength: float = 0.0
    ad_strength: float = 0.0
    has_group_evidence: bool = False

    @property
    def group_tokens(self) -> list[str]:
        seen: list[str] = []
        for hit in sorted(self.group_hits, key=lambda h: h.distance):
            if hit.token not in seen:
                seen.append(hit.token)
        return seen

    @property
    def ad_tokens(self) -> list[str]:
        seen: list[str] = []
        for hit in sorted(self.ad_hits, key=lambda h: h.distance):
            if hit.token not in seen:
                seen.append(hit.token)
        return seen


@dataclass
class ScoreResult:
    score: int
    band: str
    reasons: list[Reason] = field(default_factory=list)

    @property
    def band_label(self) -> str:
        return BAND_LABELS.get(self.band, "")

    @property
    def band_text(self) -> str:
        return f"{self.band} {self.band_label}"


@dataclass
class ScoredCandidate:
    """最终输出的一条结果。"""

    candidate: Candidate
    analysis: KeywordAnalysis
    rules: RuleEvaluation
    score: int
    band: str
    reasons: list[Reason] = field(default_factory=list)
    plugin_notes: list[str] = field(default_factory=list)

    # ---- 代理属性 ----------------------------------------------------
    @property
    def band_label(self) -> str:
        return BAND_LABELS.get(self.band, "")

    @property
    def band_text(self) -> str:
        return f"{self.band} {self.band_label}"

    @property
    def digits(self) -> str:
        return self.candidate.digits

    @property
    def file(self) -> str:
        return self.candidate.file

    @property
    def line_no(self) -> int:
        return self.candidate.line_no

    @property
    def group_tokens(self) -> list[str]:
        return self.analysis.group_tokens

    @property
    def ad_tokens(self) -> list[str]:
        return self.analysis.ad_tokens

    @property
    def rule_labels(self) -> list[str]:
        return self.rules.labels

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.candidate.file, self.candidate.line_no, self.candidate.digits)


def _distance_to_span(start: int, end: int, span: tuple[int, int]) -> int:
    span_start, span_end = span
    if end < span_start:
        return span_start - end
    if start > span_end:
        return start - span_end
    return 0


def _proximity(distance: int, window: int) -> float:
    if distance <= 2:
        return 1.15
    if distance <= 6:
        return 1.0
    if distance <= 12:
        return 0.85
    if distance <= window:
        return 0.6
    return 0.0


def _length_factor(digits: int) -> float:
    if digits <= 4:
        return 0.15
    if digits == 5:
        return 0.55
    if digits == 6:
        return 0.8
    if 7 <= digits <= 10:
        return 1.0
    if digits <= 12:
        return 0.7
    if digits <= 14:
        return 0.45
    return 0.3


class Scorer:
    """关键词分析与打分。"""

    def __init__(self, config: Config, lexicon: Lexicon) -> None:
        self.config = config
        self.lexicon = lexicon

    # ------------------------------------------------------------------
    def analyze(self, candidate: Candidate) -> KeywordAnalysis:
        folded = fold(candidate.text)
        analysis = KeywordAnalysis()

        best_effective = 0.0
        for start, end, keyword in iter_keyword_hits(folded, self.lexicon.group_keywords):
            distance = _distance_to_span(start, end, candidate.span)
            hit = KeywordHit(keyword, start, end, distance)
            analysis.group_hits.append(hit)
            effective = keyword.weight * _proximity(distance, self.config.group_window)
            if effective > best_effective:
                best_effective = effective
                analysis.best_group = hit

        analysis.group_strength = min(1.5, best_effective)

        ad_weight = 0.0
        seen_ad: set[str] = set()
        for start, end, keyword in iter_keyword_hits(folded, self.lexicon.ad_keywords):
            distance = _distance_to_span(start, end, candidate.span)
            hit = KeywordHit(keyword, start, end, distance)
            analysis.ad_hits.append(hit)
            if distance > self.config.ad_window:
                continue
            if keyword.token in seen_ad:
                continue
            seen_ad.add(keyword.token)
            ad_weight += keyword.weight
        analysis.ad_strength = min(1.0, ad_weight / 2.5)

        analysis.has_group_evidence = any(
            hit.keyword.weight >= 0.7 and hit.distance <= 6 for hit in analysis.group_hits
        )
        return analysis

    # ------------------------------------------------------------------
    def score(
        self,
        candidate: Candidate,
        analysis: KeywordAnalysis,
        rules: RuleEvaluation,
        extra_reasons: list[Reason] | None = None,
    ) -> ScoreResult:
        weights = self.config.weights
        reasons: list[Reason] = []

        # 1. 号码长度
        length_points = weights["length"] * _length_factor(len(candidate.digits))
        reasons.append(
            Reason("号码长度", length_points, f"{len(candidate.digits)} 位")
        )

        # 2. 伪装程度
        obf_points = 0.0
        if candidate.obfuscation > 0:
            kinds = [k for k in OBFUSCATED_KIND_ORDER if candidate.kinds.get(k)]
            diversity = max(0, len(kinds) - 1)
            factor = min(1.0, candidate.obfuscation * 0.95 + 0.10 * diversity)
            obf_points = weights["obfuscation"] * factor
            reasons.append(
                Reason(
                    "伪装程度",
                    obf_points,
                    f"混淆度 {candidate.obfuscation:.2f}，{candidate.kind_summary}",
                )
            )

        # 3. 噪音/符号密度
        noise_points = 0.0
        if candidate.noise_count:
            density = candidate.noise_count / max(1, candidate.end - candidate.start)
            factor = min(1.0, density * 1.9)
            noise_points = weights["noise"] * factor
            reasons.append(
                Reason("噪音字符", noise_points, f"{candidate.noise_count} 个夹杂字符，密度 {density:.2f}")
            )

        # 4. 群关键词
        group_points = 0.0
        if analysis.best_group is not None and analysis.group_strength > 0:
            group_points = weights["group_keyword"] * analysis.group_strength
            distance = analysis.best_group.distance
            reasons.append(
                Reason(
                    "群关键词",
                    group_points,
                    f"「{analysis.best_group.token}」距离 {distance} 字",
                )
            )
            if distance <= 4 and 5 <= len(candidate.digits) <= 12:
                reasons.append(Reason("号码紧跟群关键词", 10.0, "典型广告句式"))

        # 5. 广告词
        ad_points = 0.0
        if analysis.ad_strength > 0:
            ad_points = weights["ad_keyword"] * analysis.ad_strength
            tokens = "、".join(analysis.ad_tokens[:6]) or "无"
            reasons.append(Reason("广告词", ad_points, tokens))

        # 6. 排版异常（大量符号、重复符号、emoji）
        structure_points = 0.0
        structure_factor, structure_detail = self._structure(candidate)
        if structure_factor > 0:
            structure_points = weights["structure"] * structure_factor
            reasons.append(Reason("排版异常", structure_points, structure_detail))

        # 7. 规则扣分
        for hit in rules.hits:
            if hit.action == "penalty" and hit.penalty:
                reasons.append(Reason(hit.label, -abs(hit.penalty), hit.detail))

        if extra_reasons:
            reasons.extend(extra_reasons)

        raw = sum(reason.delta for reason in reasons)
        score = int(max(0, min(100, round(raw))))
        return ScoreResult(score=score, band=self.band_for(score), reasons=reasons)

    # ------------------------------------------------------------------
    def band_for(self, score: int) -> str:
        thresholds = self.config.thresholds
        if score >= thresholds["high"]:
            return "A"
        if score >= thresholds["medium"]:
            return "B"
        if score >= thresholds["low"]:
            return "C"
        return "D"

    @staticmethod
    def _structure(candidate: Candidate) -> tuple[float, str]:
        text = candidate.text
        span = candidate.raw
        symbols = sum(1 for ch in span if not ch.isalnum() and not ch.isspace())
        symbol_ratio = symbols / max(1, len(span))

        runs = 0
        previous = ""
        repeat = 0
        for ch in text:
            if not ch.isalnum() and not ch.isspace() and ch == previous:
                repeat += 1
            else:
                if repeat >= 1:
                    runs += 1
                repeat = 0
            previous = ch
        if repeat >= 1:
            runs += 1

        emoji = sum(1 for ch in text if ord(ch) >= 0x1F300)
        factor = min(1.0, symbol_ratio * 1.5 + 0.06 * min(6, runs) + 0.05 * min(4, emoji))
        if factor <= 0:
            return 0.0, ""
        detail = f"符号占比 {symbol_ratio:.0%}"
        if runs:
            detail += f"，重复符号 {runs} 处"
        if emoji:
            detail += f"，表情 {emoji} 个"
        return factor, detail

    # ------------------------------------------------------------------
    @staticmethod
    def info_density(candidate: Candidate) -> float:
        """（备用）单位长度信息量，值越大越像随手涂的噪音。"""
        text = candidate.raw
        if not text:
            return 0.0
        unique = len(set(text))
        return unique / len(text) * math.log2(1 + len(text))
