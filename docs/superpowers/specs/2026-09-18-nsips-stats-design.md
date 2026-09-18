# NSIPS 累計統計機能 設計書 (v2 — VPS + 暗号化)

- **作成日**: 2026-09-18
- **著者**: hidemasa1201social@gmail.com
- **状態**: draft
- **プロジェクト**: nsips-watcher (既存アプリへの機能追加) + 新規 VPS サーバー
- **v1 との差分**: ローカル SQLite → さくら VPS + 部分暗号化 + record 1 削除

## 1. 目的

nsips-watcher が検知した NSIPS .txt の内容をパースし、個人情報 (record 1) を削除、非医療系フィールドを AES 暗号化した上で さくら rag-server の FastAPI に送信、VPS 側の SQLite で集計。GUI ではタブから VPS の集計 API を叩いて観点別に累計を表示する。

**プライバシー多層防御**:
- **削除**: record 1 (患者氏名・住所・生年月日) は VPS に一切送らない
- **暗号化**: 医療機関名、処方日、医師名、加算名などは クライアント PC の AES 鍵で暗号化してから送信 (VPS は暗号文だけ保持)
- **平文**: YJ コード、薬品名、用量、単位、点数、算定回数 — 集計クエリに必要な最小限のみ平文

## 2. 前提

- NSIPS 形式: 行頭数字でレコード種別を表す CSV
- クライアント: 薬局 PC (Windows 10/11) 上の nsips-watcher
- サーバー: 既存 `ssh rag-server` (root@133.167.80.39, CentOS)
  - 既存 FastAPI アプリ多数稼働中 (shift-app 等)。同居させる
  - Nginx リバースプロキシで `https://kumatool.duckdns.org/nsips-stats/` にマップ
- 参考: https://github.com/araitatsuya-code/nsips-validator (MIT License)
- 暗号化: AES-256-GCM (Python `cryptography` の Fernet)
- 認証: **mTLS (相互 TLS)** + Bearer token の二段階
  - 薬局 PC が動的 IP のため IP allowlist は不採用、代わりに クライアント証明書検証
  - Bearer token はコード漏洩対策 (証明書とセットで盗まれない限り無効)

## 3. データフロー

```
[薬局 PC / nsips-watcher]                    [rag-server / nsips-stats-api]
1. .txt 検知 (既存)                          
2. parse_nsips(body)                          
3. record 1 (患者情報) を破棄               
4. 暗号化: encrypt_field(k, plaintext)                    
    - clinic_name, clinic_code                             
    - prescription_date, doctor_name                       
    - fee_name (「計量混合加算」等)                        
    - rp_no (Rp 番号)                                      
5. POST /ingest                                            
   Bearer <api_token>                                      
   {                                                       
     "source_id": "<hash of source_file>",                 
     "detected_at": "...",                                 
     "clinic_code_enc": "...",     ← 暗号                  
     "clinic_name_enc": "...",     ← 暗号                  
     "prescription_date_enc": "...", ← 暗号                
     "drugs": [                                            
       {                                                   
         "rp_no_enc": "...",       ← 暗号                  
         "yj_code": "...",         ← 平文                  
         "name": "...",            ← 平文                  
         "quantity": 1.5,          ← 平文                  
         "unit": "g"               ← 平文                  
       }, ...                                              
     ],                                                    
     "fees": [                                             
       {                                                   
         "fee_type": "7",          ← 平文 (種別)           
         "code_enc": "...",        ← 暗号 (加算コード)     
         "name_enc": "...",        ← 暗号 (加算名)         
         "count": 1,               ← 平文                  
         "points": 59              ← 平文                  
       }, ...                                              
     ]                                                     
   }
                                            →→→→→→→→→→→→→→ 
                                                          ↓
                                             1. token 検証
                                             2. INSERT OR IGNORE
                                                prescriptions (source_id UNIQUE)
                                             3. drugs / fees を関連付けて INSERT

6. 集計表示時                              
   GET /stats/drugs → {rows:[{yj_code,name,unit,n,qty}]} 
                                            ← plain data (集計済)
   GET /stats/clinics → {rows:[{clinic_code_enc,clinic_name_enc,n}]}
                                            ← 暗号のまま (クライアントで復号)
   GET /stats/mix → {total:N, breakdown:[{drug_count,n}]}
                                            ← plain data (集計済)

7. クライアントで clinics の暗号列を復号して Treeview 表示
```

## 4. 暗号化仕様

### 4.1 鍵管理
- **鍵**: 32 バイトのランダムバイト列 (Fernet 用 base64 に変換)
- **保管**: クライアント PC の `<app_dir>/.key` (Windows なので パーミッションは強制できないが `.gitignore` 済)
- **生成**: 初回起動時、鍵ファイルが無ければ `Fernet.generate_key()` で生成
- **紛失時**: `.key` を失うと、既に VPS に送信済みの暗号化フィールドは復元不能。ユーザーが自主的にバックアップする責任

### 4.2 暗号方式
- **Fernet** (AES-128-CBC + HMAC-SHA256) を使用
- 出力は URL-safe base64 文字列 → そのまま JSON で送信可能
- 各フィールド個別に暗号化 (レコード全体を暗号化するより、集計時に一部だけ復号できて便利)

### 4.3 暗号化するフィールド (詳細)

| フィールド | 由来 | 平文/暗号 | 理由 |
|---|---|---|---|
| clinic_code | record 2 | 暗号 | 医療機関特定情報 |
| clinic_name | record 2 | 暗号 | 医療機関特定情報 |
| prescription_date | record 2 | 暗号 | 時系列で患者絞込に使われる可能性 |
| doctor_name | record 2 | 暗号 | 医師特定情報 |
| rp_no | record 4 | 暗号 | Rp 内訳を復元されるリスク緩和 |
| yj_code | record 4 | **平文** | 薬品集計の主キー |
| drug_name | record 4 | **平文** | 表示用 |
| quantity | record 4 | **平文** | 集計対象 |
| unit | record 4 | **平文** | 集計対象 |
| fee_type | record 6/7 | **平文** | 集計種別 |
| fee_code | record 6/7 | 暗号 | 加算コードは組み合わせで特定情報になり得る |
| fee_name | record 6/7 | 暗号 | 加算名で LIKE 検索したいが、暗号ではできないため、後述の `is_mix_flag` を追加 |
| count | record 6/7 | **平文** | 集計対象 |
| points | record 6/7 | **平文** | 集計対象 |

### 4.4 mTLS 設定

**証明書構成**:
- **プライベート CA** (`ca.key` + `ca.crt`, 有効期限 10 年): 開発者のローカルで生成、`ca.crt` のみ VPS 配布 (`/etc/nginx/certs/nsips-ca.crt`)
- **サーバー証明書**: kumatool.duckdns.org は既存の Let's Encrypt を継続使用 (別 CA)
- **クライアント証明書** (`client-<PC名>.crt` + `client-<PC名>.key`, 有効期限 5 年): **PC ごとに 1 発行**、USB 手渡しで配布

**発行スクリプト** (`nsips-stats-api/deploy/gen_certs.sh`):
```bash
# 初回: CA 生成
./gen_certs.sh init-ca

# PC ごと: クライアント証明書発行
./gen_certs.sh client <pc-identifier>   # 例: ./gen_certs.sh client pharmacy-pc-01
# → certs/client-pharmacy-pc-01.crt + certs/client-pharmacy-pc-01.key
```

**Nginx 設定**:
既存 `kumatool.duckdns.org` の server ブロックに:
```nginx
ssl_client_certificate /etc/nginx/certs/nsips-ca.crt;
ssl_verify_client optional;   # 他 location に影響しないため optional
```

`/nsips-stats/` の location 内で:
```nginx
if ($ssl_client_verify != SUCCESS) {
    return 403 "client cert required";
}
```

**クライアント (nsips-watcher)**:
- `config.json` に `client_cert_path`, `client_key_path` を追加
- `StatsClient.__init__` で `httpx.Client(cert=(cert_path, key_path))` を渡す

**紛失/失効時**:
- MVP では CRL (Certificate Revocation List) は組まない (YAGNI)
- 代わりに CA を再発行 → 全 PC に新しい client 証明書を配布 (実質「全交換」)
- 単一薬局・数 PC 前提のため運用負荷は小さい

### 4.5 「計量混合加算」の判定

暗号化された `fee_name` に対して VPS 側で `LIKE '%計量混合%'` はできない。以下で解決:

- **クライアント側で判定**: パース後、`fee.name` に「計量混合」を含むかチェック
- ある場合、`is_mix_flag = true` を平文で追加送信
- VPS 側は `is_mix_flag = true` の fee 行を持つ prescription をカウント

## 5. サーバー側 (rag-server) 設計

### 5.1 配置

```
/root/nsips-stats-api/
├── main.py                  # FastAPI アプリ
├── models.py                # Pydantic + SQLAlchemy (or 生 sqlite3)
├── db.py                    # SQLite 接続
├── requirements.txt         # fastapi, uvicorn, sqlmodel (or raw sqlite3)
├── .env                     # API_TOKEN (git 管理外)
├── stats.db                 # SQLite ファイル (実行時に自動生成)
└── nsips-stats.service      # systemd unit
```

### 5.2 SQLite スキーマ (VPS 側)

```sql
CREATE TABLE prescriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT UNIQUE NOT NULL,          -- クライアント側でソースファイル名の hash
  detected_at TEXT NOT NULL,
  clinic_code_enc TEXT,                     -- 暗号
  clinic_name_enc TEXT,                     -- 暗号
  prescription_date_enc TEXT,               -- 暗号
  doctor_name_enc TEXT                      -- 暗号
);

CREATE TABLE drugs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prescription_id INTEGER NOT NULL,
  rp_no_enc TEXT,                           -- 暗号
  yj_code TEXT,                             -- 平文
  name TEXT,                                -- 平文
  quantity REAL,                            -- 平文
  unit TEXT,                                -- 平文
  FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
);
CREATE INDEX idx_drugs_yj ON drugs(yj_code);

CREATE TABLE fees (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prescription_id INTEGER NOT NULL,
  fee_type TEXT,                            -- '6' or '7' 平文
  code_enc TEXT,                            -- 暗号
  name_enc TEXT,                            -- 暗号
  count INTEGER,                            -- 平文
  points INTEGER,                           -- 平文
  is_mix_flag INTEGER DEFAULT 0,            -- 平文フラグ (0/1)
  FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
);
CREATE INDEX idx_fees_mix ON fees(is_mix_flag);
```

### 5.3 エンドポイント

すべて `X-API-Token: <secret>` ヘッダー必須。

**`POST /ingest`**
- 受信 JSON を検証、`INSERT OR IGNORE` で prescriptions、drugs、fees に整合的に INSERT
- 既存 source_id は skip し `{"status": "duplicate"}` 返却
- 成功時 `{"status": "ok", "prescription_id": N}`

**`GET /stats/drugs`**
- SQL: `SELECT yj_code, name, unit, COUNT(*) n, SUM(quantity) qty FROM drugs GROUP BY yj_code, name, unit ORDER BY n DESC`
- Response: `{"rows": [{"yj_code":..., "name":..., "unit":..., "n":..., "qty":...}, ...]}`

**`GET /stats/clinics`**
- SQL: `SELECT clinic_code_enc, clinic_name_enc, COUNT(*) n FROM prescriptions GROUP BY clinic_code_enc, clinic_name_enc ORDER BY n DESC`
- Response: `{"rows": [{"clinic_code_enc":..., "clinic_name_enc":..., "n":...}, ...]}`
- クライアント側で復号

**`GET /stats/mix`**
- SQL 2 段:
  ```sql
  SELECT COUNT(DISTINCT prescription_id) FROM fees WHERE is_mix_flag = 1;
  SELECT drug_count, COUNT(*) n FROM (
    SELECT prescription_id, COUNT(*) drug_count
    FROM drugs WHERE prescription_id IN (
      SELECT DISTINCT prescription_id FROM fees WHERE is_mix_flag = 1
    )
    GROUP BY prescription_id
  ) GROUP BY drug_count ORDER BY drug_count;
  ```
- Response: `{"total": N, "breakdown": [{"drug_count":2, "n":10}, ...]}`

**`GET /stats/export/prescriptions`**
- SQL: `SELECT * FROM prescriptions`
- Response: 全暗号列を含む JSON。クライアントで復号 → CSV 化

### 5.4 デプロイ

- Nginx: 既存の `kumatool.duckdns.org` 設定に location 追加:
  ```
  location /nsips-stats/ {
    proxy_pass http://127.0.0.1:8XXX/;
    proxy_set_header X-API-Token $http_x_api_token;
  }
  ```
- systemd unit: `/etc/systemd/system/nsips-stats.service`、`ExecStart=uvicorn main:app --host 127.0.0.1 --port 8XXX`
- 実際のポート番号は既存アプリと重複しない値を選ぶ (デプロイ時に `ss -tlnp` で確認)

## 6. クライアント側 (nsips-watcher) 変更

### 6.1 新規ファイル

```
~/dev/nsips-watcher/
├── nsips_parser.py       # NSIPS .txt → dict (record 1 破棄、既存)
├── nsips_crypto.py       # Fernet 鍵管理 + encrypt_field / decrypt_field
├── stats_client.py       # HTTP クライアント: post_ingest, get_drugs, get_clinics, get_mix
├── tests/
│   ├── test_nsips_parser.py
│   ├── test_nsips_crypto.py
│   ├── test_stats_client.py           # httpx MockTransport で API モック
│   └── fixtures/sample_nsips.txt
```

### 6.2 既存ファイル変更

- **`main.py`**:
  - `NsipsHandler._process` に stats 送信を追加 (parse → strip record 1 → encrypt → post_ingest)
  - `NsipsWatcherApp._build_ui` を Notebook 化: タブ 1 (既存 ScrolledText), タブ 2-5 追加
  - タブ 2-4 は起動時 / 検知時 / `<<NotebookTabChanged>>` で再 fetch
  - タブ 5 (エクスポート) はボタン: fetch → 復号 → CSV 保存
- **`requirements.txt`**: `httpx==0.27.2`, `cryptography==43.0.1` を追加
- **`config.json` に追記**: 
  - `"api_base_url": "https://kumatool.duckdns.org/nsips-stats"`
  - `"api_token": "..."`
  - `"client_cert_path": "C:\\nsips-watcher\\client.crt"` (mTLS 用)
  - `"client_key_path": "C:\\nsips-watcher\\client.key"` (mTLS 用)

### 6.3 初期セットアップ UI

`config.json` に `api_token` が無ければ起動時にダイアログで入力させる (もしくは README で手動編集を案内)。

## 7. 動作仕様

### 7.1 検知時アクション (追加分)

`NsipsHandler._process` の末尾に:

1. `parsed = parse_nsips(body)` — record 1 は破棄済み
2. `is_mix = any("計量混合" in f["name"] for f in parsed["fees"])` を計算
3. `encrypted = build_ingest_payload(parsed, is_mix, key)` — 各フィールドを暗号化
4. `stats_client.post_ingest(encrypted)` — VPS へ HTTPS POST
   - ネットワーク失敗時: `logs\all.log` に `[STATS ERROR]` 記録、後述の再送は MVP 対象外 (YAGNI)
5. `queue.put(("stats_updated", ...))` — GUI に更新シグナル

### 7.2 集計表示

- 起動時: 各タブ (2-4) が最初に選ばれた時、`stats_client.get_*()` で fetch → Treeview に描画
- 検知時: `stats_updated` を受けたら **現在開いているタブ** を再 fetch (閉じているタブは次に開かれた時)
- clinics タブは fetch 後にクライアント側で `decrypt_field(key, clinic_name_enc)` を実行して表示

### 7.3 エクスポート

- 「薬剤別累計」: `get_drugs()` → そのまま CSV
- 「医療機関別」: `get_clinics()` → クライアント復号 → CSV
- 「全 prescriptions」: `get_export_prescriptions()` → クライアント復号 → CSV

## 8. テスト方針

### 8.1 自動テスト (pytest)

**クライアント側 (nsips-watcher)**:
- `nsips_parser`: record 1 が結果に含まれないこと、各種別の分解
- `nsips_crypto`: encrypt → decrypt roundtrip、鍵ファイル生成・読み込み
- `stats_client`: httpx MockTransport で API モック、送信ペイロードの内容確認、`X-API-Token` ヘッダー確認
- `NsipsHandler` 統合: fake event → post_ingest がモックで呼ばれることを確認

**サーバー側 (nsips-stats-api)**:
- TestClient で `/ingest` → duplicate → 200 duplicate 返却
- `/stats/drugs` に既知データを入れ、集計結果を検証
- token 無し → 401
- `is_mix_flag` 集計の正確性

### 8.2 手動確認 (Windows + rag-server)

1. サーバーデプロイ後 `curl -H "X-API-Token: xxx" https://kumatool.duckdns.org/nsips-stats/health` で疎通確認
2. Windows PC で nsips-watcher 起動 → .txt 検知 → VPS に POST 成功
3. 各タブ表示、CSV エクスポート
4. `.key` ファイルを別 PC にコピー → もう 1 台の nsips-watcher でも復号できる
5. `.key` 削除 → 再起動 → 新規鍵生成 → 既存 VPS データは復号エラー扱い (エラー表示)

## 9. 運用

- クライアント PC の `.key` は定期的にバックアップ (USB, Google Drive 等)
- API token 変更時は `config.json` と VPS `.env` を両方更新
- VPS の `stats.db` は VPS 上で `sqlite3 stats.db .backup ...` でバックアップ可能

## 10. 非対応 (YAGNI)

- 送信失敗時の再送キュー (単に log に記録し次回検知で気付く)
- 複数薬局対応 (単一 tenant 前提)
- 期間フィルタ (全期間のみ)
- 鍵ローテーション
- レコード 3 (用法), 5 (調剤料) のパース
- グラフ表示

## 11. 依存関係の追加

**クライアント**:
- `cryptography==43.0.1` (Fernet)
- `httpx==0.27.2` (HTTP client)

**サーバー**:
- `fastapi==0.115.0`
- `uvicorn[standard]==0.30.6`
- `pydantic==2.9.2`
- (sqlite3 は stdlib)
