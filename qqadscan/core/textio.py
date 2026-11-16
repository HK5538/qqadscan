"""文本读取：自动处理编码与超大文件。"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from pathlib import Path

#: 这些编码在严格模式下几乎不会报错，必须排在最后
_LAST_RESORT = ("gb18030", "big5", "latin-1")

DEFAULT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "big5", "utf-16")


class FileTooLarge(Exception):
    """文件超过配置的大小上限。"""


@dataclass
class TextFile:
    path: Path
    text: str
    encoding: str
    size: int

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()


def _bom_encoding(raw: bytes) -> str | None:
    if raw.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    if raw.startswith(codecs.BOM_UTF32_LE) or raw.startswith(codecs.BOM_UTF32_BE):
        return "utf-32"
    return None


def decode_bytes(raw: bytes, encodings: tuple[str, ...] = DEFAULT_ENCODINGS) -> tuple[str, str]:
    """按候选编码依次尝试解码，返回 (文本, 使用的编码)。"""
    bom = _bom_encoding(raw)
    if bom:
        try:
            return raw.decode(bom), bom
        except UnicodeDecodeError:
            pass

    tried: list[str] = []
    # 没有 BOM 的文件不要用 utf-8-sig 解码，否则写回时会凭空多出一个 BOM
    skip = {"utf-16", "utf-32"}
    if not raw.startswith(codecs.BOM_UTF8):
        skip.add("utf-8-sig")
    ordered = [enc for enc in encodings if enc.lower() not in skip]
    ordered += [enc for enc in _LAST_RESORT if enc not in ordered]
    for encoding in ordered:
        if encoding in tried:
            continue
        tried.append(encoding)
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue
    # 最后兜底：替换无法解码的字节，保证程序不崩
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


def read_text_file(
    path: Path,
    *,
    max_bytes: int = 128 * 1024 * 1024,
    encodings: tuple[str, ...] = DEFAULT_ENCODINGS,
) -> TextFile:
    size = path.stat().st_size
    if size > max_bytes:
        raise FileTooLarge(f"文件 {path.name} 大小 {size / 1048576:.1f} MB，超过上限 {max_bytes / 1048576:.0f} MB")
    raw = path.read_bytes()
    text, encoding = decode_bytes(raw, encodings)
    return TextFile(path=path, text=text, encoding=encoding, size=size)


#: 扫描时默认跳过的目录
SKIP_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".idea",
    ".vscode",
    "$recycle.bin",
    "system volume information",
    "windows",
    "program files",
    "program files (x86)",
    "appdata",
}
