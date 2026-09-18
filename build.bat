@echo off
REM Windows での PyInstaller ビルドスクリプト
REM 事前に: pip install -r requirements-dev.txt

echo === GUI 版 nsips-watcher.exe をビルド ===
pyinstaller ^
  --onefile ^
  --noconsole ^
  --name nsips-watcher ^
  main.py

echo.
echo === サービス版 (裏で常駐監視) nsips-watcher-service.exe をビルド ===
pyinstaller ^
  --onefile ^
  --noconsole ^
  --name nsips-watcher-service ^
  service.py

echo.
echo === Build complete ===
echo dist\nsips-watcher.exe          (GUI: 見るときに手動起動)
echo dist\nsips-watcher-service.exe  (裏で常駐: スタートアップに登録)
