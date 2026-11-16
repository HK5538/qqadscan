"""配置加载与默认值。

配置文件是 ``config.json``（UTF-8），随程序放在一起，用户可以直接编辑。
所有字段都有默认值，缺字段时按默认值补齐，因此升级版本不会覆盖用户已有设置。
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import APP_ID
from .paths import CONFIG_NAME, default_config_candidates, data_root

#: 值为 True 时，表示「排除」这类条目
RULE_MODES = ("off", "smart", "always")

DEFAULT_CONFIG: dict[str, Any] = {
    "_说明": (
        "QQ群广告扫描器配置文件。修改后保存即可生效（GUI 里点「重新载入配置」）。"
        " rules 里的取值含义：off=不启用该排除规则；"
        "smart=只有当该数字没有任何群关键词/混淆迹象时才排除（推荐）；"
        "always=一律排除。"
    ),
    "scan": {
        "extensions": [".txt", ".log"],
        "recursive": True,
        "max_file_mb": 128,
        "skip_hidden": True,
        "encodings": ["utf-8-sig", "utf-8", "gb18030", "big5", "utf-16"],
    },
    "decode": {
        "min_digits": 5,
        "max_digits": 14,
        "max_gap": 3,
        "noise_precedence": True,
        "chinese_numeral_place_value": True,
        "boundary_chars": "。！？；;!?\n\r|",
    },
    "rules": {
        "pure_arabic": "smart",
        "pure_chinese": "smart",
        "quantifier": "smart",
        "time": "smart",
        "date": "smart",
        "phone": "smart",
    },
    "score": {
        "thresholds": {"high": 75, "medium": 50, "low": 30},
        "group_window": 26,
        "ad_window": 60,
        "weights": {
            "length": 22.0,
            "obfuscation": 26.0,
            "noise": 8.0,
            "group_keyword": 32.0,
            "ad_keyword": 14.0,
            "structure": 8.0,
            "penalty_pure_arabic": 12.0,
            "penalty_pure_chinese": 10.0,
            "penalty_quantifier": 35.0,
            "penalty_time": 45.0,
            "penalty_date": 28.0,
            "penalty_phone": 20.0,
        },
    },
    "output": {
        "dir": "reports",
        "formats": ["txt", "csv", "json"],
        "include_low": True,
        "max_entries": 0,
    },
    "plugins": {"enabled": True, "disabled": []},
    "ui": {"min_score": 0, "band": "全部", "max_rows": 20000, "font_size": 10},
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """递归合并字典，override 优先，但不会删除 base 的键。"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass
class Config:
    """配置对象，提供带默认值的属性访问。"""

    data: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_CONFIG))
    path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    # ---- 便捷访问 -----------------------------------------------------
    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    @property
    def extensions(self) -> tuple[str, ...]:
        raw = self.get("scan", "extensions", default=[".txt"]) or [".txt"]
        result = []
        for item in raw:
            ext = str(item).strip().lower()
            if not ext:
                continue
            result.append(ext if ext.startswith(".") else "." + ext)
        return tuple(result) or (".txt",)

    @property
    def recursive(self) -> bool:
        return bool(self.get("scan", "recursive", default=True))

    @property
    def max_file_bytes(self) -> int:
        try:
            mb = float(self.get("scan", "max_file_mb", default=128))
        except (TypeError, ValueError):
            mb = 128.0
        return max(1, int(mb * 1024 * 1024))

    @property
    def encodings(self) -> tuple[str, ...]:
        raw = self.get("scan", "encodings", default=None) or ["utf-8-sig", "utf-8", "gb18030"]
        return tuple(str(x) for x in raw)

    @property
    def min_digits(self) -> int:
        return int(self.get("decode", "min_digits", default=5) or 5)

    @property
    def max_digits(self) -> int:
        return int(self.get("decode", "max_digits", default=14) or 14)

    @property
    def max_gap(self) -> int:
        return int(self.get("decode", "max_gap", default=3) or 0)

    @property
    def noise_precedence(self) -> bool:
        return bool(self.get("decode", "noise_precedence", default=True))

    @property
    def chinese_place_value(self) -> bool:
        return bool(self.get("decode", "chinese_numeral_place_value", default=True))

    @property
    def boundary_chars(self) -> str:
        return str(self.get("decode", "boundary_chars", default="。！？；;!?\n\r"))

    def rule_mode(self, name: str) -> str:
        mode = str(self.get("rules", name, default="smart") or "smart").lower()
        return mode if mode in RULE_MODES else "smart"

    @property
    def thresholds(self) -> dict[str, int]:
        raw = self.get("score", "thresholds", default={}) or {}
        high = int(raw.get("high", 75))
        medium = int(raw.get("medium", 50))
        low = int(raw.get("low", 30))
        return {"high": high, "medium": medium, "low": low}

    @property
    def weights(self) -> dict[str, float]:
        raw = self.get("score", "weights", default={}) or {}
        base = copy.deepcopy(DEFAULT_CONFIG["score"]["weights"])
        for key, value in raw.items():
            try:
                base[key] = float(value)
            except (TypeError, ValueError):
                continue
        return base

    @property
    def group_window(self) -> int:
        return int(self.get("score", "group_window", default=26) or 26)

    @property
    def ad_window(self) -> int:
        return int(self.get("score", "ad_window", default=60) or 60)

    @property
    def plugins_enabled(self) -> bool:
        return bool(self.get("plugins", "enabled", default=True))

    @property
    def disabled_plugins(self) -> tuple[str, ...]:
        raw = self.get("plugins", "disabled", default=[]) or []
        return tuple(str(x) for x in raw)

    # ---- 读写 ---------------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        warnings: list[str] = []
        target = path
        if target is None:
            for candidate in default_config_candidates():
                if candidate.is_file():
                    target = candidate
                    break
        if target is None:
            return cls(warnings=["未找到 config.json，已使用内置默认配置"])

        try:
            raw = json.loads(target.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return cls(path=target, warnings=[f"配置文件不存在：{target}，已使用默认配置"])
        except json.JSONDecodeError as exc:
            return cls(
                path=target,
                warnings=[f"config.json 解析失败（第 {exc.lineno} 行）：{exc.msg}，已使用默认配置"],
            )

        if not isinstance(raw, dict):
            return cls(path=target, warnings=["config.json 顶层必须是对象，已使用默认配置"])

        merged = _deep_merge(DEFAULT_CONFIG, raw)
        cfg = cls(data=merged, path=target)
        cfg.warnings = warnings
        return cfg

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path or (data_root() / CONFIG_NAME)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.path = target
        return target

    def set(self, value: Any, *keys: str) -> None:
        node = self.data
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value
