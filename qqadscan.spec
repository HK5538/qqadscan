# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

用法：
    python -m PyInstaller --noconfirm --clean qqadscan.spec

生成物：
    dist/QQ群广告扫描器/QQ群广告扫描器.exe        图形界面（无控制台）
    dist/QQ群广告扫描器/lexicon/… config.json     可直接编辑
    dist/QQ群广告扫描器-CLI/qqadscan-cli.exe      命令行版
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)

DATA_FILES = [
    (str(ROOT / "lexicon"), "lexicon"),
    (str(ROOT / "plugins"), "plugins"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "config.json"), "."),
    (str(ROOT / "README.md"), "."),
]

# 只收集核心模块，避免把 tkinter 打进命令行版
BUILTIN_PLUGINS = ["contact_signals", "group_context", "obfuscation"]

CORE_HIDDEN = (
    collect_submodules("qqadscan.core")
    + collect_submodules("qqadscan.plugins")
    + ["qqadscan", "qqadscan.cli", "qqadscan.config", "qqadscan.paths"]
    + ["qqadscan.plugins.builtin"]
    + [f"qqadscan.plugins.builtin.{name}" for name in BUILTIN_PLUGINS]
)
GUI_HIDDEN = CORE_HIDDEN + ["qqadscan.gui"] + collect_submodules("qqadscan.gui")

COMMON_EXCLUDES = ["pytest", "numpy", "PIL", "matplotlib", "pandas"]

gui_analysis = Analysis(
    ["launcher_gui.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATA_FILES,
    hiddenimports=GUI_HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=COMMON_EXCLUDES,
    noarchive=False,
)
gui_pyz = PYZ(gui_analysis.pure)
gui_exe = EXE(
    gui_pyz,
    gui_analysis.scripts,
    [],
    exclude_binaries=True,
    name="QQ群广告扫描器",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "app.ico"),
)
gui_coll = COLLECT(
    gui_exe,
    gui_analysis.binaries,
    gui_analysis.datas,
    strip=False,
    upx=False,
    name="QQ群广告扫描器",
)

cli_analysis = Analysis(
    ["launcher_cli.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATA_FILES,
    hiddenimports=CORE_HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=COMMON_EXCLUDES + ["tkinter"],
    noarchive=False,
)
cli_pyz = PYZ(cli_analysis.pure)
cli_exe = EXE(
    cli_pyz,
    cli_analysis.scripts,
    [],
    exclude_binaries=True,
    name="qqadscan-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(ROOT / "assets" / "app.ico"),
)
cli_coll = COLLECT(
    cli_exe,
    cli_analysis.binaries,
    cli_analysis.datas,
    strip=False,
    upx=False,
    name="QQ群广告扫描器-CLI",
)
