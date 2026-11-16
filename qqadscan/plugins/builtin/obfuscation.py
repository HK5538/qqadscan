"""内置插件：多种伪装手法叠加。

单个同音字可能只是巧合，但同时用了符号 + 同音 + 拼音 + 噪音，就几乎可以确定是
故意在躲过滤。这个插件按「不同伪装类型数量」加分。
"""

from __future__ import annotations

from ..api import PluginBase, PluginContext, ScoreDelta

from ...core.decoder import OBFUSCATED_KIND_ORDER

KIND_LABELS = {
    "symbol": "符号",
    "shape": "形状",
    "homophone": "同音",
    "pinyin": "拼音",
    "radical": "偏旁",
    "confusable": "形近字母",
}


class ObfuscationPlugin(PluginBase):
    name = "obfuscation_diversity"
    version = "1.0.0"
    description = "同一号码叠加 3 种以上伪装手法时加分"
    author = "QQAdScan"

    def adjust_score(self, candidate, analysis, ctx: PluginContext):
        kinds = [kind for kind in OBFUSCATED_KIND_ORDER if candidate.kinds.get(kind)]
        if len(kinds) >= 3:
            names = "、".join(KIND_LABELS.get(kind, kind) for kind in kinds)
            return [ScoreDelta(6, "多种伪装叠加", f"同时使用 {len(kinds)} 种手法：{names}")]
        if len(kinds) == 2 and candidate.obfuscation >= 0.8:
            return [ScoreDelta(3, "伪装手法叠加", "两种手法且几乎没有直白数字")]
        if candidate.noise_count >= 4:
            return [ScoreDelta(3, "噪音填充", f"号码中间夹了 {candidate.noise_count} 个无用字符")]
        return []

#: 加载器会读取这个实例（也可以把类命名为 Plugin）
PLUGIN = ObfuscationPlugin()
