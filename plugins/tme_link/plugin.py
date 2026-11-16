"""外置插件示例：Telegram / 电报 / 纸飞机 引流。

它演示了两件事：

1. ``on_lexicon_ready`` 里往词库补充群关键词，不用改主程序的 TSV；
2. ``adjust_score`` 里根据行内特征加分。

把 ``plugin.json`` 里的 ``enabled`` 改成 ``false`` 即可关闭。
"""

from __future__ import annotations

import re

from qqadscan.plugins.api import PluginBase, PluginContext, ScoreDelta

LINK_PATTERN = re.compile(r"(?:t\.me/|telegram\.me/|tg://)", re.IGNORECASE)
WORD_PATTERN = re.compile(r"电报|纸飞机|飞机群|telegram|tg群", re.IGNORECASE)


class TelegramLinkPlugin(PluginBase):
    name = "tme_link"
    version = "1.0.0"
    description = "识别 Telegram 引流（示例插件）"
    author = "QQAdScan"

    def on_lexicon_ready(self, ctx: PluginContext) -> None:
        # 补充主词库没有的写法，权重 0.9 表示「基本可以确定」
        for token in ("飞机群", "电报群", "tg群", "纸飞机群"):
            ctx.lexicon.add_keyword(token, 0.9, note="由 tme_link 插件注册")
        ctx.note("已启用 tme_link 插件：Telegram 引流会额外加分")

    def adjust_score(self, candidate, analysis, ctx: PluginContext):
        text = candidate.text
        deltas: list[ScoreDelta] = []
        if LINK_PATTERN.search(text):
            deltas.append(ScoreDelta(9, "Telegram 链接", "出现 t.me / telegram.me 链接"))
        elif WORD_PATTERN.search(text):
            deltas.append(ScoreDelta(6, "Telegram 引流话术", "出现电报/纸飞机等字样"))
        return deltas
