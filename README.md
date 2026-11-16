# QQ群广告扫描器（QQAdScan）

在 txt 里找出**用同音字、谐音、拼音、圈号符号、形近符号、偏旁部首伪装的 QQ 群号**，
逐条还原号码、给出 0–100 的「疑似广告」评分，由你自己决定删哪几条。

**程序只读**：不删除、不修改、不移动任何被扫描的文件，只负责找出来和排序。

```
原文：㈡〔〔氿▲4⊥〖婈４□（叁5〓>⒍思蒐←索≌q羣：
还原：29443564        评分：96 / A 高危
依据：圈号/符号×3 + 同音字×2 + 10 个噪音字符 + 「q群」距离 4 字
```

---

## 目录

- [它认得出哪些伪装](#它认得出哪些伪装)
- [快速开始](#快速开始)
- [界面](#界面)
- [评分是怎么来的](#评分是怎么来的)
- [排除规则：别把价格和时间当广告](#排除规则别把价格和时间当广告)
- [改词库：加一个映射 / 删一个映射](#改词库加一个映射--删一个映射)
- [插件](#插件)
- [命令行](#命令行)
- [配置文件](#配置文件)
- [报告](#报告)
- [打包成 exe](#打包成-exe)
- [目录结构](#目录结构)
- [开发与测试](#开发与测试)
- [边界与已知限制](#边界与已知限制)
- [许可证](#许可证)

---

## 它认得出哪些伪装

| 类型 | 例子 | 词库文件 |
| --- | --- | --- |
| 同音 / 谐音汉字 | `氿`→9、`久`→9、`寺`→4、`舞`→5、`溜`→6 | `10_digits_homophone.tsv` |
| 中文数字 / 大写 | `三`→3、`叁`→3、`玖`→9、`两`→2 | `00_digits_base.tsv` |
| 中文数字换算 | `二十五`→25、`一百二十三`→123、`二〇二六`→2026 | 内置算法 |
| 圈号 / 括号号 | `①⑨`、`㈠㈡`、`⑴`、`❶`、`➀`、`㊈`、`⓵` | `20_digits_symbol.tsv` |
| 全角 / 上下标 / 罗马 | `９`、`⁴`、`₀`、`Ⅸ`、`ⅷ`、`0️⃣` | `20_digits_symbol.tsv` |
| 形状相近符号 | `∈`→3、`亖`→4、`丨`→1、`乙`→2、`○`→0 | `30_digits_shape.tsv` |
| 拼音 | `jiu`、`jiǔ`、`jiu3`、`wu`、`liang`、`yao` | `40_digits_pinyin.tsv` |
| 偏旁部首 | `衤`→1（yī）、`阝`→2（ěr）、`彡`→3（shān）、`纟`→4（sī） | `50_digits_radical.tsv` |
| 噪音字符 | `〔 〕 〖 〗 〓 ▲ ★ ✦ 🔥` 以及生僻字 | `60_noise.tsv` |
| 群关键词变体 | `q群`、`q羣`、`扣扣群`、`裙`、`君羊`、`QUN`、`q-u-n` | `70_group_keywords.tsv` |

一个号码中间最多允许夹 3 个噪音字符（可配置），所以这种写法也能连起来：

```
⑧ 〔 ⑦ ▲ ② 〖 ③ ① ⑨      ->  872319
```

同音字只在「像数字」时才拼进号码：`…765 老司机` 不会把「司」当成 4 拼成 10 位，
因为可信度低的汉字不允许跨过多个字符去粘号码（这条规则可在代码/词库里调）。

---

## 快速开始

### 方式一：直接用打包好的 exe

```bat
tools\build_exe.bat
```

打包完成后：

```
dist\QQ群广告扫描器\QQ群广告扫描器.exe      ← 双击运行，图形界面
dist\QQ群广告扫描器-CLI\qqadscan-cli.exe    ← 命令行版
```

`lexicon\`、`config.json` 就在 exe 旁边，随时可以改。

> 仓库的 GitHub Actions 也会在打 tag 时自动构建 exe，见 `.github/workflows/build.yml`。

### 方式二：源码运行

需要 **Python 3.9+**，并且带 tkinter（Windows 官方安装包默认包含）。

```bat
:: 双击
启动程序.bat

:: 或者手动
python -m qqadscan
```

命令行扫描：

```bat
python -m qqadscan scan D:\logs\chat.txt
python -m qqadscan scan D:\logs --min-score 50 --formats txt,csv
```

程序没有任何第三方依赖。

---

## 界面

- 顶部选择文件/文件夹（可以一次选多个，用 `;` 分隔），点「开始扫描」；
- 中间表格按分数从高到低排列，显示解密号码、群关键词、文件、行号、原文片段；
- 下方详情面板给出：解密号码、原文（号码高亮）、**逐字解码过程**、**每一分是怎么加的**；
- 「最低分数 / 等级 / 只看有群关键词的 / 搜索」四个筛选可以随意组合；
- 选中一行右键：复制原文、复制号码、复制「文件:行号」、在资源管理器中定位；
- 「导出当前结果」会把当前筛选后的条目写成 txt / csv / json 三种报告。

快捷键：`Ctrl+O` 选文件、`Ctrl+Shift+O` 选文件夹、`Ctrl+E` 导出、`F5` 重新载入配置与词库、`Esc` 取消扫描。

---

## 评分是怎么来的

分数是各项信号相加后截断到 0–100，每一项都会写进报告和详情面板：

| 信号 | 权重 | 说明 |
| --- | --- | --- |
| 号码长度 | 22 | 5–12 位最像群号，7–10 位给满分 |
| 伪装程度 | 26 | 用了几种非数字写法、每种有多像，权重来自词库 |
| 噪音字符 | 8 | 号码中间夹了多少无意义字符 |
| 群关键词 | 32 | 附近有没有 `q群 / 群号 / 加群 / 裙`，按距离衰减；紧跟号码再 +10 |
| 广告词 | 14 | `免费 / 福利 / 资源 / 上车 / 私聊` 等话术 |
| 排版异常 | 8 | 符号占比、重复符号、表情 |
| 插件 | 可变 | 微信/扫码/外链、明确写「群号：」、多种伪装叠加等 |

分档：

| 等级 | 分数 | 含义 |
| --- | --- | --- |
| A 高危 | ≥ 75 | 基本可以确定是群广告，建议人工确认 |
| B 可疑 | ≥ 50 | 有明显广告特征 |
| C 关注 | ≥ 30 | 有部分特征，可能是误伤 |
| D 低 | < 30 | 基本可以忽略 |

阈值都可以在设置里改。**分数只是排序建议，程序不会替你删任何东西。**

---

## 排除规则：别把价格和时间当广告

| 规则 | 效果 | 默认 |
| --- | --- | --- |
| 纯阿拉伯数字 | `123456789` 这种毫无伪装的号码 | 智能 |
| 纯中文数字 | `一百二十三` | 智能 |
| 量词 / 价格 | `10元`、`一百块`、`99折`、`￥2999` | 智能 |
| 时间 | `下午一点`、`18:10`、`18:10:30` | 智能 |
| 日期 | `2026-11-17`、`11月17日`、`2026年` | 智能 |
| 电话 | 手机号、座机号 | 智能 |

每档有三种取值：

- `off` —— 不启用；
- `smart` —— **只有号码附近没有群关键词时才排除**（推荐，误伤最少）；
- `always` —— 一律排除。

所以 `群号：123456789` 会被保留并评分，而正文里随便一串 `938271645` 会被安静地丢掉。

---

## 改词库：加一个映射 / 删一个映射

词库是 `lexicon/` 下的 UTF-8 TSV 文件，用记事本 / VS Code 直接改，保存后点「重新载入配置与词库」。

格式（6 列，Tab 分隔）：

```
token	category	value	kind	weight	note
氿	digit	9	homophone	0.85	jiǔ，生僻异体
q群	group_keyword			1.00	最直接的群关键词
元	quantifier			1.00	价格单位
```

- `category`：`digit` / `noise` / `group_keyword` / `ad_keyword` / `quantifier` / `time_word`
- `kind`（仅 digit）：`ascii` `cjk` `cjk_formal` `homophone` `symbol` `shape` `pinyin` `radical`
- `weight`：0–2，参与「伪装程度」计算；1.0 表示「几乎肯定」，0.4 表示「只是有点像」

**加一条映射**：新建 `lexicon/99_my.tsv`（文件名排序靠后，优先级更高）：

```
token	category	value	kind	weight	note
㊫	digit	7	symbol	0.9	自己遇到的写法
氿氿	digit	9	homophone	0.8	多字符也支持
```

**删一条映射**：在任意词库文件里加一行 `!要删的词`：

```
!思	digit
```

**改权重**：直接改第 5 列，或在新文件里重新写一遍同名词条（后加载的覆盖前面的）。

> 详细说明和更多例子见 [docs/词典编辑指南.md](docs/词典编辑指南.md)。

---

## 插件

插件放在程序目录的 `plugins/` 下，新增一个目录 + `plugin.json` + `plugin.py` 即可，**不用改主程序**。

```
plugins/
  my_rule/
    plugin.json
    plugin.py
```

```json
{ "name": "my_rule", "version": "1.0", "entry": "plugin.py", "class": "MyPlugin", "enabled": true }
```

```python
from qqadscan.plugins.api import PluginBase, ScoreDelta

class MyPlugin(PluginBase):
    name = "my_rule"
    version = "1.0"
    description = "出现「上车」时加分"

    def adjust_score(self, candidate, analysis, ctx):
        if "上车" in candidate.text:
            return [ScoreDelta(6, "上车暗语", "常见引流黑话")]
        return []

PLUGIN = MyPlugin()
```

可用钩子：`setup` / `on_lexicon_ready`（可往词库里加映射）/ `before_line` / `after_decode` /
`adjust_score` / `teardown`。插件异常会被单独捕获，不会影响其它插件或整次扫描。

仓库自带 3 个内置插件作为例子：`contact_signals`、`group_context`、`obfuscation_diversity`；
`plugins/tme_link/` 是一个可直接启用的外置示例。

> 完整 API 见 [docs/插件开发指南.md](docs/插件开发指南.md)。

---

## 命令行

```bat
:: 扫描（默认生成 txt + csv + json 三份报告）
python -m qqadscan scan D:\logs

:: 只要 50 分以上，只出 txt
python -m qqadscan scan chat.txt --min-score 50 --formats txt

:: 不递归、不用插件
python -m qqadscan scan D:\logs --no-recursive --no-plugins

:: 解码一行看看效果
python -m qqadscan decode "㈡〔〔氿▲4⊥〖婈４□（叁5〓>⒍思蒐←索≌q羣："

:: 查看词库统计
python -m qqadscan lexicon --dump
```

`--help` 可以看全部参数。

---

## 配置文件

`config.json` 与程序放在一起，缺字段会按默认值补齐，升级不会覆盖你的设置。

| 段 | 关键项 |
| --- | --- |
| `scan` | 扩展名、是否递归、单文件大小上限、编码尝试顺序 |
| `decode` | 最短/最长号码位数、允许间隔字符数、噪音优先级、中文数字换算 |
| `rules` | 6 条排除规则的 `off/smart/always` |
| `score` | 三档阈值、关键词窗口、各项权重 |
| `output` | 报告目录、格式、是否包含 D 级 |
| `plugins` | 总开关、按名字禁用 |
| `ui` | 最低分数、默认等级、最多显示行数、字号 |

改坏了也不要紧：删掉 `config.json`，程序会用内置默认值重新生成。

---

## 报告

| 格式 | 用途 |
| --- | --- |
| `扫描报告_YYYYMMDD_HHMMSS.txt` | 人看：分组清晰，含解码过程与评分明细 |
| `...csv` | Excel 打开（带 BOM，不会乱码），一行一条 |
| `...json` | 程序读：包含每个原子的位置、类型、权重 |

报告默认写到 `reports/`，不会碰到被扫描的原始文件。

---

## 打包成 exe

```bat
tools\build_exe.bat
```

脚本会先 `pip install pyinstaller`，再按 `qqadscan.spec` 打包出图形版和命令行版。
词库、配置、插件会一起复制到 `dist\QQ群广告扫描器\`，可以直接改。

如果打包后想换图标，把 `.ico` 放到 `assets/app.ico`，在 `qqadscan.spec` 的 `EXE(...)` 里加 `icon="assets/app.ico"`。

---

## 目录结构

```
qqadscan/                 程序主体（纯标准库）
  core/                   词库、解码、规则、评分、扫描、报告
  gui/                    tkinter 界面
  plugins/                插件 API、加载器、内置插件
lexicon/                  可编辑词库（11 个 TSV）
plugins/tme_link/         外置插件示例
samples/demo.txt          演示样本（含正常聊天、价格、时间、各种伪装广告）
tests/test_core.py        31 个单元测试
tools/                    符号词库生成器、打包脚本
config.json               配置
启动程序.bat               双击启动图形界面
命令行扫描.bat             拖文件进去就能扫
```

---

## 开发与测试

```bat
python -m unittest discover -s tests -v
```

测试覆盖：中文数字换算、符号/同音/拼音解码、词库覆盖与删除、六条排除规则、
评分分档、插件加载与隔离、编码回退（GBK 文件）、报告导出。

代码风格：标准库优先、类型标注、每个模块一个职责。

---

## 同步到 GitHub

这个目录已经是一个提交好的 git 仓库（分支 `main`），推送只差一个远程地址：

1. 打开 <https://github.com/new> 新建一个**空仓库**（不要勾选 README / .gitignore），
   例如叫 `qqadscan`；
2. 双击 **`同步到GitHub.bat`**，粘贴仓库地址（如
   `https://github.com/你的用户名/qqadscan.git`），按提示登录；
3. 完成后 GitHub Actions 会自动跑测试，打 `v1.0.0` 标签还会自动构建 exe 并发布 Release。

手动推送：

```bat
git remote add origin https://github.com/你的用户名/qqadscan.git
git branch -M main
git push -u origin main
```

---

## 边界与已知限制

- 只处理**纯文本**，图片/二维码/压缩包里的群号识别不了；
- 词库是「经验规则」，不可能 100%，冷门写法需要自己加词条；
- 同音字太激进会误伤正常中文，所以权重分档 + 最少 5 位 + 群关键词证据三重限制；
- 群号长度按 5–14 位处理，超长数字串（订单号、时间戳）默认不报；
- 扫描大文件时界面会持续显示进度，可随时取消。

---

## 许可证

MIT，见 [LICENSE](LICENSE)。

程序不联网、不上传任何内容，所有判断都在本机完成。
