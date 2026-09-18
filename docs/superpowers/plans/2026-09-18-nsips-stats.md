# NSIPS 累計統計機能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** nsips-watcher で検知した .txt を「record 1 削除 + 部分暗号化」してさくら rag-server の FastAPI + SQLite に送信、GUI では VPS の集計 API を叩いて 4 種のタブで累計を表示する機能を追加する。

**Architecture:** サーバー (`~/dev/nsips-stats-api` → rag-server デプロイ) と クライアント (`~/dev/nsips-watcher` 既存拡張) の 2 コンポーネント。サーバーは FastAPI + SQLite、認証は **mTLS (クライアント証明書検証) + X-API-Token** の二段階。クライアントは Fernet で選択フィールド暗号化 + httpx でクライアント証明書付き POST/GET。テストは pytest (サーバー: TestClient, クライアント: httpx MockTransport)。

**Tech Stack:** Python 3.11, FastAPI 0.115, uvicorn 0.30, SQLite (stdlib), httpx 0.27, cryptography 43.0.1, watchdog 5.0.3, tkinter (stdlib), Nginx, systemd, PyInstaller

**Related spec:** `docs/superpowers/specs/2026-09-18-nsips-stats-design.md`

---

# Phase 1: サーバー (nsips-stats-api on rag-server)

## Task 1: サーバースケルトン

**Files:**
- Create: `~/dev/nsips-stats-api/.gitignore`
- Create: `~/dev/nsips-stats-api/requirements.txt`
- Create: `~/dev/nsips-stats-api/requirements-dev.txt`
- Create: `~/dev/nsips-stats-api/.env.example`
- Create: `~/dev/nsips-stats-api/README.md`
- Create: `~/dev/nsips-stats-api/tests/__init__.py`

- [ ] **Step 1: プロジェクトディレクトリ作成 + git init**

```bash
mkdir -p ~/dev/nsips-stats-api/tests
cd ~/dev/nsips-stats-api
git init -q
```

- [ ] **Step 2: `.gitignore` を作成**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
.env
*.db
*.db-journal
*.db-wal
*.db-shm
.DS_Store
```

- [ ] **Step 3: `requirements.txt` を作成**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.9.2
python-dotenv==1.0.1
```

- [ ] **Step 4: `requirements-dev.txt` を作成**

```
-r requirements.txt
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 5: `.env.example` を作成**

```
API_TOKEN=change-me-to-strong-random-secret
DB_PATH=/root/nsips-stats-api/stats.db
```

- [ ] **Step 6: `README.md` を作成**

```markdown
# nsips-stats-api

nsips-watcher の統計データ受信・集計 API (さくら rag-server デプロイ用)。

FastAPI + SQLite、認証は X-API-Token ヘッダー。詳細は `~/dev/nsips-watcher/docs/superpowers/specs/2026-09-18-nsips-stats-design.md` 参照。

## 開発 (macOS)

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# .env の API_TOKEN を編集
pytest
uvicorn main:app --reload
```

## デプロイ (rag-server)

`deploy/deploy.md` 参照。
```

- [ ] **Step 7: `tests/__init__.py` を空ファイル作成**

```
```

- [ ] **Step 8: venv + 依存インストール + pytest 確認**

```bash
cd ~/dev/nsips-stats-api
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements-dev.txt
pytest --collect-only
```

Expected: `collected 0 items`

- [ ] **Step 9: コミット**

```bash
git add .gitignore requirements.txt requirements-dev.txt .env.example README.md tests/__init__.py
git commit -m "chore: スケルトン (FastAPI + pytest)"
```

---

## Task 2: `db.py` — SQLite 接続 + init_db

**Files:**
- Create: `~/dev/nsips-stats-api/db.py`
- Create: `~/dev/nsips-stats-api/tests/test_db.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_db.py`:

```python
import sqlite3
from pathlib import Path

from db import connect, init_db


def test_init_db_creates_all_tables(tmp_path):
    p = tmp_path / "stats.db"
    conn = connect(p)
    init_db(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    tables = [r[0] for r in rows]
    assert "prescriptions" in tables
    assert "drugs" in tables
    assert "fees" in tables


def test_init_db_creates_indexes(tmp_path):
    p = tmp_path / "stats.db"
    conn = connect(p)
    init_db(conn)
    idx = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()
    names = [r[0] for r in idx]
    assert "idx_drugs_yj" in names
    assert "idx_fees_mix" in names


def test_init_db_is_idempotent(tmp_path):
    p = tmp_path / "stats.db"
    conn = connect(p)
    init_db(conn)
    init_db(conn)  # 2 回目もエラーにならない
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    assert len(rows) == 3


def test_connect_creates_parent_dir(tmp_path):
    p = tmp_path / "sub" / "stats.db"
    conn = connect(p)
    assert p.parent.exists()
    conn.close()
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
cd ~/dev/nsips-stats-api
source .venv/bin/activate
pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: `db.py` を実装**

```python
"""SQLite 接続とスキーマ初期化。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS prescriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT UNIQUE NOT NULL,
  detected_at TEXT NOT NULL,
  clinic_code_enc TEXT,
  clinic_name_enc TEXT,
  prescription_date_enc TEXT,
  doctor_name_enc TEXT
);

CREATE TABLE IF NOT EXISTS drugs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prescription_id INTEGER NOT NULL,
  rp_no_enc TEXT,
  yj_code TEXT,
  name TEXT,
  quantity REAL,
  unit TEXT,
  FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
);

CREATE INDEX IF NOT EXISTS idx_drugs_yj ON drugs(yj_code);

CREATE TABLE IF NOT EXISTS fees (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prescription_id INTEGER NOT NULL,
  fee_type TEXT,
  code_enc TEXT,
  name_enc TEXT,
  count INTEGER,
  points INTEGER,
  is_mix_flag INTEGER DEFAULT 0,
  FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
);

CREATE INDEX IF NOT EXISTS idx_fees_mix ON fees(is_mix_flag);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """SQLite 接続を返す。親ディレクトリが無ければ作成、WAL モード有効化。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """スキーマを IF NOT EXISTS で流し込む (冪等)。"""
    conn.executescript(SCHEMA)
    conn.commit()
```

- [ ] **Step 4: テスト実行 → 成功確認**

```bash
pytest tests/test_db.py -v
```

Expected: 4 passed

- [ ] **Step 5: コミット**

```bash
git add db.py tests/test_db.py
git commit -m "feat(db): SQLite 接続 + init_db でスキーマ 3 テーブル + 2 index"
```

---

## Task 3: `models.py` — Pydantic モデル

**Files:**
- Create: `~/dev/nsips-stats-api/models.py`
- Create: `~/dev/nsips-stats-api/tests/test_models.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_models.py`:

```python
import pytest
from pydantic import ValidationError

from models import DrugIn, FeeIn, IngestPayload


def test_ingest_payload_minimal():
    p = IngestPayload(
        source_id="abc123",
        detected_at="2026-09-18T10:00:00",
        drugs=[],
        fees=[],
    )
    assert p.source_id == "abc123"
    assert p.drugs == []
    assert p.clinic_code_enc is None


def test_ingest_payload_with_data():
    p = IngestPayload(
        source_id="src",
        detected_at="2026-09-18T10:00:00",
        clinic_code_enc="ENC1",
        clinic_name_enc="ENC2",
        prescription_date_enc="ENC3",
        doctor_name_enc="ENC4",
        drugs=[
            DrugIn(
                rp_no_enc="ENC_RP",
                yj_code="6152004F2089",
                name="ビブラマイシン錠100mg",
                quantity=22.0,
                unit="錠",
            )
        ],
        fees=[
            FeeIn(
                fee_type="7",
                code_enc="ENC_CODE",
                name_enc="ENC_NAME",
                count=1,
                points=59,
                is_mix_flag=False,
            )
        ],
    )
    assert p.drugs[0].yj_code == "6152004F2089"
    assert p.fees[0].is_mix_flag is False


def test_ingest_payload_rejects_missing_source_id():
    with pytest.raises(ValidationError):
        IngestPayload(detected_at="x", drugs=[], fees=[])  # type: ignore


def test_drug_in_optional_fields():
    d = DrugIn(yj_code="X")
    assert d.name is None
    assert d.quantity is None
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 3: `models.py` を実装**

```python
"""Pydantic モデル (API リクエスト/レスポンス)。"""
from __future__ import annotations

from pydantic import BaseModel


class DrugIn(BaseModel):
    rp_no_enc: str | None = None
    yj_code: str | None = None
    name: str | None = None
    quantity: float | None = None
    unit: str | None = None


class FeeIn(BaseModel):
    fee_type: str | None = None
    code_enc: str | None = None
    name_enc: str | None = None
    count: int | None = None
    points: int | None = None
    is_mix_flag: bool = False


class IngestPayload(BaseModel):
    source_id: str
    detected_at: str
    clinic_code_enc: str | None = None
    clinic_name_enc: str | None = None
    prescription_date_enc: str | None = None
    doctor_name_enc: str | None = None
    drugs: list[DrugIn] = []
    fees: list[FeeIn] = []


class IngestResponse(BaseModel):
    status: str
    prescription_id: int | None = None


class DrugStat(BaseModel):
    yj_code: str | None
    name: str | None
    unit: str | None
    n: int
    qty: float | None


class DrugsResponse(BaseModel):
    rows: list[DrugStat]


class ClinicStat(BaseModel):
    clinic_code_enc: str | None
    clinic_name_enc: str | None
    n: int


class ClinicsResponse(BaseModel):
    rows: list[ClinicStat]


class MixBreakdown(BaseModel):
    drug_count: int
    n: int


class MixResponse(BaseModel):
    total: int
    breakdown: list[MixBreakdown]
```

- [ ] **Step 4: テスト実行 → 成功確認**

```bash
pytest tests/test_models.py -v
```

Expected: 4 passed

- [ ] **Step 5: コミット**

```bash
git add models.py tests/test_models.py
git commit -m "feat(models): Pydantic モデル (IngestPayload, DrugStat, ClinicStat, MixBreakdown)"
```

---

## Task 4: `main.py` — /health + X-API-Token 認証

**Files:**
- Create: `~/dev/nsips-stats-api/main.py`
- Create: `~/dev/nsips-stats-api/tests/test_health.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_health.py`:

```python
import os

from fastapi.testclient import TestClient

os.environ["API_TOKEN"] = "test-token"
os.environ["DB_PATH"] = ":memory:"

from main import app  # noqa: E402


def test_health_ok():
    client = TestClient(app)
    r = client.get("/health", headers={"X-API-Token": "test-token"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_missing_token():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 401


def test_health_wrong_token():
    client = TestClient(app)
    r = client.get("/health", headers={"X-API-Token": "wrong"})
    assert r.status_code == 401
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
pytest tests/test_health.py -v
```

Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: `main.py` を実装**

```python
"""nsips-stats-api FastAPI エントリポイント。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status

from db import connect, init_db

load_dotenv()

API_TOKEN = os.environ.get("API_TOKEN", "")
DB_PATH = os.environ.get("DB_PATH", "./stats.db")

app = FastAPI(title="nsips-stats-api", version="0.1.0")

# 起動時に DB 初期化
_conn_path = ":memory:" if DB_PATH == ":memory:" else DB_PATH
if _conn_path == ":memory:":
    import sqlite3 as _sq
    _conn = _sq.connect(":memory:", check_same_thread=False)
    _conn.row_factory = _sq.Row
    _conn.execute("PRAGMA foreign_keys = ON")
    init_db(_conn)
else:
    _conn = connect(Path(DB_PATH))
    # WAL モードでも同一プロセスから使うので check_same_thread=False 必須
    _conn.close()
    import sqlite3 as _sq
    _conn = _sq.connect(DB_PATH, check_same_thread=False)
    _conn.row_factory = _sq.Row
    _conn.execute("PRAGMA foreign_keys = ON")
    init_db(_conn)


def get_conn():
    return _conn


def verify_token(x_api_token: str | None = Header(default=None)) -> None:
    if not API_TOKEN or x_api_token != API_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


@app.get("/health")
def health(_: None = Depends(verify_token)) -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: テスト実行 → 成功確認**

```bash
pytest tests/test_health.py -v
```

Expected: 3 passed

- [ ] **Step 5: 全体テスト実行、回帰なし確認**

```bash
pytest -v
```

Expected: 全 pass (11 件程度)

- [ ] **Step 6: コミット**

```bash
git add main.py tests/test_health.py
git commit -m "feat(api): /health + X-API-Token 認証 (Depends)"
```

---

## Task 5: `POST /ingest` エンドポイント

**Files:**
- Modify: `~/dev/nsips-stats-api/main.py`
- Create: `~/dev/nsips-stats-api/tests/test_ingest.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_ingest.py`:

```python
import os

from fastapi.testclient import TestClient

os.environ["API_TOKEN"] = "test-token"
os.environ["DB_PATH"] = ":memory:"

from main import app, get_conn  # noqa: E402


def _headers() -> dict:
    return {"X-API-Token": "test-token"}


def _payload(source_id: str = "src1") -> dict:
    return {
        "source_id": source_id,
        "detected_at": "2026-09-18T10:00:00",
        "clinic_code_enc": "ENC_CLINIC_CODE",
        "clinic_name_enc": "ENC_CLINIC_NAME",
        "prescription_date_enc": "ENC_DATE",
        "doctor_name_enc": "ENC_DOC",
        "drugs": [
            {
                "rp_no_enc": "ENC_RP",
                "yj_code": "6152004F2089",
                "name": "ビブラマイシン錠100mg",
                "quantity": 22.0,
                "unit": "錠",
            }
        ],
        "fees": [
            {
                "fee_type": "7",
                "code_enc": "ENC_CODE",
                "name_enc": "ENC_NAME_MIX",
                "count": 1,
                "points": 100,
                "is_mix_flag": True,
            }
        ],
    }


def test_ingest_inserts_prescription_and_children():
    client = TestClient(app)
    r = client.post("/ingest", json=_payload(), headers=_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["prescription_id"], int)

    conn = get_conn()
    presc = conn.execute("SELECT * FROM prescriptions WHERE source_id='src1'").fetchone()
    assert presc is not None
    drugs = conn.execute("SELECT * FROM drugs WHERE prescription_id=?", (presc["id"],)).fetchall()
    assert len(drugs) == 1
    assert drugs[0]["yj_code"] == "6152004F2089"
    fees = conn.execute("SELECT * FROM fees WHERE prescription_id=?", (presc["id"],)).fetchall()
    assert len(fees) == 1
    assert fees[0]["is_mix_flag"] == 1


def test_ingest_duplicate_source_id_is_skipped():
    client = TestClient(app)
    r1 = client.post("/ingest", json=_payload("dup"), headers=_headers())
    assert r1.status_code == 200
    r2 = client.post("/ingest", json=_payload("dup"), headers=_headers())
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"

    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM prescriptions WHERE source_id='dup'").fetchone()[0]
    assert n == 1


def test_ingest_requires_token():
    client = TestClient(app)
    r = client.post("/ingest", json=_payload("noauth"))
    assert r.status_code == 401
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
pytest tests/test_ingest.py -v
```

Expected: `AssertionError` or `405 Method Not Allowed`

- [ ] **Step 3: `main.py` に `/ingest` を追加**

`main.py` の末尾に:

```python
from models import IngestPayload, IngestResponse


@app.post("/ingest", response_model=IngestResponse)
def ingest(payload: IngestPayload, _: None = Depends(verify_token)) -> IngestResponse:
    conn = get_conn()
    # duplicate check
    row = conn.execute(
        "SELECT id FROM prescriptions WHERE source_id=?", (payload.source_id,)
    ).fetchone()
    if row is not None:
        return IngestResponse(status="duplicate", prescription_id=row["id"])

    cur = conn.execute(
        """
        INSERT INTO prescriptions
          (source_id, detected_at, clinic_code_enc, clinic_name_enc,
           prescription_date_enc, doctor_name_enc)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payload.source_id,
            payload.detected_at,
            payload.clinic_code_enc,
            payload.clinic_name_enc,
            payload.prescription_date_enc,
            payload.doctor_name_enc,
        ),
    )
    presc_id = cur.lastrowid

    for d in payload.drugs:
        conn.execute(
            """
            INSERT INTO drugs
              (prescription_id, rp_no_enc, yj_code, name, quantity, unit)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (presc_id, d.rp_no_enc, d.yj_code, d.name, d.quantity, d.unit),
        )

    for f in payload.fees:
        conn.execute(
            """
            INSERT INTO fees
              (prescription_id, fee_type, code_enc, name_enc, count, points, is_mix_flag)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                presc_id,
                f.fee_type,
                f.code_enc,
                f.name_enc,
                f.count,
                f.points,
                1 if f.is_mix_flag else 0,
            ),
        )

    conn.commit()
    return IngestResponse(status="ok", prescription_id=presc_id)
```

- [ ] **Step 4: テスト実行 → 成功確認**

```bash
pytest tests/test_ingest.py -v
```

Expected: 3 passed

- [ ] **Step 5: 全体テスト実行**

```bash
pytest -v
```

Expected: 全 pass (14 件程度)

- [ ] **Step 6: コミット**

```bash
git add main.py tests/test_ingest.py
git commit -m "feat(api): POST /ingest で prescription + drugs + fees を INSERT (duplicate 検知)"
```

---

## Task 6: `GET /stats/drugs` エンドポイント

**Files:**
- Modify: `~/dev/nsips-stats-api/main.py`
- Create: `~/dev/nsips-stats-api/tests/test_stats_drugs.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_stats_drugs.py`:

```python
import os

from fastapi.testclient import TestClient

os.environ["API_TOKEN"] = "test-token"
os.environ["DB_PATH"] = ":memory:"

from main import app, get_conn  # noqa: E402


HEADERS = {"X-API-Token": "test-token"}


def _insert(source_id: str, drugs: list[dict]) -> None:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO prescriptions (source_id, detected_at) VALUES (?, ?)",
        (source_id, "2026-09-18T10:00:00"),
    )
    pid = cur.lastrowid
    for d in drugs:
        conn.execute(
            "INSERT INTO drugs (prescription_id, yj_code, name, quantity, unit) VALUES (?,?,?,?,?)",
            (pid, d["yj_code"], d["name"], d["quantity"], d["unit"]),
        )
    conn.commit()


def test_drugs_stats_empty():
    conn = get_conn()
    conn.executescript("DELETE FROM drugs; DELETE FROM prescriptions;")
    client = TestClient(app)
    r = client.get("/stats/drugs", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"rows": []}


def test_drugs_stats_aggregates_by_yj_name_unit():
    conn = get_conn()
    conn.executescript("DELETE FROM drugs; DELETE FROM prescriptions;")
    _insert("s1", [{"yj_code": "YJ1", "name": "A", "quantity": 10.0, "unit": "錠"}])
    _insert("s2", [{"yj_code": "YJ1", "name": "A", "quantity": 5.0, "unit": "錠"}])
    _insert("s3", [{"yj_code": "YJ2", "name": "B", "quantity": 3.0, "unit": "g"}])

    client = TestClient(app)
    r = client.get("/stats/drugs", headers=HEADERS)
    assert r.status_code == 200
    rows = r.json()["rows"]
    # 順序: n 降順
    assert rows[0]["yj_code"] == "YJ1"
    assert rows[0]["n"] == 2
    assert rows[0]["qty"] == 15.0
    assert rows[1]["yj_code"] == "YJ2"
    assert rows[1]["n"] == 1


def test_drugs_stats_requires_token():
    client = TestClient(app)
    r = client.get("/stats/drugs")
    assert r.status_code == 401
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
pytest tests/test_stats_drugs.py -v
```

Expected: FAIL (404 or 405)

- [ ] **Step 3: `main.py` に `/stats/drugs` を追加**

```python
from models import DrugsResponse, DrugStat


@app.get("/stats/drugs", response_model=DrugsResponse)
def stats_drugs(_: None = Depends(verify_token)) -> DrugsResponse:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT yj_code, name, unit, COUNT(*) AS n, SUM(quantity) AS qty
        FROM drugs
        GROUP BY yj_code, name, unit
        ORDER BY n DESC
        """
    ).fetchall()
    return DrugsResponse(
        rows=[DrugStat(yj_code=r["yj_code"], name=r["name"], unit=r["unit"], n=r["n"], qty=r["qty"]) for r in rows]
    )
```

- [ ] **Step 4: テスト実行 → 成功確認**

```bash
pytest tests/test_stats_drugs.py -v
```

Expected: 3 passed

- [ ] **Step 5: コミット**

```bash
git add main.py tests/test_stats_drugs.py
git commit -m "feat(api): GET /stats/drugs で YJ+薬品名+単位 別の累計"
```

---

## Task 7: `GET /stats/clinics` エンドポイント

**Files:**
- Modify: `~/dev/nsips-stats-api/main.py`
- Create: `~/dev/nsips-stats-api/tests/test_stats_clinics.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_stats_clinics.py`:

```python
import os

from fastapi.testclient import TestClient

os.environ["API_TOKEN"] = "test-token"
os.environ["DB_PATH"] = ":memory:"

from main import app, get_conn  # noqa: E402


HEADERS = {"X-API-Token": "test-token"}


def _clean() -> None:
    conn = get_conn()
    conn.executescript("DELETE FROM drugs; DELETE FROM fees; DELETE FROM prescriptions;")


def _insert(source_id: str, clinic_code_enc: str, clinic_name_enc: str) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO prescriptions
           (source_id, detected_at, clinic_code_enc, clinic_name_enc)
           VALUES (?, ?, ?, ?)""",
        (source_id, "2026-09-18T10:00:00", clinic_code_enc, clinic_name_enc),
    )
    conn.commit()


def test_clinics_stats_empty():
    _clean()
    client = TestClient(app)
    r = client.get("/stats/clinics", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"rows": []}


def test_clinics_stats_aggregates_by_encrypted_pair():
    _clean()
    _insert("s1", "ENC_A", "ENC_NAME_A")
    _insert("s2", "ENC_A", "ENC_NAME_A")
    _insert("s3", "ENC_B", "ENC_NAME_B")

    client = TestClient(app)
    r = client.get("/stats/clinics", headers=HEADERS)
    rows = r.json()["rows"]
    assert rows[0]["clinic_code_enc"] == "ENC_A"
    assert rows[0]["n"] == 2
    assert rows[1]["clinic_code_enc"] == "ENC_B"
    assert rows[1]["n"] == 1
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
pytest tests/test_stats_clinics.py -v
```

Expected: FAIL

- [ ] **Step 3: `main.py` に `/stats/clinics` 追加**

```python
from models import ClinicsResponse, ClinicStat


@app.get("/stats/clinics", response_model=ClinicsResponse)
def stats_clinics(_: None = Depends(verify_token)) -> ClinicsResponse:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT clinic_code_enc, clinic_name_enc, COUNT(*) AS n
        FROM prescriptions
        GROUP BY clinic_code_enc, clinic_name_enc
        ORDER BY n DESC
        """
    ).fetchall()
    return ClinicsResponse(
        rows=[
            ClinicStat(
                clinic_code_enc=r["clinic_code_enc"],
                clinic_name_enc=r["clinic_name_enc"],
                n=r["n"],
            )
            for r in rows
        ]
    )
```

- [ ] **Step 4: テスト実行 → 成功確認**

```bash
pytest tests/test_stats_clinics.py -v
```

Expected: 2 passed

- [ ] **Step 5: コミット**

```bash
git add main.py tests/test_stats_clinics.py
git commit -m "feat(api): GET /stats/clinics で医療機関 (暗号) 別の件数"
```

---

## Task 8: `GET /stats/mix` エンドポイント

**Files:**
- Modify: `~/dev/nsips-stats-api/main.py`
- Create: `~/dev/nsips-stats-api/tests/test_stats_mix.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_stats_mix.py`:

```python
import os

from fastapi.testclient import TestClient

os.environ["API_TOKEN"] = "test-token"
os.environ["DB_PATH"] = ":memory:"

from main import app, get_conn  # noqa: E402


HEADERS = {"X-API-Token": "test-token"}


def _clean() -> None:
    conn = get_conn()
    conn.executescript("DELETE FROM drugs; DELETE FROM fees; DELETE FROM prescriptions;")


def _add_prescription(source_id: str, drug_count: int, is_mix: bool) -> None:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO prescriptions (source_id, detected_at) VALUES (?, ?)",
        (source_id, "2026-09-18T10:00:00"),
    )
    pid = cur.lastrowid
    for i in range(drug_count):
        conn.execute(
            "INSERT INTO drugs (prescription_id, yj_code) VALUES (?, ?)",
            (pid, f"YJ_{i}"),
        )
    if is_mix:
        conn.execute(
            "INSERT INTO fees (prescription_id, fee_type, is_mix_flag) VALUES (?, ?, 1)",
            (pid, "7"),
        )
    conn.commit()


def test_mix_empty():
    _clean()
    client = TestClient(app)
    r = client.get("/stats/mix", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"total": 0, "breakdown": []}


def test_mix_counts_and_breakdown():
    _clean()
    _add_prescription("a", drug_count=2, is_mix=True)
    _add_prescription("b", drug_count=2, is_mix=True)
    _add_prescription("c", drug_count=3, is_mix=True)
    _add_prescription("d", drug_count=1, is_mix=False)  # 混合なしは除外

    client = TestClient(app)
    r = client.get("/stats/mix", headers=HEADERS)
    body = r.json()
    assert body["total"] == 3
    # 昇順: 2品目 → 2 件, 3品目 → 1 件
    assert body["breakdown"] == [
        {"drug_count": 2, "n": 2},
        {"drug_count": 3, "n": 1},
    ]
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
pytest tests/test_stats_mix.py -v
```

Expected: FAIL

- [ ] **Step 3: `main.py` に `/stats/mix` を追加**

```python
from models import MixBreakdown, MixResponse


@app.get("/stats/mix", response_model=MixResponse)
def stats_mix(_: None = Depends(verify_token)) -> MixResponse:
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(DISTINCT prescription_id) FROM fees WHERE is_mix_flag = 1"
    ).fetchone()[0]
    breakdown_rows = conn.execute(
        """
        SELECT drug_count, COUNT(*) AS n FROM (
          SELECT prescription_id, COUNT(*) AS drug_count
          FROM drugs
          WHERE prescription_id IN (
            SELECT DISTINCT prescription_id FROM fees WHERE is_mix_flag = 1
          )
          GROUP BY prescription_id
        )
        GROUP BY drug_count
        ORDER BY drug_count
        """
    ).fetchall()
    return MixResponse(
        total=total,
        breakdown=[MixBreakdown(drug_count=r["drug_count"], n=r["n"]) for r in breakdown_rows],
    )
```

- [ ] **Step 4: テスト実行 → 成功確認**

```bash
pytest tests/test_stats_mix.py -v
```

Expected: 2 passed

- [ ] **Step 5: コミット**

```bash
git add main.py tests/test_stats_mix.py
git commit -m "feat(api): GET /stats/mix で計量混合加算の総件数と品目数別内訳"
```

---

## Task 9: `GET /stats/export/prescriptions` エンドポイント

**Files:**
- Modify: `~/dev/nsips-stats-api/main.py`
- Modify: `~/dev/nsips-stats-api/models.py`
- Create: `~/dev/nsips-stats-api/tests/test_stats_export.py`

- [ ] **Step 1: `models.py` に `PrescriptionOut` を追加**

`models.py` の末尾に:

```python
class PrescriptionOut(BaseModel):
    id: int
    source_id: str
    detected_at: str
    clinic_code_enc: str | None
    clinic_name_enc: str | None
    prescription_date_enc: str | None
    doctor_name_enc: str | None


class PrescriptionsExportResponse(BaseModel):
    rows: list[PrescriptionOut]
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_stats_export.py`:

```python
import os

from fastapi.testclient import TestClient

os.environ["API_TOKEN"] = "test-token"
os.environ["DB_PATH"] = ":memory:"

from main import app, get_conn  # noqa: E402


HEADERS = {"X-API-Token": "test-token"}


def _clean() -> None:
    conn = get_conn()
    conn.executescript("DELETE FROM drugs; DELETE FROM fees; DELETE FROM prescriptions;")


def test_export_returns_all_prescriptions():
    _clean()
    conn = get_conn()
    conn.execute(
        """INSERT INTO prescriptions
           (source_id, detected_at, clinic_code_enc, clinic_name_enc)
           VALUES (?, ?, ?, ?)""",
        ("s1", "2026-09-18T10:00:00", "ENC_C", "ENC_N"),
    )
    conn.commit()
    client = TestClient(app)
    r = client.get("/stats/export/prescriptions", headers=HEADERS)
    body = r.json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["source_id"] == "s1"
    assert body["rows"][0]["clinic_code_enc"] == "ENC_C"
```

- [ ] **Step 3: テスト実行 → 失敗確認**

```bash
pytest tests/test_stats_export.py -v
```

Expected: FAIL

- [ ] **Step 4: `main.py` に `/stats/export/prescriptions` を追加**

```python
from models import PrescriptionOut, PrescriptionsExportResponse


@app.get("/stats/export/prescriptions", response_model=PrescriptionsExportResponse)
def export_prescriptions(_: None = Depends(verify_token)) -> PrescriptionsExportResponse:
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, source_id, detected_at, clinic_code_enc, clinic_name_enc,
                  prescription_date_enc, doctor_name_enc FROM prescriptions ORDER BY id"""
    ).fetchall()
    return PrescriptionsExportResponse(
        rows=[
            PrescriptionOut(
                id=r["id"],
                source_id=r["source_id"],
                detected_at=r["detected_at"],
                clinic_code_enc=r["clinic_code_enc"],
                clinic_name_enc=r["clinic_name_enc"],
                prescription_date_enc=r["prescription_date_enc"],
                doctor_name_enc=r["doctor_name_enc"],
            )
            for r in rows
        ]
    )
```

- [ ] **Step 5: テスト実行 → 成功確認**

```bash
pytest -v
```

Expected: 全 pass (20 件超)

- [ ] **Step 6: コミット**

```bash
git add main.py models.py tests/test_stats_export.py
git commit -m "feat(api): GET /stats/export/prescriptions で全暗号 prescriptions 返却"
```

---

## Task 9.5: mTLS 証明書発行スクリプト

**Files:**
- Create: `~/dev/nsips-stats-api/deploy/gen_certs.sh`
- Create: `~/dev/nsips-stats-api/deploy/certs/README.md`

- [ ] **Step 1: `deploy/gen_certs.sh` を作成**

```bash
#!/usr/bin/env bash
# nsips-stats-api mTLS 証明書生成スクリプト
# 使い方:
#   ./gen_certs.sh init-ca                 # 初回のみ: CA 生成
#   ./gen_certs.sh client <pc-identifier>  # PC ごとにクライアント証明書発行
set -euo pipefail

CERTS_DIR="$(dirname "$0")/certs"
mkdir -p "$CERTS_DIR"
cd "$CERTS_DIR"

case "${1:-}" in
  init-ca)
    if [[ -f ca.key ]]; then
      echo "CA already exists. Aborting."
      exit 1
    fi
    openssl genrsa -out ca.key 4096
    openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
      -subj "/CN=nsips-stats-api CA" \
      -out ca.crt
    chmod 600 ca.key
    echo "CA generated: ca.crt (デプロイ用) + ca.key (秘密、絶対公開しない)"
    ;;
  client)
    NAME="${2:?client name required (e.g., pharmacy-pc-01)}"
    if [[ ! -f ca.crt ]]; then
      echo "CA not found. Run './gen_certs.sh init-ca' first."
      exit 1
    fi
    openssl genrsa -out "client-${NAME}.key" 2048
    openssl req -new -key "client-${NAME}.key" \
      -subj "/CN=${NAME}" \
      -out "client-${NAME}.csr"
    openssl x509 -req -in "client-${NAME}.csr" \
      -CA ca.crt -CAkey ca.key -CAcreateserial \
      -out "client-${NAME}.crt" -days 1825 -sha256
    rm "client-${NAME}.csr"
    chmod 600 "client-${NAME}.key"
    echo "Client cert generated:"
    echo "  client-${NAME}.crt  (公開可: 対象 PC + サーバーは不要)"
    echo "  client-${NAME}.key  (秘密: 対象 PC にのみ配置、USB 手渡し推奨)"
    ;;
  *)
    echo "Usage: $0 {init-ca | client <pc-name>}"
    exit 1
    ;;
esac
```

- [ ] **Step 2: 実行権限を付与**

```bash
chmod +x ~/dev/nsips-stats-api/deploy/gen_certs.sh
```

- [ ] **Step 3: `deploy/certs/README.md` を作成**

```markdown
# 証明書ディレクトリ

このディレクトリは `.gitignore` されています。開発者ローカルでのみ管理。

## 生成物

- `ca.crt` — サーバー配布用 (VPS の `/etc/nginx/certs/nsips-ca.crt` へコピー)
- `ca.key` — 発行者の秘密鍵 (**絶対公開しない**)
- `client-<name>.crt` + `client-<name>.key` — 各薬局 PC 用 (USB 手渡し配布)
- `ca.srl` — シリアル番号管理 (openssl 自動生成)

## バックアップ

`ca.key` を紛失すると新しい CA を作り直す必要があり、全 client 証明書を再発行する必要がある。1Password / パスワードマネージャ等に格納推奨。
```

- [ ] **Step 4: `.gitignore` に `deploy/certs/*.key`, `*.crt`, `*.srl`, `*.csr` を追加**

`~/dev/nsips-stats-api/.gitignore` の末尾に:
```
deploy/certs/*.key
deploy/certs/*.crt
deploy/certs/*.srl
deploy/certs/*.csr
```

(README.md は追跡する)

- [ ] **Step 5: CA を初回生成 + テストクライアント発行**

```bash
cd ~/dev/nsips-stats-api
./deploy/gen_certs.sh init-ca
./deploy/gen_certs.sh client test-macos
ls deploy/certs/
# → ca.crt, ca.key, client-test-macos.crt, client-test-macos.key
```

- [ ] **Step 6: コミット (証明書ファイル自体は .gitignore で入らない)**

```bash
git add .gitignore deploy/gen_certs.sh deploy/certs/README.md
git commit -m "chore: mTLS 証明書発行スクリプト (init-ca + client <name>)"
```

---

## Task 10: GitHub public リポジトリ作成 + push

**Files:**
- なし

- [ ] **Step 1: GitHub リポジトリ作成 + push**

```bash
cd ~/dev/nsips-stats-api
gh repo create hidemasa658/nsips-stats-api --public --source=. --remote=origin
git branch -M main
git push -u origin main
```

- [ ] **Step 2: MEMORY.md に登録**

`~/.claude/projects/-Users-a/memory/nsips-stats-api.md` を作成し、`MEMORY.md` に 1 行追加。

---

## Task 11: rag-server にデプロイ

**Files:**
- Create: `~/dev/nsips-stats-api/deploy/nsips-stats.service`
- Create: `~/dev/nsips-stats-api/deploy/deploy.md`

- [ ] **Step 1: `deploy/nsips-stats.service` を作成**

```ini
[Unit]
Description=nsips-stats-api (FastAPI)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/nsips-stats-api
EnvironmentFile=/root/nsips-stats-api/.env
ExecStart=/root/nsips-stats-api/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 18821
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: `deploy/deploy.md` を作成 (rag-server 上での手順)**

```markdown
# rag-server デプロイ手順

## 初回セットアップ

```bash
ssh rag-server
cd /root
git clone https://github.com/hidemasa658/nsips-stats-api.git
cd nsips-stats-api
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# .env 作成
cp .env.example .env
# エディタで API_TOKEN を強めのランダム文字列に変更
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# systemd
cp deploy/nsips-stats.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now nsips-stats
systemctl status nsips-stats

# ポート疎通確認
curl -H "X-API-Token: $(grep API_TOKEN .env | cut -d= -f2)" http://127.0.0.1:18821/health
# → {"status":"ok"}
```

## mTLS 用 CA 証明書を配置

開発者マシンで生成した `ca.crt` を rag-server にコピー:

```bash
# macOS 側で
scp ~/dev/nsips-stats-api/deploy/certs/ca.crt rag-server:/etc/nginx/certs/nsips-ca.crt

# rag-server 側で
ls -la /etc/nginx/certs/nsips-ca.crt
# 存在確認 (owner root, mode 644 で OK)
```

## Nginx 追加

既存の `kumatool.duckdns.org` 設定 (`/etc/nginx/conf.d/kumatool.conf` 等) の **server ブロック内** に:

```nginx
# mTLS のための CA 指定 (optional にして他 location への影響を無くす)
ssl_client_certificate /etc/nginx/certs/nsips-ca.crt;
ssl_verify_client optional;
```

さらに location を追加:

```nginx
location /nsips-stats/ {
    # mTLS 検証: 有効な client cert 無しは 403
    if ($ssl_client_verify != SUCCESS) {
        return 403 "client cert required";
    }

    proxy_pass http://127.0.0.1:18821/;
    proxy_set_header X-API-Token $http_x_api_token;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 60s;
}
```

適用:
```bash
nginx -t && systemctl reload nginx
```

外部から確認 (証明書なし → 403 を期待):
```bash
curl -H "X-API-Token: <token>" https://kumatool.duckdns.org/nsips-stats/health
# → 403 "client cert required"
```

外部から確認 (証明書あり → 200 を期待):
```bash
curl -H "X-API-Token: <token>" \
     --cert ~/dev/nsips-stats-api/deploy/certs/client-test-macos.crt \
     --key ~/dev/nsips-stats-api/deploy/certs/client-test-macos.key \
     https://kumatool.duckdns.org/nsips-stats/health
# → {"status":"ok"}
```

## 更新デプロイ

```bash
ssh rag-server
cd /root/nsips-stats-api
git pull
.venv/bin/pip install -r requirements.txt
systemctl restart nsips-stats
```

## CLAUDE_CHANGES.md に記録

`/root/CLAUDE_CHANGES.md` に本デプロイ日時と Nginx 変更を追記。
```

- [ ] **Step 3: 実際にデプロイを実行**

`deploy/deploy.md` の手順を rag-server 上で人手実行 (このタスクは対話的にユーザーと進める)。

- [ ] **Step 4: コミット**

```bash
git add deploy/
git commit -m "chore: rag-server デプロイ設定 (systemd + Nginx 手順)"
git push
```

---

# Phase 2: クライアント (nsips-watcher 拡張)

## Task 12: `nsips_parser.py` — NSIPS .txt パーサー

**Files:**
- Create: `~/dev/nsips-watcher/nsips_parser.py`
- Create: `~/dev/nsips-watcher/tests/test_nsips_parser.py`
- Create: `~/dev/nsips-watcher/tests/fixtures/sample_nsips.txt`

- [ ] **Step 1: fixture ファイル作成**

`tests/fixtures/sample_nsips.txt`:

```
2,260918005395601,38,A,20260918,,20260918,20260918,0,0,0,1,2605566,14,タナベ 皮フ科医院,2520206,神奈川県相模原市中央区淵野辺3-18-5,,20,皮膚科,,,
1,タナベ,テスト 太郎,,,,,,,,,,,15bf078c-91e8-4581-a528-98b5dceaba82,0,0,0,0,0,0,0,0,0,,,
3,1,247,分1 朝食後,,,,,2,1,14,1,,2,0,0,,,,,,
4,1,1,1,6152004F2089,620006084,,7315,ビブラマイシン錠100mg,ドキシサイクリン塩酸塩 100mg,0,0,0,0,0,0,1,1,錠,0,0,0,0,1,22,,,,,,,0,0,,,0,,,,,,0
4,2,1,1,2316004F1020,612370052,,7130,ビオフェルミンR錠,耐性乳酸菌錠 6mg,0,0,0,0,0,0,1,1,錠,0,0,0,0,1,6.3,,,,2316004F1020,,,耐性乳酸菌錠 6mg,0,0,,0,,,,,,1,0
3,2,416,1日1回塗布,474,上背部・胸・上腕,474,(1),4,3,0,0,,1,0,0,,,,,
4,1,2,1,2655709N1096,621556801,,101115,ケトナゾールクリーム2%「イワキ」,ケトコナゾールクリーム 2%,0,0,0,0,0,0,30,1,g,0,0,0,0,1,12.5,,,,2655709N1096,,,ケトコナゾールクリーム 2%,0,0,,0,,,,,,1,0
7,1,470000210,調剤物価対応料,1,1
7,2,440026810,服薬管理指導料(3ヶ月以内来局なし),1,59
7,3,999999999,計量混合加算(液剤),1,45
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_nsips_parser.py`:

```python
from pathlib import Path

from nsips_parser import parse_nsips


FIXTURE = Path(__file__).parent / "fixtures" / "sample_nsips.txt"


def _load() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_returns_dict_with_expected_keys():
    result = parse_nsips(_load())
    assert set(result.keys()) == {"prescription", "drugs", "fees"}


def test_parse_extracts_prescription_from_record_2():
    result = parse_nsips(_load())
    p = result["prescription"]
    assert p["prescription_date"] == "20260918"
    assert p["clinic_code"] == "2605566"
    assert p["clinic_name"] == "タナベ 皮フ科医院"


def test_parse_drops_record_1():
    result = parse_nsips(_load())
    # 患者情報 (record 1) は一切結果に含まれない
    all_values = str(result)
    assert "テスト 太郎" not in all_values
    assert "15bf078c" not in all_values


def test_parse_extracts_all_record_4_drugs():
    result = parse_nsips(_load())
    drugs = result["drugs"]
    assert len(drugs) == 3
    d0 = drugs[0]
    assert d0["rp_no"] == "1"
    assert d0["yj_code"] == "6152004F2089"
    assert d0["name"] == "ビブラマイシン錠100mg"
    assert d0["quantity"] == 22.0
    assert d0["unit"] == "錠"
    # 3 番目 = ケトナゾール
    assert drugs[2]["yj_code"] == "2655709N1096"
    assert drugs[2]["unit"] == "g"


def test_parse_extracts_record_7_fees():
    result = parse_nsips(_load())
    fees = result["fees"]
    # record 6 は無い fixture、record 7 が 3 件
    assert len(fees) == 3
    codes = {f["code"] for f in fees}
    assert "470000210" in codes
    assert "999999999" in codes  # 計量混合加算(液剤)


def test_parse_defensive_short_line():
    # 想定より短い行 → index out of range を空文字/None で吸収
    txt = "4,1\n"  # record 4 だが 2 フィールドだけ
    result = parse_nsips(txt)
    assert result["drugs"][0]["yj_code"] is None


def test_parse_empty_input():
    result = parse_nsips("")
    assert result == {"prescription": {}, "drugs": [], "fees": []}
```

- [ ] **Step 3: テスト実行 → 失敗確認**

```bash
cd ~/dev/nsips-watcher
source .venv/bin/activate
pytest tests/test_nsips_parser.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: `nsips_parser.py` を実装**

```python
"""NSIPS .txt をレコード種別ごとにパース。record 1 (患者情報) は必ず破棄する。"""
from __future__ import annotations


def _col(fields: list[str], idx: int) -> str | None:
    """安全なフィールド取得。範囲外や空文字は None。"""
    if idx < 0 or idx >= len(fields):
        return None
    v = fields[idx].strip()
    return v if v else None


def _to_float(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _to_int(v: str | None) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def parse_nsips(body: str) -> dict:
    """NSIPS .txt 全体をパースし、record 1 を除いた辞書を返す。

    Returns:
        {
          "prescription": {"prescription_date","clinic_code","clinic_name","doctor_name"},
          "drugs": [{"rp_no","yj_code","name","quantity","unit"}, ...],
          "fees": [{"fee_type","code","name","count","points"}, ...],
        }
    """
    result: dict = {"prescription": {}, "drugs": [], "fees": []}

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split(",")
        rec = fields[0]

        if rec == "1":
            # 患者情報。**破棄**
            continue

        if rec == "2":
            result["prescription"] = {
                "prescription_date": _col(fields, 4),
                "clinic_code": _col(fields, 12),
                "clinic_name": _col(fields, 14),
                "doctor_name": None,  # 位置未確定のため MVP では None
            }

        elif rec == "4":
            result["drugs"].append(
                {
                    "rp_no": _col(fields, 2),
                    "yj_code": _col(fields, 4),
                    "name": _col(fields, 8),
                    "quantity": _to_float(_col(fields, 24)),  # 用量位置は実装で調整
                    "unit": _col(fields, 18),
                }
            )

        elif rec in ("6", "7"):
            result["fees"].append(
                {
                    "fee_type": rec,
                    "code": _col(fields, 2),
                    "name": _col(fields, 3),
                    "count": _to_int(_col(fields, 4)),
                    "points": _to_int(_col(fields, 5)),
                }
            )

        # record 3, 5 は MVP 対象外 (skip)

    return result
```

**Note**: 用量のカラム位置は nsips-validator の仕様に基づく推定。実データで合わない場合は fixture 追加で調整する。

- [ ] **Step 5: テスト実行 → 成功確認**

```bash
pytest tests/test_nsips_parser.py -v
```

Expected: 7 passed

（もし quantity が 22.0 でなく失敗する場合は、fixture の実データを目視し、カラム位置 index を調整して再実行）

- [ ] **Step 6: コミット**

```bash
git add nsips_parser.py tests/test_nsips_parser.py tests/fixtures/
git commit -m "feat(client): nsips_parser で record 1 除外 + record 2/4/6/7 パース"
```

---

## Task 13: `nsips_crypto.py` — Fernet 鍵管理

**Files:**
- Create: `~/dev/nsips-watcher/nsips_crypto.py`
- Create: `~/dev/nsips-watcher/tests/test_nsips_crypto.py`
- Modify: `~/dev/nsips-watcher/requirements.txt` (`cryptography==43.0.1` を追加)

- [ ] **Step 1: `requirements.txt` に `cryptography` を追加**

```
watchdog==5.0.3
cryptography==43.0.1
```

- [ ] **Step 2: 依存インストール**

```bash
cd ~/dev/nsips-watcher
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 3: 失敗するテストを書く**

`tests/test_nsips_crypto.py`:

```python
from pathlib import Path

from nsips_crypto import decrypt_field, encrypt_field, get_or_create_key


def test_get_or_create_key_creates_new(tmp_path):
    key_path = tmp_path / ".key"
    assert not key_path.exists()
    key = get_or_create_key(key_path)
    assert isinstance(key, bytes)
    assert key_path.exists()
    assert len(key) > 0


def test_get_or_create_key_reuses_existing(tmp_path):
    key_path = tmp_path / ".key"
    k1 = get_or_create_key(key_path)
    k2 = get_or_create_key(key_path)
    assert k1 == k2


def test_encrypt_decrypt_roundtrip(tmp_path):
    key = get_or_create_key(tmp_path / ".key")
    original = "タナベ 皮フ科医院"
    enc = encrypt_field(key, original)
    assert enc != original
    assert isinstance(enc, str)
    dec = decrypt_field(key, enc)
    assert dec == original


def test_encrypt_none_returns_none(tmp_path):
    key = get_or_create_key(tmp_path / ".key")
    assert encrypt_field(key, None) is None


def test_decrypt_none_returns_none(tmp_path):
    key = get_or_create_key(tmp_path / ".key")
    assert decrypt_field(key, None) is None


def test_decrypt_wrong_key_raises(tmp_path):
    k1 = get_or_create_key(tmp_path / "k1")
    k2 = get_or_create_key(tmp_path / "k2")
    enc = encrypt_field(k1, "secret")
    import pytest
    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        decrypt_field(k2, enc)


def test_encrypt_different_each_time(tmp_path):
    """Fernet は IV/nonce を含むので同じ平文でも毎回別の暗号文になる。"""
    key = get_or_create_key(tmp_path / ".key")
    e1 = encrypt_field(key, "same")
    e2 = encrypt_field(key, "same")
    assert e1 != e2
    assert decrypt_field(key, e1) == "same"
    assert decrypt_field(key, e2) == "same"
```

- [ ] **Step 4: テスト実行 → 失敗確認**

```bash
pytest tests/test_nsips_crypto.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 5: `nsips_crypto.py` を実装**

```python
"""Fernet 対称鍵管理と選択フィールド暗号化。"""
from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet


def get_or_create_key(key_path: Path) -> bytes:
    """鍵ファイルが存在すればロード、なければ新規生成して保存。"""
    if key_path.exists():
        return key_path.read_bytes()
    key = Fernet.generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    return key


def encrypt_field(key: bytes, plaintext: str | None) -> str | None:
    """None は None のまま。それ以外は Fernet で暗号化して URL-safe base64 文字列で返す。"""
    if plaintext is None:
        return None
    f = Fernet(key)
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_field(key: bytes, ciphertext: str | None) -> str | None:
    """None は None。それ以外は復号して UTF-8 文字列で返す。"""
    if ciphertext is None:
        return None
    f = Fernet(key)
    return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")
```

- [ ] **Step 6: テスト実行 → 成功確認**

```bash
pytest tests/test_nsips_crypto.py -v
```

Expected: 7 passed

- [ ] **Step 7: コミット**

```bash
git add nsips_crypto.py tests/test_nsips_crypto.py requirements.txt
git commit -m "feat(client): nsips_crypto で Fernet 鍵管理 + フィールド暗号/復号"
```

---

## Task 14: `stats_client.py` — HTTP クライアント

**Files:**
- Create: `~/dev/nsips-watcher/stats_client.py`
- Create: `~/dev/nsips-watcher/tests/test_stats_client.py`
- Modify: `~/dev/nsips-watcher/requirements.txt` (`httpx==0.27.2` を追加)

- [ ] **Step 1: `requirements.txt` に `httpx` を追加**

```
watchdog==5.0.3
cryptography==43.0.1
httpx==0.27.2
```

インストール:
```bash
pip install -r requirements.txt
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_stats_client.py`:

```python
import httpx
import pytest

from stats_client import StatsClient


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_post_ingest_sends_token_and_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["token"] = request.headers.get("X-API-Token")
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"status": "ok", "prescription_id": 1})

    client = StatsClient(
        base_url="https://example.test/nsips-stats",
        token="TOK",
        transport=_mock_transport(handler),
    )
    result = client.post_ingest({"source_id": "s1", "detected_at": "x", "drugs": [], "fees": []})
    assert result == {"status": "ok", "prescription_id": 1}
    assert captured["url"].endswith("/ingest")
    assert captured["token"] == "TOK"
    assert '"source_id": "s1"' in captured["body"] or '"source_id":"s1"' in captured["body"]


def test_get_drugs_returns_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/stats/drugs")
        return httpx.Response(
            200, json={"rows": [{"yj_code": "Y", "name": "A", "unit": "錠", "n": 3, "qty": 30}]}
        )

    client = StatsClient(
        base_url="https://example.test/nsips-stats", token="T",
        transport=_mock_transport(handler),
    )
    rows = client.get_drugs()
    assert rows[0]["yj_code"] == "Y"


def test_get_clinics_returns_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/stats/clinics")
        return httpx.Response(
            200, json={"rows": [{"clinic_code_enc": "E", "clinic_name_enc": "N", "n": 5}]}
        )

    client = StatsClient(
        base_url="https://example.test/nsips-stats", token="T",
        transport=_mock_transport(handler),
    )
    rows = client.get_clinics()
    assert rows[0]["n"] == 5


def test_get_mix_returns_total_and_breakdown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"total": 4, "breakdown": [{"drug_count": 2, "n": 3}]}
        )

    client = StatsClient(
        base_url="https://example.test/nsips-stats", token="T",
        transport=_mock_transport(handler),
    )
    result = client.get_mix()
    assert result["total"] == 4


def test_401_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid token"})

    client = StatsClient(
        base_url="https://example.test/nsips-stats", token="wrong",
        transport=_mock_transport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.get_drugs()
```

- [ ] **Step 3: テスト実行 → 失敗確認**

```bash
pytest tests/test_stats_client.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: `stats_client.py` を実装**

```python
"""nsips-stats-api への HTTP クライアント。"""
from __future__ import annotations

import httpx


class StatsClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        cert: tuple[str, str] | None = None,   # (cert_path, key_path) for mTLS
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        client_kwargs = dict(
            base_url=self.base_url,
            timeout=timeout,
            headers={"X-API-Token": self.token},
        )
        if transport is not None:
            client_kwargs["transport"] = transport
        if cert is not None:
            client_kwargs["cert"] = cert
        self._client = httpx.Client(**client_kwargs)

    def close(self) -> None:
        self._client.close()

    def post_ingest(self, payload: dict) -> dict:
        r = self._client.post("/ingest", json=payload)
        r.raise_for_status()
        return r.json()

    def get_drugs(self) -> list[dict]:
        r = self._client.get("/stats/drugs")
        r.raise_for_status()
        return r.json()["rows"]

    def get_clinics(self) -> list[dict]:
        r = self._client.get("/stats/clinics")
        r.raise_for_status()
        return r.json()["rows"]

    def get_mix(self) -> dict:
        r = self._client.get("/stats/mix")
        r.raise_for_status()
        return r.json()

    def get_export_prescriptions(self) -> list[dict]:
        r = self._client.get("/stats/export/prescriptions")
        r.raise_for_status()
        return r.json()["rows"]
```

- [ ] **Step 5: テスト実行 → 成功確認**

```bash
pytest tests/test_stats_client.py -v
```

Expected: 5 passed

- [ ] **Step 6: 全体テスト実行**

```bash
pytest -v
```

Expected: 全 pass (55 件超)

- [ ] **Step 7: コミット**

```bash
git add stats_client.py tests/test_stats_client.py requirements.txt
git commit -m "feat(client): stats_client (httpx) で ingest/get_drugs/get_clinics/get_mix"
```

---

## Task 15: `NsipsHandler._process` に stats 送信を統合

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`
- Create: `~/dev/nsips-watcher/tests/test_stats_integration.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_stats_integration.py`:

```python
"""NsipsHandler が検知時に stats_client.post_ingest を呼ぶことを検証。"""
import queue
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from main import NsipsHandler


def test_process_calls_post_ingest_with_encrypted_payload(tmp_path):
    base = tmp_path / "OK"
    base.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    q: queue.Queue = queue.Queue()

    src = base / "t.txt"
    src.write_bytes(
        (
            "2,x,x,x,20260918,,x,x,x,x,x,x,CLINIC01,x,タナベ 皮フ科医院,x,x,x,x,x,x,x\n"
            "1,人名,テスト 太郎,,,,,,,,,,,uuid,x\n"
            "4,1,1,1,YJ001,x,x,x,ビブラマイシン錠100mg,x,x,x,x,x,x,x,1,1,錠,x,x,x,x,x,22\n"
            "7,1,470000210,調剤物価対応料,1,1\n"
            "7,2,999999999,計量混合加算(液剤),1,45\n"
        ).encode("utf-8")
    )

    stats_client = MagicMock()
    stats_client.post_ingest.return_value = {"status": "ok", "prescription_id": 1}
    key = b"secret_key_bytes_32bytes_long___"  # placeholder; Fernet 用は base64 だが処理では bytes を渡す想定

    from cryptography.fernet import Fernet
    key = Fernet.generate_key()

    handler = NsipsHandler(
        log_dir=log_dir,
        base_dir=base,
        existing=set(),
        event_queue=q,
        stats_client=stats_client,
        crypto_key=key,
    )
    event = SimpleNamespace(src_path=str(src), dest_path=None, is_directory=False)
    handler.on_created(event)

    stats_client.post_ingest.assert_called_once()
    payload = stats_client.post_ingest.call_args[0][0]

    # 患者名 record 1 は絶対に含まれない
    assert "テスト 太郎" not in str(payload)

    # 医療機関名は平文で含まれない (暗号化されているはず)
    assert payload["clinic_name_enc"] is not None
    assert "タナベ 皮フ科医院" not in payload["clinic_name_enc"]

    # YJコードと薬品名は平文
    assert payload["drugs"][0]["yj_code"] == "YJ001"
    assert payload["drugs"][0]["name"] == "ビブラマイシン錠100mg"

    # is_mix_flag が正しく立つ
    mix_fees = [f for f in payload["fees"] if f["is_mix_flag"]]
    assert len(mix_fees) == 1


def test_process_skips_stats_when_client_is_none(tmp_path):
    """stats_client=None のときは post_ingest しない (テストや旧構成互換)。"""
    base = tmp_path / "OK"
    base.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    q: queue.Queue = queue.Queue()

    src = base / "t.txt"
    src.write_text("2,x\n4,1,1,1,YJ,x,x,x,名,x,x,x,x,x,x,x,1,1,錠,x,x,x,x,x,1\n")

    handler = NsipsHandler(
        log_dir=log_dir, base_dir=base, existing=set(), event_queue=q,
        stats_client=None, crypto_key=None,
    )
    event = SimpleNamespace(src_path=str(src), dest_path=None, is_directory=False)
    handler.on_created(event)
    # queue には ok が入るはず (既存動作)
    assert not q.empty()
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
pytest tests/test_stats_integration.py -v
```

Expected: FAIL (NsipsHandler.__init__ に stats_client/crypto_key 引数がない)

- [ ] **Step 3: `main.py` の `NsipsHandler.__init__` と `_process` を修正**

`main.py` の import 部に追加:

```python
import hashlib

from nsips_crypto import encrypt_field
from nsips_parser import parse_nsips
```

`NsipsHandler.__init__` を書き換え:

```python
    def __init__(
        self,
        log_dir: Path,
        base_dir: Path,
        existing: set[Path],
        event_queue,
        stats_client=None,
        crypto_key: bytes | None = None,
    ) -> None:
        super().__init__(
            patterns=self.patterns,
            ignore_directories=True,
            case_sensitive=False,
        )
        self.log_dir = log_dir
        self.all_log = log_dir / "all.log"
        self.base_dir = base_dir.resolve()
        self.existing = existing
        self.queue = event_queue
        self._lock = threading.Lock()
        self.stats_client = stats_client
        self.crypto_key = crypto_key
```

`_process` の末尾に追加 (既存の `self.queue.put(("ok", ...))` の直前):

```python
            # ---- Stats 送信 (追加) ----
            if self.stats_client is not None and self.crypto_key is not None:
                try:
                    parsed = parse_nsips(body)
                    payload = self._build_ingest_payload(path, ts, parsed)
                    self.stats_client.post_ingest(payload)
                except Exception:
                    append_all_log(
                        self.all_log, datetime.now(), path,
                        f"[STATS ERROR] {traceback.format_exc()}",
                    )
            # ---- Stats 送信 ここまで ----
```

同クラスに `_build_ingest_payload` メソッドを追加:

```python
    def _build_ingest_payload(self, path: Path, ts: datetime, parsed: dict) -> dict:
        k = self.crypto_key
        p = parsed["prescription"]
        source_id = hashlib.sha256(str(path).encode("utf-8")).hexdigest()

        return {
            "source_id": source_id,
            "detected_at": ts.isoformat(),
            "clinic_code_enc": encrypt_field(k, p.get("clinic_code")),
            "clinic_name_enc": encrypt_field(k, p.get("clinic_name")),
            "prescription_date_enc": encrypt_field(k, p.get("prescription_date")),
            "doctor_name_enc": encrypt_field(k, p.get("doctor_name")),
            "drugs": [
                {
                    "rp_no_enc": encrypt_field(k, d.get("rp_no")),
                    "yj_code": d.get("yj_code"),
                    "name": d.get("name"),
                    "quantity": d.get("quantity"),
                    "unit": d.get("unit"),
                }
                for d in parsed["drugs"]
            ],
            "fees": [
                {
                    "fee_type": f.get("fee_type"),
                    "code_enc": encrypt_field(k, f.get("code")),
                    "name_enc": encrypt_field(k, f.get("name")),
                    "count": f.get("count"),
                    "points": f.get("points"),
                    "is_mix_flag": "計量混合" in (f.get("name") or ""),
                }
                for f in parsed["fees"]
            ],
        }
```

- [ ] **Step 4: テスト実行 → 成功確認**

```bash
pytest tests/test_stats_integration.py -v
```

Expected: 2 passed

- [ ] **Step 5: 既存の NsipsHandler テストで回帰なし確認**

```bash
pytest tests/test_nsips_handler.py -v
```

Expected: 全 pass (既存 5 件)

- [ ] **Step 6: コミット**

```bash
git add main.py tests/test_stats_integration.py
git commit -m "feat(client): NsipsHandler に stats 送信 (record 1 除外 + 暗号化 + POST /ingest)"
```

---

## Task 16: `config.json` 拡張 + 初期セットアップダイアログ

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`

- [ ] **Step 1: `NsipsWatcherApp.__init__` に stats 初期化を追加**

`main.py` の `main()` 関数内 `NsipsWatcherApp.__init__` を以下で拡張。既存の `self.cfg_path = config_path()` の直後に:

```python
            # ---- Stats 設定 (追加) ----
            from nsips_crypto import get_or_create_key
            from stats_client import StatsClient

            self.crypto_key = get_or_create_key(app_dir() / ".key")
            self.stats_client: StatsClient | None = None
            self._init_stats_client()
```

同 `NsipsWatcherApp` クラスに新メソッド追加 (open_log_folder の下あたり):

```python
        def _init_stats_client(self) -> None:
            cfg = load_config(self.cfg_path)
            url = cfg.get("api_base_url")
            token = cfg.get("api_token")
            cert_path = cfg.get("client_cert_path")
            key_path = cfg.get("client_key_path")
            missing = []
            if not url:
                missing.append("api_base_url")
            if not token:
                missing.append("api_token")
            if not cert_path or not Path(cert_path).is_file():
                missing.append("client_cert_path (mTLS 証明書)")
            if not key_path or not Path(key_path).is_file():
                missing.append("client_key_path (mTLS 秘密鍵)")
            if missing:
                messagebox.showinfo(
                    "API 設定",
                    "config.json に以下を設定してください:\n\n"
                    + "\n".join(f"- {m}" for m in missing)
                    + "\n\n統計送信はスキップされます。",
                    parent=self.root,
                )
                return
            self.stats_client = StatsClient(
                base_url=url,
                token=token,
                cert=(cert_path, key_path),
            )
```

さらに `_start_observer` を修正、`NsipsHandler` に stats_client/crypto_key を渡す:

```python
                self.handler = NsipsHandler(
                    self.log_dir, base, self.existing, self.event_queue,
                    stats_client=self.stats_client,
                    crypto_key=self.crypto_key,
                )
```

- [ ] **Step 2: `quit_app` で stats_client.close() を呼ぶ**

```python
        def quit_app(self) -> None:
            self._stop_observer()
            if self.stats_client is not None:
                self.stats_client.close()
            self.root.destroy()
```

- [ ] **Step 3: import 確認 + 全テスト実行**

```bash
python3 -c "import main; print('ok')"
pytest -v
```

Expected: `ok` + 全 pass

- [ ] **Step 4: コミット**

```bash
git add main.py
git commit -m "feat(client): config.json 拡張 + StatsClient 初期化 + .key 自動生成"
```

---

## Task 17: GUI に Notebook 移行 (タブ 1 = 既存 ScrolledText)

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`

- [ ] **Step 1: `_build_ui` を書き換え**

`main()` 関数内 `NsipsWatcherApp._build_ui` の既存 ScrolledText 生成部分を以下で置き換え:

```python
        def _build_ui(self) -> None:
            self.root.title("nsips-watcher")
            self.root.geometry("1000x700")

            menubar = tk.Menu(self.root)
            filemenu = tk.Menu(menubar, tearoff=0)
            filemenu.add_command(label="監視パスを変更(P)", command=self.change_base_dir)
            filemenu.add_command(label="ログフォルダを開く(L)", command=self.open_log_folder)
            filemenu.add_separator()
            filemenu.add_command(label="終了(X)", command=self.quit_app)
            menubar.add_cascade(label="ファイル(F)", menu=filemenu)
            self.root.config(menu=menubar)

            self.status_var = tk.StringVar(value="監視中: (未設定)")
            status = tk.Label(self.root, textvariable=self.status_var, anchor="w")
            status.pack(fill="x", padx=8, pady=4)

            from tkinter import ttk
            self.notebook = ttk.Notebook(self.root)
            self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))

            # タブ 1: 最新検知
            tab_latest = tk.Frame(self.notebook)
            self.text = scrolledtext.ScrolledText(
                tab_latest, wrap="word", font=("Consolas", 11), state="normal",
            )
            self.text.pack(fill="both", expand=True)
            self.notebook.add(tab_latest, text="最新検知")
            self._show_body("info", None, None, "監視待機中...")
            self.text.config(state="disabled")

            self.root.protocol("WM_DELETE_WINDOW", self.quit_app)
```

- [ ] **Step 2: import + テスト**

```bash
python3 -c "import main; print('ok')"
pytest -v
```

- [ ] **Step 3: コミット**

```bash
git add main.py
git commit -m "feat(client): ScrolledText を ttk.Notebook のタブ 1 (最新検知) にラップ"
```

---

## Task 18: タブ 2 「薬剤別累計」Treeview

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`

- [ ] **Step 1: `_build_ui` の末尾に タブ 2 追加**

`self.notebook.add(tab_latest, text="最新検知")` の後に:

```python
            # タブ 2: 薬剤別累計
            tab_drugs = tk.Frame(self.notebook)
            self.tree_drugs = ttk.Treeview(
                tab_drugs,
                columns=("yj", "name", "n", "qty", "unit"),
                show="headings",
            )
            for col, heading, w in [
                ("yj", "YJコード", 130),
                ("name", "薬品名", 300),
                ("n", "調剤回数", 80),
                ("qty", "総数量", 100),
                ("unit", "単位", 80),
            ]:
                self.tree_drugs.heading(col, text=heading)
                self.tree_drugs.column(col, width=w, anchor="w")
            self.tree_drugs.pack(fill="both", expand=True)
            self.notebook.add(tab_drugs, text="薬剤別累計")
```

- [ ] **Step 2: `refresh_drugs_tab` メソッドを追加**

`NsipsWatcherApp` クラスに:

```python
        def refresh_drugs_tab(self) -> None:
            if self.stats_client is None:
                return
            try:
                rows = self.stats_client.get_drugs()
            except Exception:
                return
            self.tree_drugs.delete(*self.tree_drugs.get_children())
            for r in rows:
                self.tree_drugs.insert(
                    "", "end",
                    values=(r.get("yj_code") or "", r.get("name") or "",
                            r.get("n") or 0, r.get("qty") or 0, r.get("unit") or ""),
                )
```

- [ ] **Step 3: タブ切替と検知時の再描画**

`_poll_queue` を修正:

```python
        def _poll_queue(self) -> None:
            need_refresh = False
            try:
                while True:
                    kind, ts, path, body = self.event_queue.get_nowait()
                    if kind == "stats_updated":
                        need_refresh = True
                    else:
                        self._show_body(kind, ts, path, body)
                        need_refresh = True
            except queue.Empty:
                pass
            if need_refresh:
                self._refresh_current_tab()
            self.root.after(200, self._poll_queue)

        def _refresh_current_tab(self) -> None:
            idx = self.notebook.index("current")
            if idx == 1:
                self.refresh_drugs_tab()

        def _on_tab_changed(self, event) -> None:
            self._refresh_current_tab()
```

`_build_ui` の末尾 (return 前) に:

```python
            self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
```

- [ ] **Step 4: コミット**

```bash
git add main.py
git commit -m "feat(client): タブ 2 薬剤別累計 (Treeview + get_drugs 定期更新)"
```

---

## Task 19: タブ 3 「医療機関別」+ クライアント側復号

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`

- [ ] **Step 1: `_build_ui` にタブ 3 を追加**

タブ 2 追加コードの直下に:

```python
            # タブ 3: 医療機関別
            tab_clinics = tk.Frame(self.notebook)
            self.tree_clinics = ttk.Treeview(
                tab_clinics,
                columns=("code", "name", "n"),
                show="headings",
            )
            for col, heading, w in [
                ("code", "医療機関コード", 150),
                ("name", "医療機関名", 400),
                ("n", "件数", 80),
            ]:
                self.tree_clinics.heading(col, text=heading)
                self.tree_clinics.column(col, width=w, anchor="w")
            self.tree_clinics.pack(fill="both", expand=True)
            self.notebook.add(tab_clinics, text="医療機関別")
```

- [ ] **Step 2: `refresh_clinics_tab` を追加**

```python
        def refresh_clinics_tab(self) -> None:
            if self.stats_client is None:
                return
            from nsips_crypto import decrypt_field
            try:
                rows = self.stats_client.get_clinics()
            except Exception:
                return
            self.tree_clinics.delete(*self.tree_clinics.get_children())
            for r in rows:
                try:
                    code = decrypt_field(self.crypto_key, r.get("clinic_code_enc")) or ""
                    name = decrypt_field(self.crypto_key, r.get("clinic_name_enc")) or ""
                except Exception:
                    code = "[decrypt error]"
                    name = "[decrypt error]"
                self.tree_clinics.insert("", "end", values=(code, name, r.get("n") or 0))
```

- [ ] **Step 3: `_refresh_current_tab` に分岐を追加**

```python
        def _refresh_current_tab(self) -> None:
            idx = self.notebook.index("current")
            if idx == 1:
                self.refresh_drugs_tab()
            elif idx == 2:
                self.refresh_clinics_tab()
```

- [ ] **Step 4: コミット**

```bash
git add main.py
git commit -m "feat(client): タブ 3 医療機関別 (Treeview + クライアント側 Fernet 復号)"
```

---

## Task 20: タブ 4 「計量混合加算」

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`

- [ ] **Step 1: `_build_ui` にタブ 4 追加**

タブ 3 の後に:

```python
            # タブ 4: 計量混合加算
            tab_mix = tk.Frame(self.notebook)
            self.mix_total_var = tk.StringVar(value="計量混合加算がついた処方: -")
            tk.Label(tab_mix, textvariable=self.mix_total_var, font=("Meiryo", 12)).pack(anchor="w", padx=8, pady=8)
            self.tree_mix = ttk.Treeview(
                tab_mix, columns=("cnt", "n"), show="headings",
            )
            for col, heading, w in [
                ("cnt", "混合品目数", 120),
                ("n", "該当件数", 120),
            ]:
                self.tree_mix.heading(col, text=heading)
                self.tree_mix.column(col, width=w, anchor="center")
            self.tree_mix.pack(fill="both", expand=True, padx=8, pady=8)
            self.notebook.add(tab_mix, text="計量混合加算")
```

- [ ] **Step 2: `refresh_mix_tab` メソッドを追加**

```python
        def refresh_mix_tab(self) -> None:
            if self.stats_client is None:
                return
            try:
                result = self.stats_client.get_mix()
            except Exception:
                return
            self.mix_total_var.set(f"計量混合加算がついた処方: {result.get('total', 0)} 件")
            self.tree_mix.delete(*self.tree_mix.get_children())
            for row in result.get("breakdown", []):
                self.tree_mix.insert(
                    "", "end", values=(f"{row['drug_count']} 品目", row["n"]),
                )
```

- [ ] **Step 3: `_refresh_current_tab` に分岐追加**

```python
            elif idx == 3:
                self.refresh_mix_tab()
```

- [ ] **Step 4: コミット**

```bash
git add main.py
git commit -m "feat(client): タブ 4 計量混合加算 (総件数ラベル + 品目数別内訳 Treeview)"
```

---

## Task 21: タブ 5 「エクスポート」CSV 保存

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`

- [ ] **Step 1: `_build_ui` にタブ 5 追加**

```python
            # タブ 5: エクスポート
            tab_export = tk.Frame(self.notebook)
            tk.Button(
                tab_export, text="薬剤別累計を CSV 保存",
                command=self.export_drugs_csv, width=30,
            ).pack(pady=8, padx=8, anchor="w")
            tk.Button(
                tab_export, text="医療機関別を CSV 保存",
                command=self.export_clinics_csv, width=30,
            ).pack(pady=8, padx=8, anchor="w")
            tk.Button(
                tab_export, text="全 prescriptions を CSV 保存",
                command=self.export_prescriptions_csv, width=30,
            ).pack(pady=8, padx=8, anchor="w")
            self.notebook.add(tab_export, text="エクスポート")
```

- [ ] **Step 2: CSV 保存メソッドを追加**

```python
        def _save_csv(self, default_name: str, header: list[str], rows: list[list]) -> None:
            import csv
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                initialfile=default_name,
                filetypes=[("CSV", "*.csv")],
                parent=self.root,
            )
            if not path:
                return
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(header)
                for row in rows:
                    w.writerow(row)
            messagebox.showinfo("保存完了", f"保存しました:\n{path}", parent=self.root)

        def export_drugs_csv(self) -> None:
            if self.stats_client is None:
                return
            try:
                rows = self.stats_client.get_drugs()
            except Exception as e:
                messagebox.showerror("エラー", f"取得失敗: {e}", parent=self.root)
                return
            data = [[r.get("yj_code") or "", r.get("name") or "",
                     r.get("unit") or "", r.get("n") or 0, r.get("qty") or 0]
                    for r in rows]
            self._save_csv("drugs.csv", ["YJコード", "薬品名", "単位", "調剤回数", "総数量"], data)

        def export_clinics_csv(self) -> None:
            if self.stats_client is None:
                return
            from nsips_crypto import decrypt_field
            try:
                rows = self.stats_client.get_clinics()
            except Exception as e:
                messagebox.showerror("エラー", f"取得失敗: {e}", parent=self.root)
                return
            data = []
            for r in rows:
                try:
                    code = decrypt_field(self.crypto_key, r.get("clinic_code_enc")) or ""
                    name = decrypt_field(self.crypto_key, r.get("clinic_name_enc")) or ""
                except Exception:
                    code, name = "[decrypt error]", "[decrypt error]"
                data.append([code, name, r.get("n") or 0])
            self._save_csv("clinics.csv", ["医療機関コード", "医療機関名", "件数"], data)

        def export_prescriptions_csv(self) -> None:
            if self.stats_client is None:
                return
            from nsips_crypto import decrypt_field
            try:
                rows = self.stats_client.get_export_prescriptions()
            except Exception as e:
                messagebox.showerror("エラー", f"取得失敗: {e}", parent=self.root)
                return
            data = []
            for r in rows:
                def _dec(v):
                    try:
                        return decrypt_field(self.crypto_key, v) or ""
                    except Exception:
                        return "[decrypt error]"
                data.append([
                    r.get("id"), r.get("source_id"), r.get("detected_at"),
                    _dec(r.get("clinic_code_enc")), _dec(r.get("clinic_name_enc")),
                    _dec(r.get("prescription_date_enc")), _dec(r.get("doctor_name_enc")),
                ])
            self._save_csv(
                "prescriptions.csv",
                ["id", "source_id", "detected_at", "医療機関コード", "医療機関名", "処方日", "医師名"],
                data,
            )
```

- [ ] **Step 3: コミット**

```bash
git add main.py
git commit -m "feat(client): タブ 5 エクスポート (drugs/clinics/prescriptions を CSV 保存)"
```

---

## Task 22: MEMORY.md 更新 + push

- [ ] **Step 1: `~/.claude/projects/-Users-a/memory/nsips-watcher.md` の状態欄を更新** (統計機能追加を反映)

- [ ] **Step 2: `~/.claude/projects/-Users-a/memory/nsips-stats-api.md` を新規作成**

- [ ] **Step 3: `~/.claude/projects/-Users-a/memory/MEMORY.md` に `nsips-stats-api` を 1 行追加**

- [ ] **Step 4: `~/dev/nsips-watcher/` 側を push**

```bash
cd ~/dev/nsips-watcher
git push
```

---

# Phase 3: 統合手動確認

## Task 23: Windows PC + rag-server 統合手動確認

- [ ] **Step 1: サーバー疎通 (mTLS 検証込み)**

```bash
# 証明書なしで 403 を確認
curl -H "X-API-Token: <token>" https://kumatool.duckdns.org/nsips-stats/health
# → 403 "client cert required"

# 証明書付きで 200 を確認
curl -H "X-API-Token: <token>" \
     --cert ~/dev/nsips-stats-api/deploy/certs/client-test-macos.crt \
     --key ~/dev/nsips-stats-api/deploy/certs/client-test-macos.key \
     https://kumatool.duckdns.org/nsips-stats/health
# → {"status":"ok"}
```

- [ ] **Step 1.5: 薬局 PC 用の証明書を発行 + USB で配布**

```bash
# 開発者 macOS で
cd ~/dev/nsips-stats-api
./deploy/gen_certs.sh client solamichi-pc
# → deploy/certs/client-solamichi-pc.crt + .key
```

USB に `client-solamichi-pc.crt` と `client-solamichi-pc.key` をコピーして薬局 PC の `C:\nsips-watcher\` にコピー配置。

- [ ] **Step 2: 薬局 PC で最新版を pull + 依存更新**

```powershell
cd nsips-watcher
git pull
pip install -r requirements-dev.txt
```

- [ ] **Step 3: `config.json` に api + mTLS 設定を追記**

```json
{
  "base_dir": "C:\\solamichi\\solamichiclient\\client\\LOG\\NSIPS\\OK",
  "api_base_url": "https://kumatool.duckdns.org/nsips-stats",
  "api_token": "<token>",
  "client_cert_path": "C:\\nsips-watcher\\client-solamichi-pc.crt",
  "client_key_path": "C:\\nsips-watcher\\client-solamichi-pc.key"
}
```

- [ ] **Step 4: 起動 + テスト .txt 検知**

```powershell
python main.py
```

新規 .txt を作成 → タブ 1「最新検知」に内容表示、タブ 2 が更新される。

- [ ] **Step 5: タブ 2-4 の内容が正しいか確認**

- タブ 2: 薬剤名/YJコード/回数/数量 が入っている
- タブ 3: 医療機関名がクライアント側で復号されて表示される
- タブ 4: 計量混合加算件数と品目数内訳が出る

- [ ] **Step 6: タブ 5 の CSV エクスポート 3 種類 → Excel で開けること**

- [ ] **Step 7: `.key` バックアップ確認**

`nsips-watcher\.key` が生成されている。USB や Google Drive にコピーする運用手順をユーザーに案内。

- [ ] **Step 8: README に確認結果を追記して push**

---

## 完了基準

- Phase 1 の全 Task の全 Step チェック済み、`pytest -v` で全 pass (~40 件)
- Phase 2 の全 Task の全 Step チェック済み、`pytest -v` で全 pass (~65 件)
- Phase 3 で Windows PC + rag-server 統合確認完了
- `nsips-stats-api` GitHub public リポジトリに push 済み
- rag-server 上で `nsips-stats.service` が active
- Nginx リバースプロキシ設定済み
