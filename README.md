# nsips-watcher

Windows GUI アプリ。`C:\solamichi\solamichiclient\client\LOG\NSIPS\OK\` 直下に出力される `.txt` を監視し、最新内容を tkinter ウィンドウに表示 + `logs\all.log` 追記 + 原本コピーを行う。

sips-watcher (`~/dev/sips-watcher/`) の姉妹プロジェクト。`core.py` を共有 (コピー)。

設計書: `docs/superpowers/specs/2026-09-18-nsips-watcher-design.md`

## 開発 (macOS)

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Windows でのビルド

```
pip install -r requirements-dev.txt
build.bat
```

`dist\nsips-watcher.exe` が生成される。

## 実行

`.exe` を任意のフォルダに置いて起動。`.exe` と同じ場所に `config.json` と `logs\` が自動生成される。
