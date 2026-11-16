"""PyInstaller 打包入口（图形界面，无控制台窗口）。

支持把文件/文件夹拖到 exe 上，或从命令行带路径启动：

    QQ群广告扫描器.exe D:\\logs
    QQ群广告扫描器.exe chat.txt
"""

from __future__ import annotations

import sys

from qqadscan.gui.app import run_gui

if __name__ == "__main__":
    args = [item for item in sys.argv[1:] if not item.startswith("-")]
    sys.exit(run_gui(args or None))
