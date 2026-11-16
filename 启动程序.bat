@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 依次尝试常见安装位置，挑第一个能 import tkinter 的 Python
set "PY="
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" call :try "%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" call :try "%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python311\python.exe" call :try "%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PY if exist "%ProgramFiles%\Python313\python.exe" call :try "%ProgramFiles%\Python313\python.exe"
if not defined PY if exist "%ProgramFiles%\Python312\python.exe" call :try "%ProgramFiles%\Python312\python.exe"
if not defined PY if exist "%ProgramFiles%\Python311\python.exe" call :try "%ProgramFiles%\Python311\python.exe"
if not defined PY if exist "%ProgramFiles%\Python310\python.exe" call :try "%ProgramFiles%\Python310\python.exe"
if not defined PY call :try "python"

if not defined PY goto :notkinter

rem 用同目录的 pythonw.exe 启动，避免闪出黑色控制台
set "PYW="
for /f "delims=" %%i in ('"%PY%" -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul') do set "PYW=%%i"
if defined PYW if exist "%PYW%" (
    start "" "%PYW%" -m qqadscan
    exit /b 0
)

"%PY%" -m qqadscan
exit /b 0

:try
"%~1" -c "import tkinter" >nul 2>nul
if errorlevel 1 exit /b 0
set "PY=%~1"
exit /b 0

:notkinter
echo.
echo 没有找到带 tkinter 的 Python（图形界面需要它）。
echo.
echo 解决办法：
echo   1. 安装官方 Python 3.9+：https://www.python.org/downloads/windows/
echo      安装时勾选 "tcl/tk and IDLE" 以及 "Add python.exe to PATH"；
echo   2. 或者先用命令行版：python -m qqadscan scan 你的目录
echo.
pause
exit /b 1
