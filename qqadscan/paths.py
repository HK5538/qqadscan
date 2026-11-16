"""运行目录解析。

区分三种目录：

* ``bundle_dir()``  —— 只读资源目录。打包成 exe 后是 PyInstaller 的临时解包目录，
  源码运行时就是项目根目录。
* ``app_dir()``     —— 程序所在目录（exe 所在目录 / 源码根目录），用户的词库、
  配置、插件、报告都放在这里，方便直接编辑。
* ``data_root()``   —— 真正可写的数据根目录。如果 ``app_dir()`` 不可写（例如放在
  ``C:\\Program Files`` 下），自动退回到 ``%APPDATA%\\QQAdScan``。
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from . import APP_ID

LEXICON_DIRNAME = "lexicon"
CONFIG_NAME = "config.json"
REPORTS_DIRNAME = "reports"
PLUGINS_DIRNAME = "plugins"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包后的 exe 中。"""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """只读资源目录（打包后为临时解包目录）。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def app_dir() -> Path:
    """程序所在目录：exe 同级目录，或源码仓库根目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def data_root() -> Path:
    """可写数据根目录。优先使用程序目录，不可写则回退到 %APPDATA%。"""
    override = os.environ.get("QQADSCAN_HOME")
    if override:
        target = Path(override).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target

    base = app_dir()
    if _is_writable(base):
        return base

    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    fallback = Path(appdata) / APP_ID
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


@dataclass(frozen=True)
class AppPaths:
    """一次性解析出的常用路径集合。"""

    root: Path
    lexicon: Path
    config: Path
    reports: Path
    plugins: Path

    def ensure(self) -> "AppPaths":
        for folder in (self.lexicon, self.reports, self.plugins):
            folder.mkdir(parents=True, exist_ok=True)
        return self


def _seed_defaults(root: Path) -> None:
    """首次运行时把内置的默认词库/配置复制到可写目录。"""
    src = bundle_dir()
    if src == root:
        return
    for name in (LEXICON_DIRNAME, PLUGINS_DIRNAME):
        source_dir = src / name
        target_dir = root / name
        if not source_dir.is_dir():
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in source_dir.iterdir():
            if item.is_file():
                target = target_dir / item.name
                if not target.exists():
                    try:
                        shutil.copy2(item, target)
                    except OSError:
                        pass
            elif item.is_dir():
                target_sub = target_dir / item.name
                if not target_sub.exists():
                    try:
                        shutil.copytree(item, target_sub)
                    except OSError:
                        pass
    cfg_src = src / CONFIG_NAME
    cfg_dst = root / CONFIG_NAME
    if cfg_src.is_file() and not cfg_dst.exists():
        try:
            shutil.copy2(cfg_src, cfg_dst)
        except OSError:
            pass


def get_paths(create: bool = True) -> AppPaths:
    """返回应用路径集合；``create=True`` 时会建目录并补齐默认文件。"""
    root = data_root()
    if create:
        _seed_defaults(root)
    paths = AppPaths(
        root=root,
        lexicon=root / LEXICON_DIRNAME,
        config=root / CONFIG_NAME,
        reports=root / REPORTS_DIRNAME,
        plugins=root / PLUGINS_DIRNAME,
    )
    if create:
        paths.ensure()
    return paths


def default_config_candidates() -> list[Path]:
    """配置文件候选位置：程序目录优先，打包资源目录兜底。"""
    return [data_root() / CONFIG_NAME, bundle_dir() / CONFIG_NAME]


def default_lexicon_dirs() -> list[Path]:
    """词库候选目录：程序目录优先，打包资源目录兜底。"""
    return [data_root() / LEXICON_DIRNAME, bundle_dir() / LEXICON_DIRNAME]
