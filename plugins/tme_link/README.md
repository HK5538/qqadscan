# tme_link —— 外置插件示例

演示如何在不修改主程序的情况下：

- 往词库里补充群关键词（`on_lexicon_ready`）；
- 根据行内特征加分（`adjust_score`）。

启用/禁用：修改 `plugin.json` 的 `"enabled": true/false`，或者在 `config.json` 的
`plugins.disabled` 里写上 `"tme_link"`。

删掉整个目录也不会影响程序运行。
