"""解码器：把一行文本里的「伪装数字」还原成数字串。

处理流程：

1. 逐字符扫描，用词库做最长匹配，把字符转换成「数字原子」（Atom）；
2. 允许数字之间夹少量噪音字符（默认 3 个以内，且不能是句读符号）；
3. 把连续的原子合并成候选号码；
4. 纯中文数字的候选会按「一百二十三」的规则换算成真正的数值。

整个过程不修改原文，只记录位置，因此报告可以精确还原上下文。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .lexicon import PLAIN_KINDS, Lexicon
from .numerals import CN_NUMERAL_CHARS, cn_to_int

KIND_LABELS = {
    "ascii": "原样数字",
    "cjk": "中文数字",
    "cjk_formal": "大写中文数字",
    "homophone": "同音/谐音",
    "symbol": "圈号/符号",
    "shape": "形状相近",
    "pinyin": "拼音",
    "radical": "偏旁部首",
    "confusable": "形近字母",
}

OBFUSCATED_KIND_ORDER = ["symbol", "shape", "homophone", "pinyin", "radical", "confusable"]


@dataclass(frozen=True)
class Atom:
    """一个字符（或一串字符）被翻译成的一个数字。"""

    start: int
    end: int
    digit: int
    token: str
    kind: str
    weight: float = 1.0

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


@dataclass
class Candidate:
    """一个候选号码。"""

    text: str
    span: tuple[int, int]
    atoms: list[Atom]
    line_no: int = 0
    file: str = ""
    digits: str = ""
    numeric_value: int | None = None
    noise: list[tuple[int, str]] = field(default_factory=list)
    kinds: dict[str, int] = field(default_factory=dict)
    obfuscation: float = 0.0
    symbol_density: float = 0.0
    plain_ascii: bool = False
    plain_cjk: bool = False
    context_before: str = ""
    context_after: str = ""

    # ---- 展示辅助 ----------------------------------------------------
    @property
    def start(self) -> int:
        return self.span[0]

    @property
    def end(self) -> int:
        return self.span[1]

    @property
    def raw(self) -> str:
        return self.text[self.span[0] : self.span[1]]

    @property
    def length(self) -> int:
        return len(self.digits)

    @property
    def kind_summary(self) -> str:
        parts = []
        for kind in OBFUSCATED_KIND_ORDER:
            count = self.kinds.get(kind, 0)
            if count:
                parts.append(f"{KIND_LABELS.get(kind, kind)}×{count}")
        return "、".join(parts) if parts else "无（直白数字）"

    @property
    def noise_count(self) -> int:
        return len(self.noise)

    def marked(self, radius: int = 24, left: str = "⟦", right: str = "⟧") -> str:
        """带高亮标记的上下文片段。"""
        start = max(0, self.span[0] - radius)
        end = min(len(self.text), self.span[1] + radius)
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(self.text) else ""
        return (
            f"{prefix}{self.text[start:self.span[0]]}{left}"
            f"{self.text[self.span[0]:self.span[1]]}{right}"
            f"{self.text[self.span[1]:end]}{suffix}"
        )

    def decode_steps(self) -> list[str]:
        """逐段的解码说明，供报告与详情面板展示。"""
        steps: list[str] = []
        cursor = self.span[0]
        for atom in self.atoms:
            if atom.start > cursor:
                gap = self.text[cursor : atom.start]
                if gap.strip():
                    steps.append(f"「{gap}」→ 噪音，跳过")
            steps.append(f"「{atom.token}」→ {atom.digit}（{atom.kind_label}）")
            cursor = atom.end
        if cursor < self.span[1]:
            gap = self.text[cursor : self.span[1]]
            if gap.strip():
                steps.append(f"「{gap}」→ 噪音，跳过")
        return steps


def _tokenize(text: str, lexicon: Lexicon, noise_precedence: bool) -> list[Atom]:
    atoms: list[Atom] = []
    index = 0
    length = len(text)
    digits = lexicon.digits
    noise = lexicon.noise
    while index < length:
        char = text[index]
        if char.isascii() and char.isdigit():
            atoms.append(Atom(index, index + 1, int(char), char, "ascii", 1.0))
            index += 1
            continue
        if noise_precedence and char in noise:
            index += 1
            continue
        token = lexicon.digit_at(text, index) if digits else None
        if token is not None:
            atoms.append(
                Atom(index, index + len(token.token), token.digit, token.token, token.kind, token.weight)
            )
            index += len(token.token)
            continue
        index += 1
    return atoms


def _drop_orphan_confusables(atoms: list[Atom]) -> list[Atom]:
    """形近字母（l/O 等）只有在紧邻真实数字时才生效。"""
    if not atoms:
        return atoms
    kept: list[Atom] = []
    for atom in atoms:
        if atom.kind != "confusable":
            kept.append(atom)
            continue
        neighbour = False
        for other in atoms:
            if other is atom or other.kind == "confusable":
                continue
            gap = max(other.start - atom.end, atom.start - other.end, 0)
            if gap <= 2:
                neighbour = True
                break
        if neighbour:
            kept.append(atom)
    return kept


def _split_runs(
    atoms: list[Atom], text: str, max_gap: int, boundaries: set[str]
) -> list[list[Atom]]:
    if not atoms:
        return []
    runs: list[list[Atom]] = []
    current: list[Atom] = [atoms[0]]
    for previous, atom in zip(atoms, atoms[1:]):
        gap = text[previous.end : atom.start]
        joinable = len(gap) <= max_gap and not any(ch in boundaries for ch in gap)
        # 低可信度的汉字类伪装（比如「司机」的司）不允许跨过多个字符粘到号码上，
        # 否则「…765 老司机」会把「司」当成 4 拼出错误的号码。
        # 圈号/符号类不受限制：⑨、４ 这类符号本身就是明确的数字。
        if (
            joinable
            and len(gap) > 1
            and atom.kind in {"homophone", "radical", "pinyin", "shape"}
            and atom.weight < 0.8
        ):
            joinable = False
        if joinable:
            current.append(atom)
        else:
            runs.append(current)
            current = [atom]
    runs.append(current)
    return runs


def _build_candidate(
    run: list[Atom],
    text: str,
    line_no: int,
    file: str,
    place_value: bool,
) -> Candidate | None:
    span = (run[0].start, run[-1].end)
    covered = [False] * (span[1] - span[0])
    for atom in run:
        for index in range(atom.start - span[0], atom.end - span[0]):
            if 0 <= index < len(covered):
                covered[index] = True

    noise: list[tuple[int, str]] = []
    for offset, is_covered in enumerate(covered):
        if is_covered:
            continue
        char = text[span[0] + offset]
        if char.strip():
            noise.append((span[0] + offset, char))

    kinds: dict[str, int] = {}
    for atom in run:
        kinds[atom.kind] = kinds.get(atom.kind, 0) + 1

    total_weight = sum(atom.weight for atom in run if atom.kind not in PLAIN_KINDS)
    obfuscation = min(1.0, total_weight / max(1, len(run)))
    span_len = max(1, span[1] - span[0])
    # 号码范围内非数字字符的占比（空格不算）
    symbol_density = min(1.0, len(noise) / span_len)

    plain_ascii = all(atom.kind == "ascii" for atom in run)
    plain_cjk = all(atom.kind in {"cjk", "cjk_formal"} for atom in run)

    digits = "".join(str(atom.digit) for atom in run)
    numeric_value: int | None = None
    if plain_cjk and place_value:
        token_text = "".join(atom.token for atom in run)
        if all(ch in CN_NUMERAL_CHARS for ch in token_text):
            value = cn_to_int(token_text)
            if value is not None:
                numeric_value = value
                digits = str(value)

    return Candidate(
        text=text,
        span=span,
        atoms=list(run),
        line_no=line_no,
        file=file,
        digits=digits,
        numeric_value=numeric_value,
        noise=noise,
        kinds=kinds,
        obfuscation=obfuscation,
        symbol_density=symbol_density,
        plain_ascii=plain_ascii,
        plain_cjk=plain_cjk,
        context_before=text[max(0, span[0] - 16) : span[0]],
        context_after=text[span[1] : span[1] + 16],
    )


def decode_line(
    text: str,
    lexicon: Lexicon,
    *,
    min_digits: int = 5,
    max_digits: int = 14,
    max_gap: int = 3,
    boundaries: Iterable[str] = "。！？；;!?\n",
    noise_precedence: bool = True,
    place_value: bool = True,
    line_no: int = 0,
    file: str = "",
) -> list[Candidate]:
    """解码一行文本，返回所有候选号码。"""
    if not text:
        return []
    atoms = _tokenize(text, lexicon, noise_precedence)
    if not atoms:
        return []
    atoms = _drop_orphan_confusables(atoms)
    boundary_set = set(boundaries) | {"\n", "\r"}
    runs = _split_runs(atoms, text, max_gap, boundary_set)

    candidates: list[Candidate] = []
    for run in runs:
        if len(run) < max(2, min_digits):
            continue
        candidate = _build_candidate(run, text, line_no, file, place_value)
        if candidate is None:
            continue
        if not (min_digits <= len(candidate.digits) <= max_digits):
            continue
        candidates.append(candidate)
    return candidates


def decode_text(
    text: str,
    lexicon: Lexicon,
    **kwargs,
) -> list[Candidate]:
    """解码多行文本（保持全局行号）。"""
    result: list[Candidate] = []
    for index, line in enumerate(text.splitlines(), 1):
        result.extend(decode_line(line, lexicon, line_no=index, **kwargs))
    return result
