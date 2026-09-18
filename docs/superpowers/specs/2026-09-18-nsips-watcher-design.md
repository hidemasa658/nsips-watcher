# nsips-watcher 設計書

- **作成日**: 2026-09-18
- **著者**: hidemasa1201social@gmail.com
- **状態**: draft

## 1. 目的

solamichi クラウド薬歴クライアントが Windows 上で `C:\solamichi\solamichiclient\client\LOG\NSIPS\OK\` 直下に出力する成功ログ `.txt` を検知し、GUI に内容を表示しつつローカルにログを蓄積する GUI アプリを作る。

- **範囲外**: 外部送信、複数 PC 対応、暗号化、認証、SIPS フォルダの監視 (それは sips-watcher の役割)
- 単一 PC 上の GUI アプリのみ

## 2. 前提

- 監視対象 PC: Windows (10/11 想定)、solamichi クライアントがインストールされている PC
- 監視ベースパス (デフォルト): `C:\solamichi\solamichiclient\client\LOG\NSIPS\OK\`
- 監視は **直下のみ (non-recursive)**、`*.txt` のみ、大文字小文字区別なし
- .txt のエンコーディングは事前不明 (UTF-8 か CP932 を想定)
- 検知はローカル処理のみ、ネットワーク送信・API 連携は行わない
- sips-watcher (`~/dev/sips-watcher/`) とは完全に別プロジェクト、`core.py` は sips-watcher からコピーして利用

## 3. 動作仕様

### 3.1 起動シーケンス

1. tkinter ウィンドウを表示 (メニューバー + ラベル + ScrolledText)
2. `logs\` ディレクトリを作成 (無ければ)
   - PyInstaller ビルド版: `sys.executable` の親ディレクトリ配下
   - 開発時: `main.py` の親ディレクトリ配下
3. `config.json` を読み、監視ベースディレクトリ (base_dir) を決定:
   - `config.json` の `base_dir` が有効ならそれを使う (存在チェックのみ、SIPS のようなサブフォルダ判定は不要)
   - なければデフォルト `C:\solamichi\solamichiclient\client\LOG\NSIPS\OK\` を試す
   - どちらも見つからなければ tkinter フォルダ選択ダイアログを表示、有効パスまでループ
   - キャンセル → アプリ終了
4. base_dir 直下の既存 `.txt` の絶対パスを set (`existing_files`) に登録
5. watchdog `Observer` を起動、base_dir を `recursive=False` で監視
6. queue.Queue を `root.after(200ms)` でポーリング開始

### 3.2 検知時アクション

**監視イベント**: `on_created` と `on_moved` (dest が .txt) を扱う。`on_modified` は無視。

処理フロー:

1. `existing_files` に含まれていれば無視 (Lock で保護)
2. `wait_for_unlock` で読み込み可能になるまで待つ (0.1秒 × 20回)
3. `wait_for_stable_size` でサイズが 3 回連続同じになるまで待つ (書き込み完了判定)
4. `path.read_bytes()` + `decode_auto` で本文を取得
5. `logs\all.log` に UTF-8 で追記:
   ```
   [YYYY-MM-DD HH:MM:SS.mmm] <検知ファイルの絶対パス>
   <本文>
   ---
   ```
6. `logs\OK\<YYYYMMDD_HHMMSS_mmm>_<元ファイル名>` にバイナリコピー (衝突時 `_2`, `_3` リネーム)
7. `queue.Queue` に `("ok", timestamp, path, body)` を put
8. GUI スレッドが queue をポーリング、Text ウィジェットの内容を差し替え

### 3.3 エラー処理

- ロック解放タイムアウト / サイズ不安定: `all.log` に `[ERROR]` 記録、queue にも `("error", timestamp, path, "エラー内容")` を put して GUI に表示
- Handler 内の予期しない例外: try/except で握って `all.log` に traceback 記録、Observer は継続
- Queue が空: 次のポーリング周期を待つ

### 3.4 GUI レイアウト

- ウィンドウタイトル: `nsips-watcher`
- サイズ: 初期 800×600、リサイズ可
- メニューバー:
  - `ファイル(F)`:
    - `監視パスを変更(P)`: フォルダ選択ダイアログ → 有効なら Observer 再起動 & config.json 更新
    - `ログフォルダを開く(L)`: `os.startfile(LOG_DIR)`
    - `終了(X)`: Observer.stop() → root.destroy()
- 上部ラベル: `監視中: <base_dir>` (base_dir 変更時に更新)
- 中央: `ScrolledText` (read-only、フォント等幅、大サイズ)
  - 初期状態: 「監視待機中...」
  - 検知時: `# yyyy-mm-dd HH:MM:SS <path>\n\n<body>` で差し替え
  - エラー時: `# ERROR yyyy-mm-dd HH:MM:SS <path>\n\n<message>` で差し替え

### 3.5 終了処理

- ウィンドウの ✕ ボタンでも `終了` メニューでも同じ経路
- `WM_DELETE_WINDOW` プロトコルで `quit_app()` に紐付け
- Observer.stop() → Observer.join(timeout=5) → root.destroy()

## 4. ファイル配置

### 4.1 実行時

```
<任意フォルダ>\
  nsips-watcher.exe
  config.json                            # {"base_dir": "C:\\solamichi\\...\\OK"}
  logs\
    all.log                              # 全検知の時系列ログ (UTF-8)
    OK\
      20260918_103912_123_abc.txt        # 原本バイナリコピー
      20260918_104501_005_def.txt
```

### 4.2 リポジトリ

```
~/dev/nsips-watcher/
├── main.py               # tkinter GUI + Observer + NsipsHandler
├── core.py               # sips-watcher から純粋関数を丸ごとコピー
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_decode_auto.py
│   ├── test_snapshot_existing.py
│   ├── test_append_all_log.py
│   ├── test_unique_dest_path.py
│   ├── test_copy_backup.py
│   ├── test_wait_for_unlock.py
│   ├── test_wait_for_stable_size.py
│   ├── test_main_helpers.py             # resolve_base_dir 等
│   └── test_nsips_handler.py            # NsipsHandler 統合
├── requirements.txt      # watchdog==5.0.3
├── requirements-dev.txt  # + pytest==8.3.3, pyinstaller==6.10.0
├── build.bat
├── README.md
├── .gitignore
└── docs/superpowers/
    ├── specs/2026-09-18-nsips-watcher-design.md
    └── plans/2026-09-18-nsips-watcher.md
```

## 5. スレッド設計

- **メインスレッド (tkinter mainloop)**: GUI 描画とイベントループ、queue ポーリング (`root.after(200, poll_queue)`)
- **watchdog Observer スレッド (1 本)**: `NsipsHandler` のコールバックを呼ぶ。ファイル読み込み・all.log 追記・バックアップコピーまで完結。GUI は触らず queue に put だけ
- **スレッド間通信**: `queue.Queue` 1 本、`("ok"|"error", timestamp, path, body_or_message)` タプル
- **既存 set (`existing_files`) の保護**: `threading.Lock`

## 6. 技術スタック

- **言語**: Python 3.11
- **監視**: `watchdog==5.0.3` (PatternMatchingEventHandler)
- **GUI**: `tkinter` + `tkinter.ttk` + `tkinter.scrolledtext` + `tkinter.filedialog` + `tkinter.messagebox` (Python 標準ライブラリ)
- **配布**: `PyInstaller==6.10.0` (`--onefile --noconsole --name nsips-watcher`)
- **開発 OS**: macOS (コード書きと自動テスト)、動作確認は Windows 実機

## 7. テスト方針

### 7.1 自動テスト (pytest, macOS/Windows 両方で通す)

- **core.py の純粋関数**: sips-watcher の該当テストをそのままコピー (config, decode_auto, snapshot_existing, append_all_log, unique_dest_path, copy_backup, wait_for_unlock, wait_for_stable_size)
- **NsipsHandler の統合テスト**: `_process()` を直接呼び、queue に put されるか、all.log に追記されるか、コピーが作られるか、既存 .txt が skip されるか、パス外は無視されるか
- **resolve_base_dir**: config → default → None の遷移
- **GUI 部**: tkinter は自動テスト対象外 (手動確認)

### 7.2 手動確認 (Windows 実機、1 回)

1. `nsips-watcher.exe` 起動 → ウィンドウが表示され「監視中: <path>」ラベルと空の Text エリアが出る
2. 監視パス直下に `test.txt` を新規作成 → Text エリアに内容が表示される
3. `logs\all.log` に追記、`logs\OK\<ts>_test.txt` にコピーが存在
4. 起動前からあった .txt は検知されない
5. メニュー「監視パスを変更」→ 別フォルダに切替できる、config.json も更新される
6. メニュー「ログフォルダを開く」で explorer が開く
7. ✕ ボタンでプロセスが完全終了 (タスクマネージャで確認)
8. PyInstaller `build.bat` で `dist\nsips-watcher.exe` 単体で動く

## 8. 運用

- `.exe` は自由な場所に配置、同じフォルダに `config.json` と `logs\` が自動生成
- 自動起動は `shell:startup` に `.exe` ショートカット手動配置 (アプリ側では登録しない)
- ログの肥大化対策は本バージョンでは行わない (YAGNI)

## 9. 非対応 (YAGNI)

- ログローテーション
- 複数フォルダ同時監視 (sips-watcher の SIPS* パターンのような)
- 検知履歴の閲覧 UI (最新のみ表示、過去は logs\ を直接見る)
- 通知 (音、トースト、Windows notification)
- クリップボードへの自動コピー
- タスクトレイ最小化 (GUI ウィンドウのみ)
- エンコーディングの chardet 等による厳密判定 (cp932 で読めればほぼ問題なし)
