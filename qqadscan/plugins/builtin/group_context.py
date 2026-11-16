"""内置插件：「群号：xxxx」这类明确标注。

核心评分只看「附近有没有群关键词」，这个插件进一步识别「群号/群号码/群ID」
这种直接标注的句式，并检查号码是不是被括号、方框包起来——这是广告里最常见的写法。
"""

from __future__ import annotations

import re

from ..api import PluginBase, PluginContext, ScoreDelta

LABEL_PATTERN = re.compile(
    r"(?:群号|群号码|群\s*id|qq群号|扣扣群号|裙号|群聊号)\s*(?:是|为|:|：)?\s*$",
    re.IGNORECASE,
)

BRACKETS = (
    ("(", ")"),
    ("（", "）"),
    ("[", "]"),
    ("【", "】"),
    ("〔", "〕"),
    ("〖", "〗"),
    ("{", "}"),
    ("<", ">"),
    ("「", "」"),
    ("《", "》"),
)


class GroupContextPlugin(PluginBase):
    name = "group_context"
    version = "1.0.0"
    description = "识别「群号：」明确标注与括号包裹的号码"
    author = "QQAdScan"

    def adjust_score(self, candidate, analysis, ctx: PluginContext):
        deltas: list[ScoreDelta] = []
        head = candidate.text[max(0, candidate.start - 14) : candidate.start]
        if LABEL_PATTERN.search(head):
            deltas.append(ScoreDelta(8, "明确标注群号", "号码前面直接写着「群号」"))

        before = candidate.text[candidate.start - 1] if candidate.start > 0 else ""
        after = candidate.text[candidate.end] if candidate.end < len(candidate.text) else ""
        for left, right in BRACKETS:
            if before == left or after == right:
                deltas.append(ScoreDelta(4, "括号包裹", f"号码被 {before}{after} 包起来"))
                break

        if 9 <= len(candidate.digits) <= 11 and candidate.plain_ascii:
            deltas.append(ScoreDelta(3, "QQ号长度", "9-11 位纯数字，符合 QQ 号特征"))
        return deltas

#: 加载器会读取这个实例（也可以把类命名为 Plugin）
PLUGIN = GroupContextPlugin()
