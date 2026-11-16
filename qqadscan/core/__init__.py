"""核心引擎：词库、解码、规则、评分、扫描、报告。"""

from __future__ import annotations

from .decoder import Atom, Candidate, decode_line, decode_text
from .lexicon import DigitToken, Keyword, Lexicon
from .scanner import ScanOptions, ScanResult, Scanner, collect_files
from .scorer import KeywordAnalysis, Reason, ScoredCandidate, Scorer, ScoreResult
from .rules import RuleEngine, RuleEvaluation, RuleHit

__all__ = [
    "Atom",
    "Candidate",
    "decode_line",
    "decode_text",
    "DigitToken",
    "Keyword",
    "KeywordAnalysis",
    "Lexicon",
    "Reason",
    "RuleEngine",
    "RuleEvaluation",
    "RuleHit",
    "ScanOptions",
    "ScanResult",
    "Scanner",
    "ScoredCandidate",
    "Scorer",
    "ScoreResult",
    "collect_files",
]
