"""PyInstaller 打包入口（命令行版，保留控制台）。"""

from __future__ import annotations

import sys

from qqadscan.cli import main

if __name__ == "__main__":
    sys.exit(main())
