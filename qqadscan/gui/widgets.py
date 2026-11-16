"""自定义控件：详情面板、说明窗口。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.scorer import ScoredCandidate
from . import theme


class DetailView(ttk.Frame):
    """右侧/下方的详情面板，展示单条命中的全部依据。"""

    def __init__(self, master: tk.Misc, fonts: theme.Fonts) -> None:
        super().__init__(master, style="Panel.TFrame")
        self.fonts = fonts
        self.text = tk.Text(
            self,
            wrap="word",
            font=fonts.base,
            background=theme.PANEL_BG,
            foreground=theme.TEXT,
            relief="flat",
            borderwidth=0,
            padx=16,
            pady=12,
            spacing1=2,
            spacing3=4,
            cursor="arrow",
            height=14,
        )
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.text.tag_configure("title", font=fonts.title, foreground=theme.TEXT, spacing3=6)
        self.text.tag_configure("h2", font=fonts.h2, foreground=theme.TEXT, spacing1=10, spacing3=4)
        self.text.tag_configure("big", font=fonts.big, foreground=theme.ACCENT, spacing3=6)
        self.text.tag_configure("mono", font=fonts.mono)
        self.text.tag_configure("muted", foreground=theme.MUTED, font=fonts.small)
        self.text.tag_configure("hl", background=theme.HIGHLIGHT_BG)
        self.text.tag_configure("bandA", foreground="#b91c1c", font=fonts.bold)
        self.text.tag_configure("bandB", foreground="#c2410c", font=fonts.bold)
        self.text.tag_configure("bandC", foreground="#a16207", font=fonts.bold)
        self.text.tag_configure("bandD", foreground="#6b7280", font=fonts.bold)
        self.text.configure(state="disabled")
        self._empty()

    # ------------------------------------------------------------------
    def _reset(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")

    def _empty(self) -> None:
        self._reset()
        self.text.insert("end", "选中左侧任意一条结果，这里会显示：\n\n", "muted")
        self.text.insert("end", "· 解密出的群号\n· 原文（号码部分高亮）\n· 逐字解码过程\n· 每一分是怎么来的\n", "muted")
        self.text.configure(state="disabled")

    # ------------------------------------------------------------------
    def show(self, entry: ScoredCandidate) -> None:
        candidate = entry.candidate
        self._reset()

        self.text.insert("end", f"分数 {entry.score}  ", "title")
        self.text.insert("end", f"{entry.band_text}\n", f"band{entry.band}")
        self.text.insert("end", f"{candidate.file}  第 {candidate.line_no} 行\n", "muted")

        self.text.insert("end", "\n解密号码\n", "h2")
        self.text.insert("end", f"{candidate.digits}\n", "big")

        info = [f"{len(candidate.digits)} 位"]
        if candidate.numeric_value is not None:
            info.append(f"中文数字换算值 {candidate.numeric_value}")
        info.append(f"伪装：{candidate.kind_summary}")
        info.append(f"噪音 {candidate.noise_count} 个")
        self.text.insert("end", "  ·  ".join(info) + "\n", "muted")

        self.text.insert("end", "\n原文\n", "h2")
        self._insert_marked(candidate)
        self.text.insert("end", "\n")

        steps = candidate.decode_steps()
        if steps:
            self.text.insert("end", "\n解码过程\n", "h2")
            for step in steps:
                self.text.insert("end", "  " + step + "\n", "mono")

        self.text.insert("end", "\n评分明细\n", "h2")
        for reason in entry.reasons:
            sign = "+" if reason.delta >= 0 else "−"
            self.text.insert("end", f"  {reason.label} ", "mono")
            self.text.insert("end", f"{sign}{abs(reason.delta):.0f}", "mono")
            if reason.detail:
                self.text.insert("end", f"   {reason.detail}", "muted")
            self.text.insert("end", "\n")

        if entry.group_tokens or entry.ad_tokens or entry.rule_labels:
            self.text.insert("end", "\n命中\n", "h2")
            if entry.group_tokens:
                self.text.insert("end", "  群关键词：", "muted")
                self.text.insert("end", "、".join(entry.group_tokens) + "\n")
            if entry.ad_tokens:
                self.text.insert("end", "  广告词：", "muted")
                self.text.insert("end", "、".join(entry.ad_tokens[:12]) + "\n")
            if entry.rule_labels:
                self.text.insert("end", "  规则：", "muted")
                self.text.insert("end", "、".join(entry.rule_labels) + "\n")

        self.text.configure(state="disabled")
        self.text.yview_moveto(0)

    # ------------------------------------------------------------------
    def _insert_marked(self, candidate) -> None:
        start, end = candidate.span
        before = candidate.text[:start]
        marked = candidate.text[start:end]
        after = candidate.text[end:]
        indent = "  "
        self.text.insert("end", indent)
        if before:
            self.text.insert("end", before)
        self.text.insert("end", marked, "hl")
        if after:
            self.text.insert("end", after)
        self.text.insert("end", "\n")


class HelpWindow(tk.Toplevel):
    """评分说明窗口。"""

    CONTENT = """\
评分是怎么算出来的

一条命中的分数 = 各项信号相加，最后截断到 0-100：

  号码长度     5-12 位最像群号，7-10 位给满分；太长或太短都会减分
  伪装程度     用了多少种「不是数字的写法」，以及这些写法有多像数字
  噪音字符     号码中间夹了多少无意义字符（越多越可疑）
  群关键词     附近有没有「q群 / 群号 / 加群 / 裙 / 羣」这类词，以及离得多近
  广告词       「免费 / 福利 / 资源 / 上车 / 私聊」这类话术
  排版异常     符号占比、重复符号、表情

插件还会补充：微信/扫码/外链、明确写着「群号：」、多种伪装叠加等。

分档
  A 高危  ≥ 75   基本可以确定是群广告，建议人工确认
  B 可疑  ≥ 50   有明显特征，可能是广告
  C 关注  ≥ 30   有部分特征，可能是误伤
  D 低    < 30   基本可以忽略

排除规则（可在 config.json 里逐项开关）
  · 纯阿拉伯数字：123456789 这种没有任何伪装的号码
  · 纯中文数字：一百二十三
  · 量词：10元、一百块、99折
  · 时间：下午一点、18:10:30
  · 日期：2026-11-17、11月17日
  · 电话：手机号 / 座机号
每一项都有三档：off 不启用 / smart 只有附近没有群关键词时才排除 / always 一律排除。

程序不会删除或修改任何被扫描的文件。
"""

    def __init__(self, master: tk.Misc, fonts: theme.Fonts) -> None:
        super().__init__(master)
        self.title("评分说明")
        self.geometry("720x620")
        self.minsize(520, 420)
        frame = ttk.Frame(self, style="Panel.TFrame")
        frame.pack(fill="both", expand=True)
        text = tk.Text(
            frame,
            wrap="word",
            font=fonts.base,
            background=theme.PANEL_BG,
            relief="flat",
            padx=18,
            pady=16,
            spacing1=2,
            spacing3=3,
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.insert("1.0", self.CONTENT)
        text.configure(state="disabled")
