"""内置插件：联系方式 / 引流信号。

广告除了群号，通常还会附带「加微信」「扫码」「看主页」之类的引导语。
只要这些词出现在号码附近，就额外加分。
"""

from __future__ import annotations

import re

from ..api import PluginBase, PluginContext, ScoreDelta

PATTERNS = (
    (re.compile(r"微信|威信|薇信|v信|vx|weixin|加我|私聊|私信", re.IGNORECASE), 7.0, "微信/私聊引导"),
    (re.compile(r"扫码|二维码|长按|识别|关注公众号|主页|评论区", re.IGNORECASE), 6.0, "扫码/主页引导"),
    (re.compile(r"https?://|t\.me/|t\.cn/|\.com|\.cn|\.net", re.IGNORECASE), 5.0, "外链"),
    (re.compile(r"客服|秒回|全天在线|24小时|人工", re.IGNORECASE), 5.0, "客服话术"),
)


class ContactSignalsPlugin(PluginBase):
    name = "contact_signals"
    version = "1.0.0"
    description = "号码附近出现微信/扫码/外链/客服话术时加分"
    author = "QQAdScan"

    def adjust_score(self, candidate, analysis, ctx: PluginContext):
        window = 40
        start = max(0, candidate.start - window)
        end = min(len(candidate.text), candidate.end + window)
        near = candidate.text[start:end]
        deltas: list[ScoreDelta] = []
        for pattern, points, label in PATTERNS:
            match = pattern.search(near)
            if match:
                deltas.append(ScoreDelta(points, label, f"附近出现「{match.group(0)}」"))
        return deltas

#: 加载器会读取这个实例（也可以把类命名为 Plugin）
PLUGIN = ContactSignalsPlugin()
