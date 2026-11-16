"""PyInstaller 打包入口（图形界面，无控制台窗口）。"""

from __future__ import annotations

import sys

from qqadscan.gui.app import run_gui

if __name__ == "__main__":
    sys.exit(run_gui())
