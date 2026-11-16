"""设置窗口：常用选项的可视化编辑（写回 config.json）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from ..config import Config
from . import theme

RULE_LABELS = [
    ("pure_arabic", "纯阿拉伯数字", "123456789 这种没有任何伪装的号码"),
    ("pure_chinese", "纯中文数字", "一百二十三 这种全中文写法"),
    ("quantifier", "量词/价格", "10元、一百块、99折"),
    ("time", "时间", "下午一点、18:10:30"),
    ("date", "日期", "2026-11-17、11月17日"),
    ("phone", "电话号码", "手机号、座机号"),
]

MODE_VALUES = {"不启用": "off", "智能（推荐）": "smart", "一律排除": "always"}
MODE_LABELS = {value: label for label, value in MODE_VALUES.items()}


class SettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, config: Config, on_saved: Callable[[], None]) -> None:
        super().__init__(master)
        self.title("设置")
        self.transient(master)
        self.resizable(False, False)
        self.config_obj = config
        self.on_saved = on_saved
        self.vars: dict[str, tk.Variable] = {}

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        notebooks = {
            "rules": ttk.Frame(notebook, padding=12),
            "decode": ttk.Frame(notebook, padding=12),
            "score": ttk.Frame(notebook, padding=12),
            "scan": ttk.Frame(notebook, padding=12),
        }
        notebook.add(notebooks["rules"], text="排除规则")
        notebook.add(notebooks["decode"], text="解码")
        notebook.add(notebooks["score"], text="评分阈值")
        notebook.add(notebooks["scan"], text="扫描范围")

        self._build_rules(notebooks["rules"])
        self._build_decode(notebooks["decode"])
        self._build_score(notebooks["score"])
        self._build_scan(notebooks["scan"])

        footer = ttk.Frame(self, padding=(12, 6, 12, 12))
        footer.pack(fill="x")
        ttk.Label(
            footer,
            text="提示：也可以直接编辑 config.json，改完点「重新载入配置」。",
            style="Muted.TLabel",
        ).pack(side="left")
        ttk.Button(footer, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="保存", style="Accent.TButton", command=self._save).pack(side="right")

        self.update_idletasks()
        self._center(master)

    # ------------------------------------------------------------------
    def _center(self, master: tk.Misc) -> None:
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    def _build_rules(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="「智能」= 只有号码附近没有群关键词时才排除，误伤最少。",
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        for index, (key, title, hint) in enumerate(RULE_LABELS, start=1):
            ttk.Label(parent, text=title).grid(row=index, column=0, sticky="w", pady=4)
            variable = tk.StringVar(value=MODE_LABELS.get(str(self.config_obj.rule_mode(key)), "智能（推荐）"))
            combo = ttk.Combobox(
                parent,
                textvariable=variable,
                values=list(MODE_VALUES.keys()),
                state="readonly",
                width=14,
            )
            combo.grid(row=index, column=1, sticky="w", padx=12, pady=4)
            ttk.Label(parent, text=hint, style="Muted.TLabel").grid(row=index, column=2, sticky="w")
            self.vars[f"rules.{key}"] = variable

    def _build_decode(self, parent: ttk.Frame) -> None:
        rows = [
            ("decode.min_digits", "最短号码位数", 2, 20),
            ("decode.max_digits", "最长号码位数", 4, 40),
            ("decode.max_gap", "允许的数字间隔字符数", 0, 10),
        ]
        for index, (key, title, low, high) in enumerate(rows):
            ttk.Label(parent, text=title).grid(row=index, column=0, sticky="w", pady=8)
            section, name = key.split(".")
            value = int(self.config_obj.get(section, name, default=low))
            variable = tk.IntVar(value=value)
            ttk.Spinbox(parent, from_=low, to=high, textvariable=variable, width=8).grid(
                row=index, column=1, sticky="w", padx=12
            )
            self.vars[key] = variable
        ttk.Label(
            parent,
            text="间隔字符数越大，越能把夹了很多符号的号码连起来，但误连也更多。",
            style="Muted.TLabel",
            wraplength=420,
        ).grid(row=len(rows), column=0, columnspan=3, sticky="w", pady=(12, 0))

    def _build_score(self, parent: ttk.Frame) -> None:
        thresholds = self.config_obj.thresholds
        rows = [
            ("score.high", "A 高危阈值", thresholds["high"]),
            ("score.medium", "B 可疑阈值", thresholds["medium"]),
            ("score.low", "C 关注阈值", thresholds["low"]),
        ]
        for index, (key, title, value) in enumerate(rows):
            ttk.Label(parent, text=title).grid(row=index, column=0, sticky="w", pady=8)
            variable = tk.IntVar(value=value)
            ttk.Spinbox(parent, from_=0, to=100, textvariable=variable, width=8).grid(
                row=index, column=1, sticky="w", padx=12
            )
            self.vars[key] = variable
        ttk.Label(
            parent,
            text="阈值只影响分档显示，不改变分数本身。",
            style="Muted.TLabel",
        ).grid(row=len(rows), column=0, columnspan=3, sticky="w", pady=(12, 0))

    def _build_scan(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="扫描的文件扩展名（逗号分隔）").grid(row=0, column=0, sticky="w", pady=8)
        extensions = ", ".join(self.config_obj.extensions)
        variable = tk.StringVar(value=extensions)
        ttk.Entry(parent, textvariable=variable, width=40).grid(
            row=0, column=1, columnspan=2, sticky="w", padx=12
        )
        self.vars["scan.extensions"] = variable

        recursive = tk.BooleanVar(value=self.config_obj.recursive)
        ttk.Checkbutton(parent, text="扫描子目录", variable=recursive).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=8
        )
        self.vars["scan.recursive"] = recursive

        skip_hidden = tk.BooleanVar(value=bool(self.config_obj.get("scan", "skip_hidden", default=True)))
        ttk.Checkbutton(parent, text="跳过隐藏文件/目录", variable=skip_hidden).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=8
        )
        self.vars["scan.skip_hidden"] = skip_hidden

    # ------------------------------------------------------------------
    def _save(self) -> None:
        for key, variable in self.vars.items():
            section, name = key.split(".", 1)
            try:
                value = variable.get()
            except tk.TclError:
                messagebox.showwarning("设置有误", f"{key} 的取值无效", parent=self)
                return
            if section == "rules":
                value = MODE_VALUES.get(str(value), "smart")
            elif section == "scan" and name == "extensions":
                items = [item.strip() for item in str(value).split(",") if item.strip()]
                value = [item if item.startswith(".") else "." + item for item in items] or [".txt"]
            self.config_obj.set(value, section, name)
        try:
            path = self.config_obj.save()
        except OSError as exc:
            messagebox.showerror("保存失败", f"无法写入 {path}：{exc}", parent=self)
            return
        self.on_saved()
        self.destroy()
