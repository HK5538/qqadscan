"""界面主题：字体、配色、DPI 适配。"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# 浅色主题（Windows 默认）
BG = "#f7f8fa"
PANEL_BG = "#ffffff"
BORDER = "#dfe3e8"
TEXT = "#1f2328"
MUTED = "#6b7280"
ACCENT = "#1a56db"
ACCENT_LIGHT = "#e8f0fe"
HIGHLIGHT_BG = "#fff2b8"
ROW_ALT = "#fafbfc"

BAND_TAGS = {
    "A": {"foreground": "#b91c1c"},
    "B": {"foreground": "#c2410c"},
    "C": {"foreground": "#a16207"},
    "D": {"foreground": "#6b7280"},
}


def enable_dpi_awareness() -> None:
    """让窗口在高分屏上不发虚。"""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:
            pass


class Fonts:
    def __init__(self, size: int = 10) -> None:
        family = self._pick_family(["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "SimHei"])
        mono_family = self._pick_family(["Cascadia Mono", "Consolas", "Courier New"])
        self.base = tkfont.Font(family=family, size=size)
        self.small = tkfont.Font(family=family, size=max(8, size - 1))
        self.bold = tkfont.Font(family=family, size=size, weight="bold")
        self.title = tkfont.Font(family=family, size=size + 8, weight="bold")
        self.h2 = tkfont.Font(family=family, size=size + 1, weight="bold")
        self.big = tkfont.Font(family=mono_family, size=size + 10, weight="bold")
        self.mono = tkfont.Font(family=mono_family, size=size)

    @staticmethod
    def _pick_family(candidates: list[str]) -> str:
        available = set(tkfont.families())
        for name in candidates:
            if name in available:
                return name
        return "TkDefaultFont"


def apply_theme(root: tk.Misc, fonts: Fonts) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("vista")
    except tk.TclError:
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    style.configure(".", font=fonts.base, background=BG, foreground=TEXT)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL_BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Title.TLabel", font=fonts.title, foreground=TEXT)
    style.configure("TButton", padding=(10, 4))
    style.configure("Accent.TButton", padding=(14, 5), font=fonts.bold)
    style.configure("TLabelframe", background=BG, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=MUTED, font=fonts.small)
    style.configure(
        "Treeview",
        background=PANEL_BG,
        fieldbackground=PANEL_BG,
        foreground=TEXT,
        rowheight=max(22, int(fonts.base.metrics("linespace") * 1.7)),
        bordercolor=BORDER,
    )
    style.configure(
        "Treeview.Heading",
        font=fonts.bold,
        background="#eef1f5",
        foreground=TEXT,
        relief="flat",
        padding=(6, 4),
    )
    style.map("Treeview.Heading", background=[("active", "#e3e8ef")])
    style.map("Treeview", background=[("selected", ACCENT_LIGHT)], foreground=[("selected", TEXT)])
    style.configure("TEntry", padding=4)
    style.configure("TSpinbox", padding=3)
    style.configure("TCombobox", padding=3)
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#e5e7eb")
    style.configure("TNotebook", background=BG)
    style.configure("TNotebook.Tab", padding=(12, 5))
    return style
