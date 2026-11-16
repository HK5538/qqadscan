"""插件加载器。

支持两种形式：

* 目录插件：``plugins/xxx/plugin.json`` + ``plugin.py``
* 单文件插件：``plugins/xxx.py``（模块里要有 ``PLUGIN`` 实例或 ``Plugin`` 类）

内置插件放在 ``qqadscan/plugins/builtin/``，随程序发布；外部插件放在程序目录的
``plugins/`` 下，用户自己增删即可。
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import pkgutil
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from ..config import Config
from ..core.decoder import Candidate
from ..core.lexicon import Lexicon
from ..core.scorer import KeywordAnalysis
from ..paths import AppPaths
from .api import API_VERSION, PluginBase, PluginContext, ScoreDelta

LOGGER = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^0-9A-Za-z_]")


@dataclass
class LoadedPlugin:
    plugin: PluginBase
    source: str
    builtin: bool = False


@dataclass
class PluginManager:
    """负责发现、加载、调度插件。"""

    config: Config
    lexicon: Lexicon
    paths: AppPaths
    logger: logging.Logger = LOGGER
    context: PluginContext | None = None
    plugins: list[LoadedPlugin] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    def load(self) -> list[LoadedPlugin]:
        self.context = PluginContext(
            config=self.config,
            lexicon=self.lexicon,
            root=self.paths.root,
            logger=self.logger,
        )
        if not self.config.plugins_enabled:
            self.logger.info("插件系统已在配置中关闭")
            return []

        disabled = {name.lower() for name in self.config.disabled_plugins}
        loaded: list[LoadedPlugin] = []

        for item in self._iter_builtin():
            if item.plugin.name.lower() in disabled:
                continue
            loaded.append(item)
        for item in self._iter_external():
            if item.plugin.name.lower() in disabled:
                continue
            loaded.append(item)

        self.plugins = []
        for item in loaded:
            try:
                item.plugin.setup(self.context)
                self.plugins.append(item)
            except Exception as exc:  # noqa: BLE001 - 插件隔离
                self.errors.append(f"插件 {item.plugin.name} 初始化失败：{exc}")
                self.logger.exception("插件初始化失败：%s", item.plugin.name)
        return self.plugins

    # ------------------------------------------------------------------
    def _iter_builtin(self):
        package = importlib.import_module("qqadscan.plugins.builtin")
        names = list(getattr(package, "BUILTIN_PLUGIN_MODULES", ()))
        if not names:
            names = [
                info.name
                for info in pkgutil.iter_modules(package.__path__)
                if not info.name.startswith("_")
            ]
        for name in names:
            if name.startswith("_"):
                continue
            module_name = f"{package.__name__}.{name}"
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"内置插件 {name} 导入失败：{exc}")
                continue
            plugin = self._instantiate(module)
            if plugin:
                yield LoadedPlugin(plugin=plugin, source=module_name, builtin=True)

    def _iter_external(self):
        root = self.paths.plugins
        if not root.is_dir():
            return
        for entry in sorted(root.iterdir()):
            if entry.name.startswith((".", "_")):
                continue
            if entry.is_dir():
                module = self._load_module_from_dir(entry)
                if module is None:
                    continue
                plugin = self._instantiate(module, manifest=self._read_manifest(entry))
                if plugin:
                    yield LoadedPlugin(plugin=plugin, source=str(entry))
            elif entry.suffix == ".py":
                module = self._load_module_from_file(entry)
                if module is None:
                    continue
                plugin = self._instantiate(module)
                if plugin:
                    yield LoadedPlugin(plugin=plugin, source=str(entry))

    # ------------------------------------------------------------------
    def _read_manifest(self, folder: Path) -> dict:
        manifest_path = folder / "plugin.json"
        if not manifest_path.is_file():
            return {}
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            self.errors.append(f"{folder.name}/plugin.json 解析失败：{exc}")
            return {}

    def _load_module_from_dir(self, folder: Path) -> ModuleType | None:
        manifest = self._read_manifest(folder)
        if manifest.get("enabled") is False:
            self.logger.info("插件 %s 在清单里被禁用", folder.name)
            return None
        entry = manifest.get("entry") or "plugin.py"
        target = folder / entry
        if not target.is_file():
            self.errors.append(f"{folder.name} 缺少入口文件 {entry}")
            return None
        return self._load_module_from_file(target, extra_path=str(folder))

    def _load_module_from_file(self, path: Path, extra_path: str | None = None) -> ModuleType | None:
        module_name = "qqadscan_ext_" + _SAFE_NAME.sub("_", path.stem) + f"_{abs(hash(str(path))) % 100000}"
        added = False
        if extra_path and extra_path not in sys.path:
            sys.path.insert(0, extra_path)
            added = True
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                self.errors.append(f"无法加载插件文件：{path}")
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"插件 {path.name} 加载失败：{exc}")
            self.logger.exception("插件加载失败：%s", path)
            return None
        finally:
            if added:
                try:
                    sys.path.remove(extra_path or "")
                except ValueError:
                    pass

    def _instantiate(self, module: ModuleType, manifest: dict | None = None) -> PluginBase | None:
        manifest = manifest or {}
        class_name = manifest.get("class")
        candidate = None
        if class_name:
            candidate = getattr(module, class_name, None)
        if candidate is None:
            candidate = getattr(module, "PLUGIN", None)
        if candidate is None:
            candidate = getattr(module, "Plugin", None)

        try:
            plugin = candidate() if isinstance(candidate, type) else candidate
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"{module.__name__} 实例化失败：{exc}")
            return None
        if plugin is None:
            self.errors.append(f"{module.__name__} 里没有找到 Plugin 类或 PLUGIN 实例")
            return None
        if not isinstance(plugin, PluginBase):
            self.errors.append(f"{module.__name__} 的插件类没有继承 PluginBase")
            return None
        if str(plugin.api_version) != API_VERSION:
            self.errors.append(
                f"插件 {plugin.name} 的 API 版本 {plugin.api_version} 与程序 {API_VERSION} 不匹配，已跳过"
            )
            return None

        if manifest.get("name"):
            plugin.name = str(manifest["name"])
        if manifest.get("version"):
            plugin.version = str(manifest["version"])
        if manifest.get("description"):
            plugin.description = str(manifest["description"])
        if manifest.get("author"):
            plugin.author = str(manifest["author"])
        return plugin

    # ------------------------------------------------------------------
    # 调度
    # ------------------------------------------------------------------
    @property
    def names(self) -> list[str]:
        return [item.plugin.name for item in self.plugins]

    def on_lexicon_ready(self) -> None:
        if not self.context:
            return
        for item in self.plugins:
            try:
                item.plugin.on_lexicon_ready(self.context)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"插件 {item.plugin.name} on_lexicon_ready 出错：{exc}")
                self.logger.exception("插件 on_lexicon_ready 出错：%s", item.plugin.name)

    def before_line(self, line: str, source: str = "") -> str | None:
        if not self.context:
            return line
        current: str | None = line
        for item in self.plugins:
            if current is None:
                return None
            try:
                current = item.plugin.before_line(current, self.context)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"插件 {item.plugin.name} before_line 出错（{source}）：{exc}")
                self.logger.exception("插件 before_line 出错：%s", item.plugin.name)
        return current

    def after_decode(self, candidates: list[Candidate], source: str = "") -> None:
        if not self.context:
            return
        for item in self.plugins:
            try:
                item.plugin.after_decode(candidates, self.context)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"插件 {item.plugin.name} after_decode 出错（{source}）：{exc}")

    def adjust_score(
        self, candidate: Candidate, analysis: KeywordAnalysis
    ) -> list[ScoreDelta]:
        deltas: list[ScoreDelta] = []
        if not self.context:
            return deltas
        for item in self.plugins:
            try:
                result = item.plugin.adjust_score(candidate, analysis, self.context)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"插件 {item.plugin.name} adjust_score 出错：{exc}")
                continue
            if not result:
                continue
            for delta in result:
                if isinstance(delta, ScoreDelta):
                    deltas.append(delta)
                else:
                    deltas.append(ScoreDelta(float(delta), f"插件 {item.plugin.name}"))
        return deltas

    def teardown(self) -> None:
        if not self.context:
            return
        for item in self.plugins:
            try:
                item.plugin.teardown(self.context)
            except Exception:  # noqa: BLE001
                self.logger.exception("插件 teardown 出错：%s", item.plugin.name)

    @property
    def report_notes(self) -> list[str]:
        return list(self.context.report_notes) if self.context else []
