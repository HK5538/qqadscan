@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   QQ群广告扫描器 - 命令行模式
echo   只读扫描，不会删除或修改任何文件
echo ============================================================
echo.
set /p TARGET=请输入要扫描的 txt 文件或文件夹（可直接把文件拖进来）：
if "%TARGET%"=="" goto :eof

echo.
python -m qqadscan scan "%TARGET%" --formats txt,csv,json
echo.
echo 报告在上面的路径里，按任意键关闭。
pause >nul
