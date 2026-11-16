# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

用法：
    python -m PyInstaller --noconfirm --clean qqadscan.spec

生成物在 dist/ 下：
    dist/QQ群广告扫描器/QQ群广告扫描器.exe       图形界面
    dist/QQ群广告扫描器/qqadscan-cli.exe          命令行
    dist/QQ群广告扫描器/lexicon/…                可直接编辑的词库
    dist/QQ群广告扫描器/config.json              可直接编辑的配置
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "lexicon"), "lexicon"),
    (str(ROOT / "plugins"), "plugins"),
    (str(ROOT / "config.json"), "."),
    (str(ROOT / "README.md"), "."),
]

hidden = collect_submodules("qqadscan")

gui_analysis = Analysis(
    ["launcher_gui.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "numpy", "PIL"],
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
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "numpy", "PIL", "tkinter"],
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
)
cli_coll = COLLECT(
    cli_exe,
    cli_analysis.binaries,
    cli_analysis.datas,
    strip=False,
    upx=False,
    name="QQ群广告扫描器-CLI",
)
