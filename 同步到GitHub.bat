@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   QQ群广告扫描器 - 同步到 GitHub
echo ============================================================
echo.
echo 第 1 步：先到 https://github.com/new 新建一个空仓库
echo          不要勾选 Add a README / .gitignore，仓库名建议 qqadscan
echo.

choice /c YN /n /m "现在打开新建仓库页面？(Y/N) "
if errorlevel 2 goto :skip_browser
start "" "https://github.com/new"

:skip_browser
echo.
echo 第 2 步：把仓库地址粘贴到下面，例如
echo          https://github.com/你的用户名/qqadscan.git
echo.

set "URL=%~1"
if "%URL%"=="" set /p URL=仓库地址：
if "%URL%"=="" goto :eof

where git >nul 2>nul
if errorlevel 1 (
    echo.
    echo 没有找到 git，请先安装 Git for Windows：
    echo   https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)

git rev-parse --git-dir >nul 2>nul
if errorlevel 1 (
    git init -b main
    git config user.name "QQAdScan"
    git config user.email "qqadscan@users.noreply.github.com"
    git add -A
    git commit -m "QQ群广告扫描器 v1.0.0"
)

git remote remove origin >nul 2>nul
git remote add origin "%URL%"
git branch -M main

echo.
echo 正在推送…（第一次会弹出 GitHub 登录窗口）
git push -u origin main
if errorlevel 1 goto :failed

echo.
echo 推送成功：%URL%
echo.
pause
exit /b 0

:failed
echo.
echo 推送失败，常见原因：
echo   1. 仓库还没创建，或者地址写错；
echo   2. 没有登录 GitHub / 没有该仓库的写权限；
echo   3. 仓库不是空的（新建时勾选了 README），先删掉仓库重建，或执行：
echo        git pull --rebase origin main
echo        git push -u origin main
echo.
pause
exit /b 1
