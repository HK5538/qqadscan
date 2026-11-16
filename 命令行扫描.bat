@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   QQ群广告扫描器 - 命令行模式
echo   扫描只读；如需删除，请用图形界面标记后输出
echo ============================================================
echo.
set /p TARGET=请输入要扫描的 txt 文件或文件夹（可直接把文件拖进来）：
if "%TARGET%"=="" goto :eof

echo.
python -m qqadscan scan "%TARGET%" --formats txt,csv,json
echo.
echo 报告在上面的路径里，按任意键关闭。
pause >nul
