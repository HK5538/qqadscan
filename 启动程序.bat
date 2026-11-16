@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto :nopython

python -c "import tkinter" >nul 2>nul
if errorlevel 1 goto :notkinter

rem 取与 python 同目录的 pythonw.exe，避免启动时闪出黑色控制台
set "PYW="
for /f "delims=" %%i in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul') do set "PYW=%%i"

if defined PYW if exist "%PYW%" (
    start "" "%PYW%" -m qqadscan
    exit /b 0
)

python -m qqadscan
exit /b 0

:nopython
echo.
echo 没有找到 Python。请先安装 Python 3.9 或更高版本：
echo   https://www.python.org/downloads/windows/
echo 安装时请勾选 "Add python.exe to PATH"。
echo.
pause
exit /b 1

:notkinter
echo.
echo 当前 Python 缺少 tkinter（图形界面组件），无法打开窗口。
echo 解决办法：
echo   1. 用官方安装包重新安装 Python，并勾选 "tcl/tk and IDLE"；
echo   2. 或者改用命令行：python -m qqadscan scan 你的目录
echo.
pause
exit /b 1
