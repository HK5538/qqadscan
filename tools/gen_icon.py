"""生成程序图标 assets/app.ico。

用法（需要 Pillow，仅打包时用到）：
    python tools/gen_icon.py

图标含义：深蓝圆角方块 + 白色 Q（QQ 群）+ 右上角橙色感叹号（告警/评分）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "app.ico"

SIZE = 256
BLUE_TOP = (37, 99, 235)
BLUE_BOTTOM = (23, 54, 150)
ACCENT = (249, 115, 22)
WHITE = (255, 255, 255)


def _gradient(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(size):
        ratio = y / max(1, size - 1)
        color = tuple(
            int(BLUE_TOP[i] + (BLUE_BOTTOM[i] - BLUE_TOP[i]) * ratio) for i in range(3)
        )
        for x in range(size):
            pixels[x, y] = (*color, 255)
    return image


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    ]
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def build(size: int = SIZE) -> Image.Image:
    base = _gradient(size)
    base.putalpha(_rounded_mask(size, radius=int(size * 0.22)))

    draw = ImageDraw.Draw(base)

    # 顶部高光，让方块不那么平
    highlight = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    hd = ImageDraw.Draw(highlight)
    hd.ellipse([-size * 0.35, -size * 0.55, size * 1.1, size * 0.45], fill=(255, 255, 255, 26))
    base.alpha_composite(highlight)

    # 白色 Q
    font = _font(int(size * 0.66))
    text = "Q"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((size - (right - left)) / 2 - left, (size - (bottom - top)) / 2 - top - size * 0.02),
        text,
        font=font,
        fill=WHITE,
    )

    # 右上角橙色感叹号徽标
    badge_r = size * 0.15
    cx, cy = size * 0.79, size * 0.21
    draw.ellipse([cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r], fill=ACCENT)
    bar_w = max(2, int(badge_r * 0.26))
    draw.rounded_rectangle(
        [cx - bar_w / 2, cy - badge_r * 0.55, cx + bar_w / 2, cy + badge_r * 0.12],
        radius=bar_w / 2,
        fill=WHITE,
    )
    dot_r = badge_r * 0.15
    draw.ellipse([cx - dot_r, cy + badge_r * 0.3, cx + dot_r, cy + badge_r * 0.3 + dot_r * 2], fill=WHITE)
    return base


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image = build(SIZE)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    image.save(OUTPUT, format="ICO", sizes=sizes)
    preview = OUTPUT.with_suffix(".png")
    image.save(preview, format="PNG")
    print(f"已生成 {OUTPUT}（{', '.join(str(s[0]) for s in sizes)}）")
    print(f"预览图 {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
