"""对话框：导出清理后的文件。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import theme


class CleanExportDialog(tk.Toplevel):
    """让用户选择输出目录 / 后缀 / 是否覆盖原文件。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        default_dir: Path,
        suffix: str = "_已清理",
        count: int = 0,
        files: int = 0,
    ) -> None:
        super().__init__(master)
        self.title("输出清理后的文件")
        self.transient(master)
        self.resizable(False, False)
        self.result: dict | None = None

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text=f"将删除 {count} 行（涉及 {files} 个文件），生成新的文本文件。",
            font=theme.Fonts().h2,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        ttk.Label(frame, text="输出目录").grid(row=1, column=0, sticky="w", pady=4)
        self.dir_var = tk.StringVar(value=str(default_dir))
        ttk.Entry(frame, textvariable=self.dir_var, width=52).grid(
            row=1, column=1, sticky="we", padx=(8, 6)
        )
        ttk.Button(frame, text="浏览…", command=self._browse).grid(row=1, column=2)

        ttk.Label(frame, text="文件名后缀").grid(row=2, column=0, sticky="w", pady=4)
        self.suffix_var = tk.StringVar(value=suffix)
        ttk.Entry(frame, textvariable=self.suffix_var, width=18).grid(
            row=2, column=1, sticky="w", padx=(8, 6)
        )
        ttk.Label(
            frame,
            text="例：demo_已清理.txt",
            style="Muted.TLabel",
        ).grid(row=2, column=2, sticky="w")

        self.overwrite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="覆盖原文件（会先生成 .bak 备份，谨慎使用）",
            variable=self.overwrite_var,
            command=self._toggle_overwrite,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 2))

        self.warning = ttk.Label(
            frame,
            text="",
            style="Muted.TLabel",
            foreground="#b91c1c",
            wraplength=520,
        )
        self.warning.grid(row=4, column=0, columnspan=3, sticky="w")

        ttk.Label(
            frame,
            text="默认只写入新文件，原文件不会被改动；同时会在输出目录生成「_删除记录.txt」。",
            style="Muted.TLabel",
            wraplength=520,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))

        footer = ttk.Frame(frame)
        footer.grid(row=6, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(footer, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="开始输出", style="Accent.TButton", command=self._confirm).pack(
            side="right"
        )

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

    def _browse(self) -> None:
        folder = filedialog.askdirectory(parent=self, title="选择输出目录")
        if folder:
            self.dir_var.set(folder)

    def _toggle_overwrite(self) -> None:
        if self.overwrite_var.get():
            self.warning.configure(
                text="覆盖模式：原文件会被改写（先生成 .bak 备份）。建议先输出到新文件确认效果。"
            )
        else:
            self.warning.configure(text="")

    # ------------------------------------------------------------------
    def _confirm(self) -> None:
        out_dir = self.dir_var.get().strip()
        if not out_dir:
            messagebox.showwarning("请选择输出目录", "输出目录不能为空。", parent=self)
            return
        suffix = self.suffix_var.get().strip()
        overwrite = bool(self.overwrite_var.get())
        if overwrite:
            if not messagebox.askyesno(
                "确认覆盖原文件",
                "将直接改写被扫描的原始文件。\n\n程序会先在同一目录生成 .bak 备份，"
                "但仍然建议先输出到新文件核对结果。\n\n确定继续？",
                icon="warning",
                default="no",
                parent=self,
            ):
                return
        self.result = {
            "out_dir": Path(out_dir),
            "suffix": suffix,
            "overwrite": overwrite,
        }
        self.destroy()
