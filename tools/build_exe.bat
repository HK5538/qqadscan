@echo off
chcp 65001 >nul
cd /d "%~dp0.."

echo 正在安装/更新 PyInstaller…
python -m pip install --upgrade pyinstaller || goto :fail

echo.
echo 正在打包…
python -m PyInstaller --noconfirm --clean qqadscan.spec || goto :fail

echo.
echo 打包完成，产物在 dist\ 目录：
echo   dist\QQ群广告扫描器\QQ群广告扫描器.exe
echo   dist\QQ群广告扫描器-CLI\qqadscan-cli.exe
pause
exit /b 0

:fail
echo.
echo 打包失败，请检查上面的错误信息。
pause
exit /b 1
