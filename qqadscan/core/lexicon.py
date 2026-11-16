"""词库：加载、合并、查询。

词库全部是 UTF-8 的 TSV 文件，放在 ``lexicon/`` 目录下，按文件名排序加载，
后加载的会覆盖先加载的同名条目。每行 6 列：

    token <TAB> category <TAB> value <TAB> kind <TAB> weight <TAB> note

* ``token``    要识别的字符串（可以是多字符，如拼音 ``jiu``）
* ``category`` ``digit`` / ``noise`` / ``group_keyword`` / ``ad_keyword`` /
               ``quantifier`` / ``time_word``
* ``value``    ``digit`` 类别时填 0-9，其它类别留空
* ``kind``     ``digit`` 类别时的伪装类型：
               ``ascii``（原样数字）、``cjk``（中文数字）、``cjk_formal``（大写中文数字）、
               ``homophone``（同音/谐音字）、``symbol``（①㈠⑨ 之类符号）、
               ``shape``（∈ 之类形状相近符号）、``pinyin``（拼音）、``radical``（偏旁部首）
* ``weight``   可信度 0-2，参与「混淆度」计算，默认 1.0
* ``note``     备注，仅用于展示

想删除某个映射，在任意词库文件里加一行：``!要删除的词<TAB>digit`` 即可。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from .normalize import fold

LOGGER = logging.getLogger(__name__)

DIGIT_KINDS = {
    "ascii",
    "cjk",
    "cjk_formal",
    "homophone",
    "symbol",
    "shape",
    "pinyin",
    "radical",
    "confusable",
}

#: 属于「伪装」的类型，参与混淆度计算
OBFUSCATED_KINDS = {"homophone", "symbol", "shape", "pinyin", "radical", "confusable"}

#: 属于「直白数字」的类型
PLAIN_KINDS = {"ascii", "cjk", "cjk_formal"}

CATEGORIES = {
    "digit",
    "noise",
    "group_keyword",
    "ad_keyword",
    "quantifier",
    "time_word",
}

#: 需要词边界（前后不是拉丁字母）的类别，避免 san 命中 sans 这类误伤
_WORD_BOUNDARY_KINDS = {"pinyin"}

#: 需要紧贴其它数字才生效的类别，避免 O/l 之类在普通英文里乱命中
_DIGIT_ADJACENT_KINDS = {"confusable"}

CATEGORY_LABELS = {
    "digit": "数字映射",
    "noise": "噪音字符",
    "group_keyword": "群关键词",
    "ad_keyword": "广告关键词",
    "quantifier": "量词",
    "time_word": "时间词",
}


@dataclass(frozen=True)
class DigitToken:
    """一条「字符 -> 数字」的映射。"""

    token: str
    digit: int
    kind: str = "homophone"
    weight: float = 1.0
    note: str = ""

    @property
    def is_obfuscated(self) -> bool:
        return self.kind in OBFUSCATED_KINDS

    @property
    def context(self) -> str:
        if self.kind in _WORD_BOUNDARY_KINDS:
            return "word"
        if self.kind in _DIGIT_ADJACENT_KINDS:
            return "digit_adjacent"
        return "any"


@dataclass(frozen=True)
class Keyword:
    """群关键词 / 广告关键词 / 量词。"""

    token: str
    weight: float = 1.0
    kind: str = "group"
    note: str = ""
    source: str = ""


@dataclass
class Lexicon:
    """内存中的词库。"""

    digits: dict[str, DigitToken] = field(default_factory=dict)
    noise: dict[str, float] = field(default_factory=dict)
    group_keywords: dict[str, Keyword] = field(default_factory=dict)
    ad_keywords: dict[str, Keyword] = field(default_factory=dict)
    quantifiers: dict[str, Keyword] = field(default_factory=dict)
    time_words: dict[str, Keyword] = field(default_factory=dict)
    boundaries: set[str] = field(default_factory=set)
    loaded_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    _max_token_len: int = 1

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @property
    def max_token_len(self) -> int:
        return self._max_token_len

    def _recalc_max_len(self) -> None:
        self._max_token_len = max((len(k) for k in self.digits), default=1)

    def digit_at(self, text: str, index: int) -> DigitToken | None:
        """从 ``index`` 开始做最长匹配，返回数字映射。"""
        remaining = len(text) - index
        if remaining <= 0:
            return None
        limit = min(self._max_token_len, remaining)
        for length in range(limit, 0, -1):
            chunk = text[index : index + length]
            token = self.digits.get(chunk)
            if token is None and chunk.lower() != chunk:
                token = self.digits.get(chunk.lower())
            if token is None:
                continue
            context = token.context
            if context == "word" and not self._word_boundary_ok(text, index, length):
                continue
            return token
        return None

    @staticmethod
    def _word_boundary_ok(text: str, index: int, length: int) -> bool:
        before = text[index - 1] if index > 0 else ""
        after_index = index + length
        after = text[after_index] if after_index < len(text) else ""
        for ch in (before, after):
            if ch and ch.isascii() and ch.isalpha():
                return False
        return True

    # ------------------------------------------------------------------
    # 修改
    # ------------------------------------------------------------------
    def add_digit(
        self,
        token: str,
        digit: int,
        kind: str = "homophone",
        weight: float = 1.0,
        note: str = "",
        source: str = "",
    ) -> None:
        token = (token or "").strip()
        if not token:
            return
        if not 0 <= int(digit) <= 9:
            self.warnings.append(f"{source}: 数字超出 0-9 范围，已忽略：{token}->{digit}")
            return
        if kind not in DIGIT_KINDS:
            self.warnings.append(f"{source}: 未知类型 {kind}，按 homophone 处理：{token}")
            kind = "homophone"
        weight = max(0.0, min(2.0, float(weight)))
        self.digits[token] = DigitToken(token, int(digit), kind, weight, note)
        if len(token) > self._max_token_len:
            self._max_token_len = len(token)

    def add_keyword(self, token: str, weight: float, note: str = "", source: str = "") -> None:
        token = (token or "").strip()
        if not token:
            return
        key = fold(token)
        self.group_keywords[key] = Keyword(
            token=token, weight=max(0.0, min(2.0, float(weight))), kind="group", note=note, source=source
        )

    def add_ad_keyword(self, token: str, weight: float, note: str = "", source: str = "") -> None:
        token = (token or "").strip()
        if not token:
            return
        key = fold(token)
        self.ad_keywords[key] = Keyword(
            token=token, weight=max(0.0, min(2.0, float(weight))), kind="ad", note=note, source=source
        )

    def add_noise(self, token: str, weight: float = 1.0) -> None:
        for ch in token:
            self.noise[ch] = weight

    def add_quantifier(self, token: str, weight: float = 1.0, note: str = "", source: str = "") -> None:
        token = (token or "").strip()
        if not token:
            return
        self.quantifiers[fold(token)] = Keyword(token, weight, "quantifier", note, source)

    def add_time_word(self, token: str, weight: float = 1.0, note: str = "", source: str = "") -> None:
        token = (token or "").strip()
        if not token:
            return
        self.time_words[fold(token)] = Keyword(token, weight, "time", note, source)

    def add_boundary(self, chars: str) -> None:
        for ch in chars:
            self.boundaries.add(ch)

    def remove(self, category: str, token: str) -> bool:
        key = fold(token)
        if category == "digit":
            return self.digits.pop(token, None) is not None
        if category == "noise":
            removed = False
            for ch in token:
                removed = self.noise.pop(ch, None) is not None or removed
            return removed
        mapping = {
            "group_keyword": self.group_keywords,
            "ad_keyword": self.ad_keywords,
            "quantifier": self.quantifiers,
            "time_word": self.time_words,
        }.get(category)
        if mapping is None:
            return False
        return mapping.pop(key, None) is not None

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------
    def merge_file(self, path: Path) -> int:
        """合并一个 TSV 词库文件，返回成功处理的条目数。"""
        try:
            raw = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            self.warnings.append(f"读取词库失败：{path}（{exc}）")
            return 0

        count = 0
        header_seen = False
        for lineno, line in enumerate(raw.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("\t")]
            if not header_seen and parts and parts[0].lower() == "token":
                header_seen = True
                continue
            if len(parts) < 2:
                self.warnings.append(f"{path.name}:{lineno} 列数不足，已跳过")
                continue

            token = parts[0].replace("\\t", "\t")
            category = parts[1].lower()
            value = parts[2] if len(parts) > 2 else ""
            kind = (parts[3] if len(parts) > 3 else "").lower()
            weight_raw = parts[4] if len(parts) > 4 else ""
            note = parts[5] if len(parts) > 5 else ""

            if category not in CATEGORIES:
                self.warnings.append(f"{path.name}:{lineno} 未知类别 {category}，已跳过")
                continue

            if token.startswith("!"):
                self.remove(category, token[1:])
                count += 1
                continue

            try:
                weight = float(weight_raw) if weight_raw else 1.0
            except ValueError:
                weight = 1.0

            source = f"{path.name}:{lineno}"
            if category == "digit":
                try:
                    digit = int(value)
                except ValueError:
                    self.warnings.append(f"{source} 数字值无效：{value}")
                    continue
                self.add_digit(token, digit, kind or "homophone", weight, note, source)
            elif category == "noise":
                self.add_noise(token, weight)
            elif category == "group_keyword":
                self.add_keyword(token, weight, note, source)
            elif category == "ad_keyword":
                self.add_ad_keyword(token, weight, note, source)
            elif category == "quantifier":
                self.add_quantifier(token, weight, note, source)
            elif category == "time_word":
                self.add_time_word(token, weight, note, source)
            count += 1

        self.loaded_files.append(str(path))
        return count

    def load_dir(self, directory: Path, extra_dirs: Iterable[Path] = ()) -> "Lexicon":
        """加载目录下所有 ``*.tsv`` / ``*.csv`` 文件（按文件名排序）。"""
        files: list[Path] = []
        for folder in (directory, *extra_dirs):
            if not folder or not folder.is_dir():
                continue
            for pattern in ("*.tsv", "*.csv"):
                files.extend(sorted(folder.glob(pattern)))
        # 去重并保持顺序
        seen: set[str] = set()
        unique: list[Path] = []
        for item in files:
            key = str(item.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)

        if not unique:
            self.warnings.append(f"词库目录为空：{directory}，已载入内置最小词表")
            self._load_minimum()
        for item in unique:
            self.merge_file(item)
        if not self.digits:
            self._load_minimum()
        return self

    def _load_minimum(self) -> None:
        """最小可用词表，保证即使词库丢失程序也能跑。"""
        for i in range(10):
            self.add_digit(str(i), i, "ascii", 1.0, "内置")
        for i, ch in enumerate("〇一二三四五六七八九"):
            self.add_digit(ch, i, "cjk", 1.0, "内置")
        for ch in "０１２３４５６７８９":
            self.add_digit(ch, int(ch.translate(str.maketrans("０１２３４５６７８９", "0123456789"))), "symbol", 0.5, "内置")
        for word in ("群", "q群", "qq群", "群号"):
            self.add_keyword(word, 0.9, "内置")
        self.add_boundary("。！？；;!?\n\r")

    # ------------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        return {
            "digit_mappings": len(self.digits),
            "noise_chars": len(self.noise),
            "group_keywords": len(self.group_keywords),
            "ad_keywords": len(self.ad_keywords),
            "quantifiers": len(self.quantifiers),
            "time_words": len(self.time_words),
            "files": len(self.loaded_files),
        }

    def describe(self) -> str:
        s = self.stats()
        return (
            f"数字映射 {s['digit_mappings']} 条 / 噪音 {s['noise_chars']} 个 / "
            f"群关键词 {s['group_keywords']} 个 / 广告词 {s['ad_keywords']} 个 / "
            f"量词 {s['quantifiers']} 个 / 词库文件 {s['files']} 个"
        )

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, directory: Path, extra_dirs: Iterable[Path] = ()) -> "Lexicon":
        return cls().load_dir(Path(directory), extra_dirs)


def iter_keyword_hits(text_folded: str, keywords: dict[str, Keyword]) -> Iterator[tuple[int, int, Keyword]]:
    """在折叠文本中查找所有关键词出现位置。"""
    if not text_folded or not keywords:
        return
    for key, keyword in keywords.items():
        if not key:
            continue
        start = text_folded.find(key)
        while start != -1:
            yield start, start + len(key), keyword
            start = text_folded.find(key, start + 1)
