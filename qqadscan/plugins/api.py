"""插件 API。

写一个插件只需要三步：

1. 在 ``plugins/`` 下建一个目录，例如 ``plugins/my_rule/``；
2. 放一个 ``plugin.py``，里面写一个继承 :class:`PluginBase` 的类；
3. 放一个 ``plugin.json`` 清单（name / entry / class / enabled）。

最小示例::

    from qqadscan.plugins.api import PluginBase, ScoreDelta

    class MyPlugin(PluginBase):
        name = "my_rule"
        version = "1.0"
        description = "示例：出现「上车」时加分"

        def adjust_score(self, candidate, analysis, ctx):
            if "上车" in candidate.text:
                return [ScoreDelta(6, "上车暗语", "常见引流黑话")]
            return []

钩子一览（都返回 ``None`` 表示不做处理）：

``setup(ctx)``
    插件载入时调用一次，可做初始化。
``on_lexicon_ready(ctx)``
    词库加载完成后调用，可在这里往词库里加映射/关键词。
``before_line(line, ctx)``
    每行解码前调用，返回新的行文本；返回 ``None`` 跳过该行。
``after_decode(candidates, ctx)``
    解码完成后调用，可读取/标记候选。
``adjust_score(candidate, analysis, ctx)``
    返回 ``ScoreDelta`` 列表，分数会在核心评分之后叠加。
``teardown(ctx)``
    扫描结束时调用。

插件抛出的异常会被单独捕获并记录，不会影响其它插件或整次扫描。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..config import Config
from ..core.decoder import Candidate
from ..core.lexicon import Lexicon
from ..core.scorer import KeywordAnalysis

API_VERSION = "1"


@dataclass
class ScoreDelta:
    """插件对分数的调整。"""

    delta: float
    label: str
    detail: str = ""


@dataclass
class PluginContext:
    """插件可访问的运行时上下文。"""

    config: Config
    lexicon: Lexicon
    root: Path
    logger: logging.Logger
    report_notes: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def note(self, text: str) -> None:
        """往报告头部加一行说明。"""
        if text and text not in self.report_notes:
            self.report_notes.append(text)


class PluginBase:
    """所有插件的基类。"""

    api_version = API_VERSION
    name = "unnamed"
    version = "1.0.0"
    description = ""
    author = ""
    enabled = True

    def setup(self, ctx: PluginContext) -> None:  # noqa: D401
        """插件载入时调用。"""

    def on_lexicon_ready(self, ctx: PluginContext) -> None:
        """词库就绪时调用，可扩充词库。"""

    def before_line(self, line: str, ctx: PluginContext) -> str | None:
        """逐行预处理，返回新文本或 None（跳过）。"""
        return line

    def after_decode(self, candidates: list[Candidate], ctx: PluginContext) -> None:
        """解码完成后的回调。"""

    def adjust_score(
        self, candidate: Candidate, analysis: KeywordAnalysis, ctx: PluginContext
    ) -> Iterable[ScoreDelta] | None:
        """按需加分/减分。"""
        return None

    def teardown(self, ctx: PluginContext) -> None:
        """扫描结束时调用。"""

    # ---- 辅助 --------------------------------------------------------
    def describe(self) -> str:
        text = f"{self.name} v{self.version}"
        if self.description:
            text += f" — {self.description}"
        return text
