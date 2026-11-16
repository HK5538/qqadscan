"""主窗口。

设计原则：
* 默认只读——扫描和评分不碰原文件；只有你点「输出清理后的文件」才会写出副本，
  覆盖原文件需要显式勾选并自动生成 .bak 备份；
* 结果按分数排序，每一分都能在详情里看到依据；
* 扫描在后台线程进行，界面不卡。
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import APP_NAME, __version__
from ..config import Config
from ..core.cleaning import DEFAULT_SUFFIX, build_plan, run_plan
from ..core.lexicon import Lexicon
from ..core.report import write_reports
from ..core.scanner import ProgressEvent, ScanOptions, ScanResult, Scanner
from ..paths import display_path, get_paths, relative_path
from ..plugins.loader import PluginManager
from . import theme
from .dialogs import CleanExportDialog
from .settings import SettingsDialog
from .widgets import DetailView, HelpWindow

BAND_FILTERS = {
    "全部": None,
    "A 高危": "A",
    "B 可疑": "B",
    "C 关注": "C",
    "D 低": "D",
}

COLUMNS = (
    ("score", "分数", 62, "center"),
    ("band", "等级", 78, "center"),
    ("digits", "解密号码", 130, "w"),
    ("group", "群关键词", 140, "w"),
    ("file", "文件", 150, "w"),
    ("line", "行号", 62, "center"),
    ("snippet", "原文片段", 520, "w"),
)


class ScanApp(tk.Tk):
    def __init__(self, initial_paths: list[str] | None = None) -> None:
        # 必须在创建窗口之前声明 DPI 感知，否则 125%/150% 缩放下窗口会比屏幕还高
        theme.enable_dpi_awareness()
        super().__init__()
        self.fonts = theme.Fonts()
        theme.apply_theme(self, self.fonts)

        self.title(f"{APP_NAME} v{__version__}  ——  扫描只读，删除需你确认")
        self._apply_geometry()
        self.minsize(900, 600)
        self.configure(background=theme.BG)
        self._set_window_icon()

        self._initial_paths = [str(item) for item in (initial_paths or []) if str(item).strip()]

        self.paths = get_paths()
        self.config_obj = Config.load(self.paths.config)
        self.lexicon: Lexicon | None = None
        self.result: ScanResult | None = None
        self.visible_entries: list = []
        self.entry_by_iid: dict[str, object] = {}
        # 已标记删除的行：key = (文件绝对路径, 行号)
        self.deleted_keys: set[tuple[str, int]] = set()
        self.deleted_entries: list = []
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self._render_job: str | None = None
        self._sort_column = "score"
        self._sort_desc = True

        self._build_menu()
        self._build_toolbar()
        # 状态栏必须先 pack（side=bottom），否则会被 expand 的主体挤出窗口
        self._build_status()
        self._build_body()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._poll_queue)
        self._load_lexicon(verbose=True)

        if self.config_obj.warnings:
            self._set_status("；".join(self.config_obj.warnings))

        # 支持「把文件/文件夹拖到 exe 上」或命令行带路径启动
        existing = [item for item in self._initial_paths if Path(item).exists()]
        if existing:
            self.path_var.set(" ; ".join(existing))
            self.after(350, self._start_scan)
        elif self._initial_paths:
            self._set_status("传入的路径不存在：" + "、".join(self._initial_paths))

    # ==================================================================
    # 界面构建
    # ==================================================================
    def _set_window_icon(self) -> None:
        try:
            from ..paths import bundle_dir

            icon = bundle_dir() / "assets" / "app.ico"
            if icon.is_file():
                self.iconbitmap(default=str(icon))
        except Exception:  # noqa: BLE001 - 图标缺失不影响使用
            pass

    def _apply_geometry(self) -> None:
        """按屏幕大小与 DPI 缩放自适应，避免小屏上状态栏被挤到屏幕外。"""
        try:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            screen_w, screen_h, scale = 1280, 800, 1.0
        width = min(int(1320 * scale), max(900, screen_w - 80))
        height = min(int(800 * scale), max(600, screen_h - 150))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - int(10 * scale))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="选择文件…", accelerator="Ctrl+O", command=self._choose_files)
        file_menu.add_command(label="选择文件夹…", accelerator="Ctrl+Shift+O", command=self._choose_folder)
        file_menu.add_separator()
        file_menu.add_command(label="导出当前结果…", accelerator="Ctrl+E", command=self._export)
        file_menu.add_command(label="打开报告目录", command=self._open_reports)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="设置…", command=self._open_settings)
        settings_menu.add_command(label="编辑 config.json", command=self._open_config_file)
        settings_menu.add_command(label="打开词库目录", command=lambda: self._open_folder(self.paths.lexicon))
        settings_menu.add_command(label="打开插件目录", command=lambda: self._open_folder(self.paths.plugins))
        settings_menu.add_separator()
        settings_menu.add_command(label="重新载入配置与词库", accelerator="F5", command=self._reload_all)
        menubar.add_cascade(label="设置", menu=settings_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="评分说明", command=self._show_help)
        help_menu.add_command(label="使用说明 / README", command=self._open_readme)
        help_menu.add_separator()
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.configure(menu=menubar)
        self.bind("<Control-o>", lambda _event: self._choose_files())
        self.bind("<Control-O>", lambda _event: self._choose_folder())
        self.bind("<Control-e>", lambda _event: self._export())
        self.bind("<F5>", lambda _event: self._reload_all())
        self.bind("<Escape>", lambda _event: self._cancel_scan())

    def _build_toolbar(self) -> None:
        outer = ttk.Frame(self, padding=(14, 12, 14, 6))
        outer.pack(fill="x")

        title_row = ttk.Frame(outer)
        title_row.pack(fill="x")
        ttk.Label(title_row, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(
            title_row,
            text="  识别同音字 / 拼音 / 圈号 / 形近符号伪装的 QQ 群号，只评分，不删文件",
            style="Muted.TLabel",
        ).pack(side="left", pady=(6, 0))

        path_row = ttk.Frame(outer)
        path_row.pack(fill="x", pady=(10, 0))
        self.path_var = tk.StringVar()
        entry = ttk.Entry(path_row, textvariable=self.path_var, font=self.fonts.base)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self._start_scan())
        ttk.Button(path_row, text="选择文件", command=self._choose_files).pack(side="left", padx=(8, 0))
        ttk.Button(path_row, text="选择文件夹", command=self._choose_folder).pack(side="left", padx=(6, 0))
        self.scan_button = ttk.Button(
            path_row, text="开始扫描", style="Accent.TButton", command=self._start_scan
        )
        self.scan_button.pack(side="left", padx=(10, 0))
        self.cancel_button = ttk.Button(
            path_row, text="取消", command=self._cancel_scan, state="disabled"
        )
        self.cancel_button.pack(side="left", padx=(6, 0))

        filter_row = ttk.Frame(outer)
        filter_row.pack(fill="x", pady=(10, 0))
        ttk.Label(filter_row, text="最低分数").pack(side="left")
        self.min_score_var = tk.IntVar(value=int(self.config_obj.get("ui", "min_score", default=0) or 0))
        spin = ttk.Spinbox(
            filter_row,
            from_=0,
            to=100,
            width=5,
            textvariable=self.min_score_var,
            command=self._apply_filters,
        )
        spin.pack(side="left", padx=(6, 14))
        spin.bind("<Return>", lambda _event: self._apply_filters())
        spin.bind("<FocusOut>", lambda _event: self._apply_filters())

        ttk.Label(filter_row, text="等级").pack(side="left")
        self.band_var = tk.StringVar(value="全部")
        band_combo = ttk.Combobox(
            filter_row, textvariable=self.band_var, values=list(BAND_FILTERS), width=8, state="readonly"
        )
        band_combo.pack(side="left", padx=(6, 14))
        band_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_filters())

        self.only_group_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            filter_row,
            text="只看附近有群关键词的",
            variable=self.only_group_var,
            command=self._apply_filters,
        ).pack(side="left", padx=(0, 14))

        ttk.Label(filter_row, text="搜索").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filters())
        ttk.Entry(filter_row, textvariable=self.search_var, width=26).pack(side="left", padx=(6, 0))

        ttk.Button(
            filter_row, text="重新载入配置与词库", command=self._reload_all
        ).pack(side="right")

        # 操作栏：多选删除 + 输出清理后的文件
        action_row = ttk.Frame(outer)
        action_row.pack(fill="x", pady=(8, 0))
        self.selection_var = tk.StringVar(value="未选中条目（Ctrl/Shift 可多选）")
        ttk.Label(action_row, textvariable=self.selection_var, style="Muted.TLabel").pack(side="left")

        self.delete_button = ttk.Button(
            action_row, text="删除选中", command=self._delete_selected, state="disabled"
        )
        self.delete_button.pack(side="left", padx=(12, 0))
        self.undo_button = ttk.Button(
            action_row, text="撤销删除", command=self._undo_delete, state="disabled"
        )
        self.undo_button.pack(side="left", padx=(6, 0))
        self.output_button = ttk.Button(
            action_row, text="输出清理后的文件", command=self._export_clean, state="disabled"
        )
        self.output_button.pack(side="left", padx=(6, 0))

        self.deleted_var = tk.StringVar(value="")
        ttk.Label(action_row, textvariable=self.deleted_var, foreground="#b91c1c").pack(
            side="left", padx=(12, 0)
        )

    def _build_body(self) -> None:
        container = ttk.Frame(self, padding=(14, 6, 14, 6))
        container.pack(fill="both", expand=True)

        paned = ttk.Panedwindow(container, orient="vertical")
        paned.pack(fill="both", expand=True)

        # 表格
        table_frame = ttk.Frame(paned, style="Panel.TFrame")
        self.tree = ttk.Treeview(
            table_frame,
            columns=[column[0] for column in COLUMNS],
            show="headings",
            selectmode="extended",
            height=14,
        )
        for key, title, width, anchor in COLUMNS:
            self.tree.heading(key, text=title, command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "snippet"), minwidth=50)
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        for band, options in theme.BAND_TAGS.items():
            self.tree.tag_configure(band, **options)
        self.tree.tag_configure("odd", background=theme.ROW_ALT)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Delete>", lambda _event: self._delete_selected())
        self.tree.bind("<Control-a>", self._select_all_rows)
        self._build_context_menu()

        # 详情
        self.detail = DetailView(paned, self.fonts)
        paned.add(table_frame, weight=3)
        paned.add(self.detail, weight=2)
        self.paned = paned
        self.after(120, self._place_sash)

    def _place_sash(self, attempt: int = 0) -> None:
        """给表格和详情一个合理的初始比例（否则表格会被挤成两行）。"""
        try:
            height = self.paned.winfo_height()
            if height < 400 and attempt < 25:
                # 窗口还没完成布局，等下一轮再试
                self.after(80, lambda: self._place_sash(attempt + 1))
                return
            if height > 240:
                self.paned.sashpos(0, max(240, int(height * 0.60)))
        except tk.TclError:
            pass

    def _build_context_menu(self) -> None:
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="删除选中行（Del）", command=self._delete_selected)
        self.context_menu.add_command(label="撤销全部删除", command=self._undo_delete)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="复制原文", command=lambda: self._copy("text"))
        self.context_menu.add_command(label="复制解密号码", command=lambda: self._copy("digits"))
        self.context_menu.add_command(label="复制「文件:行号」", command=lambda: self._copy("location"))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="在资源管理器中定位", command=self._reveal_file)

        def popup(event):
            iid = self.tree.identify_row(event.y)
            if iid:
                if iid not in self.tree.selection():
                    self.tree.selection_set(iid)
                self.context_menu.tk_popup(event.x_root, event.y_root)

        self.tree.bind("<Button-3>", popup)

    def _select_all_rows(self, _event=None):
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children)
            self.tree.focus(children[0])
            self._on_select()
        return "break"

    def _build_status(self) -> None:
        bar = ttk.Frame(self, padding=(14, 4, 14, 8))
        bar.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(bar, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(bar, mode="determinate", length=220)
        self.progress.pack(side="right")
        self.progress.pack_forget()

    # ==================================================================
    # 资源加载
    # ==================================================================
    def _load_lexicon(self, verbose: bool = False) -> None:
        try:
            self.lexicon = Lexicon.load(self.paths.lexicon)
        except Exception as exc:  # noqa: BLE001
            self.lexicon = None
            self._set_status(f"词库加载失败：{exc}")
            return
        if verbose:
            self._set_status(f"词库已载入：{self.lexicon.describe()}")

    def _reload_all(self) -> None:
        self.config_obj = Config.load(self.paths.config)
        self._load_lexicon(verbose=False)
        if self.result is not None:
            messagebox.showinfo(
                "已重新载入",
                "配置和词库已重新载入。\n\n已有结果不会自动重算，请重新扫描。",
                parent=self,
            )
        else:
            self._set_status("配置和词库已重新载入")

    # ==================================================================
    # 选择路径
    # ==================================================================
    def _append_paths(self, paths: list[str]) -> None:
        current = [item.strip() for item in self.path_var.get().split(";") if item.strip()]
        for path in paths:
            shown = display_path(path)
            if path and shown not in current:
                current.append(shown)
        self.path_var.set(" ; ".join(current))

    def _choose_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="选择要扫描的文本文件",
            filetypes=[("文本文件", "*.txt"), ("日志文件", "*.log"), ("所有文件", "*.*")],
        )
        if files:
            self._append_paths(list(files))

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择要扫描的文件夹")
        if folder:
            self._append_paths([folder])

    def _collect_paths(self) -> list[Path]:
        raw = [item.strip().strip('"') for item in self.path_var.get().split(";")]
        return [Path(item) for item in raw if item]

    # ==================================================================
    # 扫描
    # ==================================================================
    def _start_scan(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        paths = self._collect_paths()
        paths = [path for path in paths if path.exists()]
        if not paths:
            messagebox.showwarning("没有可扫描的路径", "请先选择 txt 文件或文件夹。", parent=self)
            return
        self.path_var.set(" ; ".join(display_path(path) for path in paths))

        self.stop_event.clear()
        self.result = None
        # 新一轮扫描，旧的删除标记已失效
        self.deleted_keys.clear()
        self.deleted_entries.clear()
        self._update_deleted_ui()
        self.tree.delete(*self.tree.get_children())
        self.entry_by_iid.clear()
        self.detail._empty()
        self.scan_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.pack(side="right")
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(12)
        self._set_status("正在准备词库…")

        self.worker = threading.Thread(target=self._scan_worker, args=(paths,), daemon=True)
        self.worker.start()

    def _scan_worker(self, paths: list[Path]) -> None:
        try:
            config = Config.load(self.paths.config)
            lexicon = Lexicon.load(self.paths.lexicon)
            manager = None
            if config.plugins_enabled:
                manager = PluginManager(config, lexicon, self.paths)
                manager.load()
            scanner = Scanner(config, lexicon, manager)
            max_rows = int(config.get("ui", "max_rows", default=20000) or 20000)
            options = ScanOptions(paths=paths, min_score=0, max_entries=max_rows)
            result = scanner.scan(
                options,
                progress=lambda event: self.queue.put(("progress", event)),
                should_stop=self.stop_event.is_set,
            )
            self.queue.put(("done", result))
        except Exception as exc:  # noqa: BLE001
            import traceback

            self.queue.put(("fatal", f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"))

    def _cancel_scan(self) -> None:
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            self._set_status("正在取消…")

    # ==================================================================
    # 事件轮询
    # ==================================================================
    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "progress":
                    self._on_progress(payload)
                elif kind == "done":
                    self._on_done(payload)
                elif kind == "fatal":
                    self._on_fatal(payload)
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _on_progress(self, event: ProgressEvent) -> None:
        if event.phase == "file":
            self._set_status(
                f"正在扫描 [{event.files_done + 1}/{event.files_total}] {event.current_file}"
                f"　已命中 {event.hits} 条"
            )
            if event.files_total > 1:
                if str(self.progress.cget("mode")) != "determinate":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=event.files_total)
                self.progress.configure(value=event.files_done)
        elif event.phase == "start":
            self._set_status(f"开始扫描：{event.message}")
        elif event.phase == "progress":
            self._set_status(
                f"已扫 {event.lines_done} 行　命中 {event.hits} 条　{event.current_file}"
            )

    def _on_done(self, result: ScanResult) -> None:
        self.result = result
        self.progress.stop()
        self.progress.pack_forget()
        self.scan_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

        counts = result.band_counts()
        message = (
            f"扫描完成：{result.files_scanned} 个文件 / {result.lines_scanned} 行，"
            f"命中 {result.total_hits} 条（A {counts['A']} / B {counts['B']} / "
            f"C {counts['C']} / D {counts['D']}）"
        )
        if result.cancelled:
            message += "　（已取消，结果不完整）"
        if result.errors:
            message += f"　{len(result.errors)} 条警告"
        self._set_status(message)
        self._apply_filters()

    def _on_fatal(self, message: str) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self.scan_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._set_status("扫描失败")
        messagebox.showerror("扫描失败", message, parent=self)

    # ==================================================================
    # 结果展示
    # ==================================================================
    def _apply_filters(self) -> None:
        if self.result is None:
            return
        try:
            min_score = int(self.min_score_var.get())
        except (tk.TclError, ValueError):
            min_score = 0
        band = BAND_FILTERS.get(self.band_var.get())
        keyword = self.search_var.get().strip().lower()
        only_group = self.only_group_var.get()

        entries = []
        for entry in self.result.entries:
            if entry.score < min_score:
                continue
            if band and entry.band != band:
                continue
            if only_group and not entry.group_tokens:
                continue
            if self._entry_key(entry) in self.deleted_keys:
                continue
            if keyword:
                haystack = " ".join(
                    [
                        entry.candidate.text,
                        entry.candidate.digits,
                        entry.candidate.file,
                        " ".join(entry.group_tokens),
                        " ".join(entry.ad_tokens),
                    ]
                ).lower()
                if keyword not in haystack:
                    continue
            entries.append(entry)
        self.visible_entries = self._sorted(entries)
        self._update_deleted_ui()
        self._render()

    def _sort_by(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_column = column
            self._sort_desc = column not in ("file", "digits")
        self.visible_entries = self._sorted(self.visible_entries)
        self._render()

    def _sorted(self, entries: list) -> list:
        column = self._sort_column
        reverse = self._sort_desc

        def key(entry):
            candidate = entry.candidate
            if column == "score":
                return entry.score
            if column == "band":
                return entry.band
            if column == "digits":
                return candidate.digits
            if column == "file":
                return (candidate.file, candidate.line_no)
            if column == "line":
                return candidate.line_no
            if column == "group":
                return (len(entry.group_tokens), entry.score)
            return (entry.score, candidate.file)

        return sorted(entries, key=key, reverse=reverse)

    def _render(self) -> None:
        if self._render_job:
            try:
                self.after_cancel(self._render_job)
            except tk.TclError:
                pass
            self._render_job = None
        self.tree.delete(*self.tree.get_children())
        self.entry_by_iid.clear()
        entries = self.visible_entries[: int(self.config_obj.get("ui", "max_rows", default=20000) or 20000)]
        self._pending = entries
        self._pending_index = 0
        if entries:
            self._insert_batch()
        else:
            self.detail._empty()

    def _insert_batch(self, size: int = 300) -> None:
        entries = getattr(self, "_pending", [])
        start = getattr(self, "_pending_index", 0)
        end = min(len(entries), start + size)
        for index in range(start, end):
            entry = entries[index]
            candidate = entry.candidate
            iid = f"r{index}"
            tags = [entry.band] if entry.band in theme.BAND_TAGS else []
            if index % 2:
                tags.append("odd")
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    entry.score,
                    entry.band_text,
                    candidate.digits,
                    "、".join(entry.group_tokens[:3]),
                    candidate.file,
                    candidate.line_no,
                    candidate.marked(radius=26),
                ),
                tags=tags,
            )
            self.entry_by_iid[iid] = entry
        self._pending_index = end
        if end < len(entries):
            self._render_job = self.after(1, self._insert_batch)
        else:
            self._render_job = None
            children = self.tree.get_children()
            if not children:
                self.detail._empty()
                return
            # 始终从最高分开始显示，并默认选中第一条
            self.tree.yview_moveto(0)
            if not self.tree.selection():
                self.tree.selection_set(children[0])
                self.tree.focus(children[0])
                self._on_select()
            # 布局完成后再校正一次滚动位置，避免前几行被藏在视口上方
            self.after(60, self._scroll_to_top)

    def _scroll_to_top(self) -> None:
        try:
            children = self.tree.get_children()
            if children:
                self.tree.see(children[0])
            self.tree.yview_moveto(0)
        except tk.TclError:
            pass

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        total = len(self.entry_by_iid)
        if not selection:
            self.selection_var.set(f"未选中条目（共 {total} 条，Ctrl/Shift 可多选）")
            self.delete_button.configure(state="disabled")
            return
        self.selection_var.set(f"已选 {len(selection)} 条 / 共 {total} 条")
        self.delete_button.configure(state="normal")
        entry = self.entry_by_iid.get(selection[0])
        if entry is not None:
            self.detail.show(entry)

    # ------------------------------------------------------------------
    # 删除 / 撤销 / 输出
    # ------------------------------------------------------------------
    @staticmethod
    def _entry_key(entry) -> tuple[str, int]:
        source = entry.source_path or entry.candidate.file
        try:
            source = str(Path(source).resolve())
        except OSError:
            source = str(source)
        return (os.path.normcase(source), int(entry.line_no))

    def _update_deleted_ui(self) -> None:
        count = len(self.deleted_entries)
        self.undo_button.configure(state="normal" if count else "disabled")
        self.output_button.configure(state="normal" if count else "disabled")
        self.deleted_var.set(f"待删除 {count} 行（尚未写入文件）" if count else "")

    def _delete_selected(self) -> None:
        selection = self.tree.selection()
        entries = [self.entry_by_iid[iid] for iid in selection if iid in self.entry_by_iid]
        if not entries:
            return
        added = 0
        for entry in entries:
            key = self._entry_key(entry)
            if key in self.deleted_keys:
                continue
            self.deleted_keys.add(key)
            self.deleted_entries.append(entry)
            added += 1
        if not added:
            return
        self._apply_filters()
        self._set_status(
            f"已标记删除 {added} 条（累计 {len(self.deleted_entries)} 行，尚未写入文件）；"
            "点「输出清理后的文件」生成副本"
        )

    def _undo_delete(self) -> None:
        if not self.deleted_entries:
            return
        count = len(self.deleted_entries)
        self.deleted_keys.clear()
        self.deleted_entries.clear()
        self._apply_filters()
        self._set_status(f"已撤销 {count} 行的删除标记")

    def _export_clean(self) -> None:
        if not self.deleted_entries:
            messagebox.showinfo("没有待删除的行", "先在列表里选中条目并点「删除选中」。", parent=self)
            return
        plan = build_plan(self.deleted_entries)
        if plan.empty():
            messagebox.showwarning("无法定位原文件", "这些条目缺少源文件路径，无法生成副本。", parent=self)
            return

        dialog = CleanExportDialog(
            self,
            default_dir=self.paths.root / "output",
            suffix=DEFAULT_SUFFIX,
            count=plan.total_lines,
            files=plan.total_files,
        )
        self.wait_window(dialog)
        options = dialog.result
        if not options:
            return

        outcomes = run_plan(
            plan,
            options["out_dir"],
            suffix=options["suffix"],
            overwrite=options["overwrite"],
            backup=True,
        )
        ok = [item for item in outcomes if item.ok]
        failed = [item for item in outcomes if not item.ok]
        removed = sum(item.removed for item in ok)

        lines = [f"已处理 {len(ok)} 个文件，删除 {removed} 行。"]
        for item in ok[:8]:
            lines.append(f"  {relative_path(item.target)}")
            if item.backup is not None:
                lines.append(f"    备份：{relative_path(item.backup)}")
        if failed:
            lines.append("")
            lines.append("失败：")
            for item in failed[:6]:
                lines.append(f"  {item.source.name}：{item.error}")
        target_dir = Path(options["out_dir"])
        if options["overwrite"] and ok:
            target_dir = ok[0].target.parent
            lines.append("")
            lines.append("原文件已被覆盖（已生成 .bak 备份），接下来会重新扫描。")

        self._set_status(f"输出完成：{len(ok)} 个文件，删除 {removed} 行")
        if failed and not ok:
            messagebox.showerror("输出失败", "\n".join(lines), parent=self)
            return
        if messagebox.askyesno("输出完成", "\n".join(lines) + "\n\n是否打开输出目录？", parent=self):
            self._open_folder(target_dir)

        if options["overwrite"]:
            self.deleted_keys.clear()
            self.deleted_entries.clear()
            self._update_deleted_ui()
            self.after(250, self._start_scan)

    # ==================================================================
    # 右键 / 双击
    # ==================================================================
    def _current_entry(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self.entry_by_iid.get(selection[0])

    def _copy(self, what: str) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        if what == "text":
            value = entry.candidate.text.strip()
        elif what == "digits":
            value = entry.candidate.digits
        else:
            value = f"{entry.candidate.file}:{entry.candidate.line_no}"
        self.clipboard_clear()
        self.clipboard_append(value)
        self._set_status("已复制到剪贴板")

    def _reveal_file(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        for path in self._collect_paths():
            base = path if path.is_dir() else path.parent
            target = base / entry.candidate.file
            if target.exists():
                try:
                    subprocess.Popen(["explorer", "/select,", str(target)])
                except OSError as exc:
                    messagebox.showerror("无法打开", str(exc), parent=self)
                return
        messagebox.showinfo("找不到文件", "原始文件可能已被移动。", parent=self)

    def _on_double_click(self, _event) -> None:
        self._reveal_file()

    # ==================================================================
    # 导出
    # ==================================================================
    def _export(self) -> None:
        if self.result is None:
            messagebox.showinfo("还没有结果", "请先扫描一次。", parent=self)
            return
        entries = self.visible_entries
        if not entries:
            messagebox.showinfo("没有可导出的内容", "当前筛选条件下没有结果。", parent=self)
            return
        result = replace(self.result, entries=list(entries))
        formats = self.config_obj.get("output", "formats", default=["txt", "csv", "json"]) or ["txt"]
        out_dir = self.paths.reports
        try:
            written = write_reports(result, out_dir, formats=list(formats), include_low=True)
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)
            return
        self._set_status(f"已导出 {len(written)} 个报告到 {out_dir}")
        text = "已生成：\n\n" + "\n".join(str(path) for path in written)
        if messagebox.askyesno("导出完成", text + "\n\n是否打开报告目录？", parent=self):
            self._open_folder(out_dir)

    # ==================================================================
    # 其它
    # ==================================================================
    def _open_folder(self, folder: Path) -> None:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("无法打开目录", str(exc), parent=self)

    def _open_reports(self) -> None:
        self._open_folder(self.paths.reports)

    def _open_config_file(self) -> None:
        try:
            os.startfile(str(self.paths.config))  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("无法打开", f"{exc}\n\n路径：{self.paths.config}", parent=self)

    def _open_readme(self) -> None:
        for name in ("README.md", "README.txt"):
            candidate = self.paths.root / name
            if candidate.is_file():
                try:
                    os.startfile(str(candidate))  # type: ignore[attr-defined]
                except OSError as exc:
                    messagebox.showerror("无法打开", str(exc), parent=self)
                return
        messagebox.showinfo("没有找到说明文件", f"请查看程序目录：{self.paths.root}", parent=self)

    def _open_settings(self) -> None:
        SettingsDialog(self, self.config_obj, self._after_settings_saved)

    def _after_settings_saved(self) -> None:
        self.config_obj = Config.load(self.paths.config)
        self._set_status("设置已保存")
        if self.result is not None:
            self._apply_filters()

    def _show_help(self) -> None:
        HelpWindow(self, self.fonts)

    def _show_about(self) -> None:
        messagebox.showinfo(
            "关于",
            f"{APP_NAME} v{__version__}\n\n"
            "扫描 txt 文件，识别用同音字、谐音、拼音、圈号符号、\n"
            "形近符号、偏旁部首伪装的 QQ 群号，并给出 0-100 的疑似广告评分。\n\n"
            "扫描过程只读；标记删除后由你点「输出清理后的文件」才写出副本，\n"
            "覆盖原文件需显式勾选并自动生成 .bak 备份。\n\n"
            f"词库目录：{self.paths.lexicon}\n"
            f"插件目录：{self.paths.plugins}\n"
            "许可证：MIT",
            parent=self,
        )

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _on_close(self) -> None:
        self.stop_event.set()
        self.destroy()


def run_gui(paths: list[str] | None = None) -> int:
    """启动图形界面；没有 tkinter 时给出提示。"""
    try:
        app = ScanApp(initial_paths=paths)
    except Exception as exc:  # noqa: BLE001
        print(f"无法启动图形界面：{exc}", file=sys.stderr)
        print("可以改用命令行：python -m qqadscan scan <目录>", file=sys.stderr)
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_gui())
