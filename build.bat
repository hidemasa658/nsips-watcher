@echo off
REM Windows での PyInstaller ビルドスクリプト
REM 事前に: pip install -r requirements-dev.txt
pyinstaller ^
  --onefile ^
  --noconsole ^
  --name nsips-watcher ^
  main.py
echo.
echo === Build complete ===
echo dist\nsips-watcher.exe
