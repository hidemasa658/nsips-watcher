# NSIPS 累計統計機能 設計書

- **作成日**: 2026-09-18
- **著者**: hidemasa1201social@gmail.com
- **状態**: draft
- **プロジェクト**: nsips-watcher (既存アプリへの機能追加)

## 1. 目的

nsips-watcher が検知した NSIPS .txt の内容をパースし、SQLite に蓄積、GUI のタブで観点別に累計統計を見られるようにする。個人情報 (患者氏名等) は保存しない。

- **範囲外**: 期間フィルタ、レコード 3/5 のパース、削除・訂正処理、過去 .txt のバックフィル、加算コード辞書
- 単一 PC 上の GUI アプリ内で完結

## 2. 前提

- NSIPS 形式は行頭の数字でレコード種別を表す CSV
  - `1,` 患者情報 (**個人情報のため保存しない**)
  - `2,` 処方情報 (処方箋番号、日付、医療機関、医師)
  - `3,` 用法部 (RP番号、用法)
  - `4,` 医薬品 (YJコード、薬品名、用量、単位)
  - `5,` 調剤料
  - `6,` 調剤料内訳
  - `7,` 加算料
- 参考: https://github.com/araitatsuya-code/nsips-validator (MIT License)
- 文字コードは CP932 想定 (`decode_auto` で吸収)

## 3. データ設計

### 3.1 SQLite ファイル

- **配置**: `<app_dir>/logs/stats.db`
- **接続**: WAL モード (concurrent reader OK)
- **主キー**: `source_file` (絶対パス) で UNIQUE、重複検知は INSERT OR IGNORE

### 3.2 スキーマ

```sql
CREATE TABLE prescriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_file TEXT UNIQUE NOT NULL,        -- 検知した元 .txt のフルパス
  detected_at TEXT NOT NULL,               -- 検知日時 ISO
  prescription_date TEXT,                  -- 処方日 YYYYMMDD (record 2)
  clinic_code TEXT,                        -- 医療機関コード (record 2)
  clinic_name TEXT                         -- 医療機関名 (record 2)
);

CREATE TABLE drugs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prescription_id INTEGER NOT NULL,
  rp_no INTEGER,                           -- Rp番号 (record 4 col 2)
  yj_code TEXT,                            -- YJコード (record 4 col 4)
  name TEXT,                               -- 薬品名 (record 4 col 8)
  quantity REAL,                           -- 用量 (record 4 col 16)
  unit TEXT,                               -- 単位 (record 4 col 18)
  FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
);
CREATE INDEX idx_drugs_yj ON drugs(yj_code);

CREATE TABLE fees (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prescription_id INTEGER NOT NULL,
  fee_type TEXT,                           -- '6' (調剤料内訳) or '7' (加算料)
  code TEXT,                               -- 加算コード
  name TEXT,                               -- 加算名 (「計量混合加算」等)
  count INTEGER,                           -- 算定回数
  points INTEGER,                          -- 点数
  FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
);
CREATE INDEX idx_fees_name ON fees(name);
```

### 3.3 パーサーのカラム位置

nsips-validator の仕様に基づく主要カラム (0-indexed で、先頭のレコード種別を含む):

**record 2 (処方情報)**:
- col 4: 処方日 (YYYYMMDD)
- col 12: 医療機関コード
- col 14: 医療機関名

**record 4 (医薬品)**:
- col 2: Rp番号
- col 4: YJコード
- col 8: 薬品名
- col 16: 用量 (数値)
- col 18: 単位

**record 6, 7 (料金)**:
- col 2: コード
- col 3: 名称
- col 4: 算定回数
- col 5: 点数

(実データ形式は多少ゆれがある可能性があるため、実装ではフィールド不足を defensive に扱う: index out of range を空文字/None にフォールバック)

## 4. 動作仕様

### 4.1 検知時アクション (既存 `NsipsHandler._process` に追加)

既存の「all.log 追記 + copy_backup」の後に:

1. `parse_nsips(body)` で辞書化: `{"record_2": {...}, "record_4": [...], "record_6": [...], "record_7": [...]}`
2. `insert_prescription(db, source_file, detected_at, parsed)` で SQLite に INSERT
   - `INSERT OR IGNORE` で source_file 重複は skip (nsips-watcher の existing set と二重防御)
3. `queue.put(("stats_updated", None, None, None))` を追加 put (GUI に更新シグナル)

### 4.2 GUI タブ構成 (既存 ScrolledText を Notebook で包む)

**タブ 1: 最新検知** (既存の ScrolledText、変更なし)

**タブ 2: 薬剤別累計** (`ttk.Treeview`, 5 列)
- 列: `YJコード | 薬品名 | 調剤回数 | 総数量 | 単位`
- 集計 SQL:
  ```sql
  SELECT yj_code, name, COUNT(*) as n, SUM(quantity) as qty, unit
  FROM drugs GROUP BY yj_code, name, unit
  ORDER BY n DESC
  ```

**タブ 3: 医療機関別** (`ttk.Treeview`, 3 列)
- 列: `医療機関コード | 医療機関名 | 件数`
- 集計 SQL:
  ```sql
  SELECT clinic_code, clinic_name, COUNT(*) as n
  FROM prescriptions GROUP BY clinic_code, clinic_name
  ORDER BY n DESC
  ```

**タブ 4: 計量混合加算**
- 上段ラベル: `計量混合加算がついた処方: N 件`
- 下段 Treeview (2 列): `混合品目数 | 該当件数`
- 集計 SQL (2 段):
  ```sql
  -- 総件数
  SELECT COUNT(DISTINCT prescription_id) FROM fees WHERE name LIKE '%計量混合%';

  -- 品目数別内訳
  SELECT drug_count, COUNT(*) as n
  FROM (
    SELECT prescription_id, COUNT(*) as drug_count
    FROM drugs
    WHERE prescription_id IN (
      SELECT DISTINCT prescription_id FROM fees WHERE name LIKE '%計量混合%'
    )
    GROUP BY prescription_id
  )
  GROUP BY drug_count
  ORDER BY drug_count;
  ```
- **注**: 「品目数」は処方内の drugs 総数を近似値として使用 (厳密には計量混合された Rp のみを数えるべきだが、MVP では簡易実装)

**タブ 5: エクスポート** (ボタン 3 つ)
- 「薬剤別累計を CSV 保存」→ tkinter.filedialog.asksaveasfilename → 保存
- 「医療機関別を CSV 保存」→ 同上
- 「全 prescriptions を CSV 保存」→ 同上

### 4.3 タブ更新タイミング

- **アプリ起動時**: 各タブに全期間のデータを表示
- **新規検知時**: `stats_updated` シグナルを受けて、開いているタブのデータを再クエリして再描画
- 閉じているタブは描画不要 (`<<NotebookTabChanged>>` イベントで再描画も可)

## 5. モジュール構成

### 5.1 新規ファイル

```
~/dev/nsips-watcher/
├── nsips_parser.py       # NSIPS .txt → dict にパース (純粋関数、DB非依存)
├── stats_db.py           # SQLite の open/init/insert/query 関数群
├── tests/
│   ├── test_nsips_parser.py       # パーサーの単体テスト
│   ├── test_stats_db.py           # DB 操作の単体テスト
│   └── fixtures/
│       └── sample_nsips.txt       # 実データを匿名化した fixture
```

### 5.2 既存ファイル変更

- `main.py`:
  - `NsipsHandler._process` の末尾に stats 更新 (`insert_prescription`) を追加
  - `NsipsHandler.__init__` に `db_path` を受け取れるようにする (テスト時は tmp_path)
  - `NsipsWatcherApp._build_ui` を書き換え: 既存 ScrolledText を **タブ 1 (最新検知)** としてラップし、その上位に `ttk.Notebook` を配置。他 4 タブ (薬剤別/医療機関別/計量混合/エクスポート) を追加
  - `_poll_queue` で `stats_updated` シグナルを受け、開いているタブを再描画
  - `WM_DELETE_WINDOW` (`quit_app`) で SQLite 接続を close

- `requirements.txt`: 変更なし (sqlite3 は stdlib)

## 6. テスト方針

### 6.1 自動テスト (pytest)

- **`nsips_parser`**:
  - 各レコード種別の分解 (record_2 の 医療機関名, record_4 の YJコード等)
  - フィールド不足時の defensive 動作 (index out of range → None)
  - 複数レコードの正しいディスパッチ (record_4 が複数行あるケース)
- **`stats_db`**:
  - 空 DB → init テーブル作成
  - insert_prescription で 3 テーブルに整合的に INSERT
  - source_file 重複 → INSERT OR IGNORE で 1 件だけ
  - 集計クエリ (drugs 累計、clinics 累計、計量混合)
- **NsipsHandler 統合**: 既存テストは維持、fake event → stats.db にレコード入るか追加検証

### 6.2 手動確認 (Windows 実機)

1. `nsips-watcher.exe` 起動 → タブ 5 つが表示される
2. 新規 .txt が来る → タブ 1 (最新検知) 更新、タブ 2〜4 の数値が加算される
3. タブ 5 の各 CSV 保存ボタン → Excel で開ける
4. アプリ再起動 → 累計データが復元される (stats.db から)

## 7. 運用

- `stats.db` は `logs\` 内で自動生成
- サイズ肥大は SQLite なので大量データでも問題ないが、極端に増えた場合は手動削除で全リセット可能
- CSV エクスポートで外部集計 (Excel, pandas) にデータを渡せる

## 8. 非対応 (YAGNI)

- 期間フィルタ (今月/本日/カスタム)
- 加算コード辞書ベースの厳密判定
- レコード 3 (用法), 5 (調剤料) のパース
- 削除・訂正処理
- 過去 .txt のバックフィル
- グラフ表示
