# nsips-watcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** solamichi クライアントが `C:\solamichi\solamichiclient\client\LOG\NSIPS\OK\` 直下に出力する成功ログ `.txt` を監視し、tkinter GUI に最新内容を表示しつつ `logs\all.log` 追記 + 原本コピーを行う Windows GUI アプリを作る。

**Architecture:** Python 3.11 + watchdog（監視）+ tkinter（GUI、標準ライブラリ）+ PyInstaller（単一 .exe 化）。純粋ロジックは `core.py` に集約し、sips-watcher (`~/dev/sips-watcher/core.py`) からそのままコピーして再利用。Handler は observer スレッドで動き、GUI へは `queue.Queue` 経由で受け渡し、tkinter は `root.after(200, poll)` でポーリング。

**Tech Stack:** Python 3.11, watchdog 5.0.3, tkinter (stdlib), pytest 8.3.3, PyInstaller 6.10.0

**Related spec:** `docs/superpowers/specs/2026-09-18-nsips-watcher-design.md`
**Related project:** `~/dev/sips-watcher/` — `core.py` を丸ごと流用

---

## Task 1: プロジェクトスケルトン整備

**Files:**
- Create: `~/dev/nsips-watcher/.gitignore`
- Create: `~/dev/nsips-watcher/requirements.txt`
- Create: `~/dev/nsips-watcher/requirements-dev.txt`
- Create: `~/dev/nsips-watcher/README.md`
- Create: `~/dev/nsips-watcher/tests/__init__.py`

- [ ] **Step 1: `.gitignore` を作成**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
build/
dist/
*.spec
.DS_Store
logs/
config.json
```

- [ ] **Step 2: `requirements.txt` を作成**

```
watchdog==5.0.3
```

- [ ] **Step 3: `requirements-dev.txt` を作成**

```
-r requirements.txt
pytest==8.3.3
pyinstaller==6.10.0
```

- [ ] **Step 4: `README.md` を作成**

```markdown
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
```

- [ ] **Step 5: `tests/__init__.py` を空ファイルとして作成**

```
```

- [ ] **Step 6: venv を作って依存インストール、pytest が起動できることを確認**

```bash
cd ~/dev/nsips-watcher
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest --collect-only
```

Expected: pytest が起動し `collected 0 items` を出す

- [ ] **Step 7: コミット**

```bash
cd ~/dev/nsips-watcher
git add .gitignore requirements.txt requirements-dev.txt README.md tests/__init__.py
git commit -m "chore: プロジェクトスケルトン (deps, gitignore, README)"
```

---

## Task 2: `core.py` を sips-watcher からコピー + 全 core テストを移植

sips-watcher の `core.py` は Windows 依存なしの純粋関数群。そのまま流用し、テストも移植して全通ることを確認する。

**Files:**
- Create: `~/dev/nsips-watcher/core.py` (sips-watcher の同ファイルをコピー)
- Create: `~/dev/nsips-watcher/tests/test_core.py` (sips-watcher の core 系テストを 1 ファイルに集約)

- [ ] **Step 1: `core.py` をコピー**

```bash
cp ~/dev/sips-watcher/core.py ~/dev/nsips-watcher/core.py
```

- [ ] **Step 2: `tests/test_core.py` を作成** (sips-watcher の該当テストを 1 ファイルに集約)

```python
"""core.py のテスト。sips-watcher と共通。"""
from datetime import datetime
from pathlib import Path

from core import (
    append_all_log,
    copy_backup,
    decode_auto,
    load_config,
    save_config,
    snapshot_existing,
    unique_dest_path,
    wait_for_stable_size,
    wait_for_unlock,
)


# --- decode_auto ---

def test_decode_utf8():
    assert decode_auto("こんにちは".encode("utf-8")) == "こんにちは"


def test_decode_cp932():
    assert decode_auto("こんにちは".encode("cp932")) == "こんにちは"


def test_decode_binary_fallback_to_latin1():
    result = decode_auto(bytes([0xff, 0xfe, 0x80, 0x81]))
    assert isinstance(result, str)
    assert len(result) == 4


def test_decode_empty():
    assert decode_auto(b"") == ""


# --- snapshot_existing ---

def test_snapshot_empty_dir(tmp_path):
    assert snapshot_existing([tmp_path]) == set()


def test_snapshot_recursive(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("b")
    (sub / "c.bin").write_text("c")
    result = snapshot_existing([tmp_path])
    assert result == {(tmp_path / "a.txt").resolve(), (sub / "b.txt").resolve()}


def test_snapshot_multiple_roots(tmp_path):
    r1 = tmp_path / "R1"
    r2 = tmp_path / "R2"
    r1.mkdir()
    r2.mkdir()
    (r1 / "1.txt").write_text("1")
    (r2 / "2.txt").write_text("2")
    assert snapshot_existing([r1, r2]) == {
        (r1 / "1.txt").resolve(),
        (r2 / "2.txt").resolve(),
    }


def test_snapshot_missing_root_is_ignored(tmp_path):
    exists = tmp_path / "e"
    exists.mkdir()
    (exists / "x.txt").write_text("x")
    missing = tmp_path / "missing"
    assert snapshot_existing([exists, missing]) == {(exists / "x.txt").resolve()}


# --- append_all_log ---

def test_append_creates_file(tmp_path):
    log = tmp_path / "all.log"
    ts = datetime(2026, 9, 18, 10, 39, 12, 123000)
    append_all_log(log, ts, Path("C:/foo/a.txt"), "本文A")
    assert log.read_text(encoding="utf-8") == (
        "[2026-09-18 10:39:12.123] C:/foo/a.txt\n"
        "本文A\n"
        "---\n"
    )


def test_append_appends_not_overwrites(tmp_path):
    log = tmp_path / "all.log"
    ts1 = datetime(2026, 9, 18, 10, 39, 12, 123000)
    ts2 = datetime(2026, 9, 18, 10, 40, 0, 5000)
    append_all_log(log, ts1, Path("a"), "AAA")
    append_all_log(log, ts2, Path("b"), "BBB")
    c = log.read_text(encoding="utf-8")
    assert "AAA\n" in c and "BBB\n" in c
    assert c.index("AAA") < c.index("BBB")
    assert c.count("---\n") == 2


def test_append_creates_parent_dir(tmp_path):
    log = tmp_path / "sub" / "all.log"
    ts = datetime(2026, 9, 18, 10, 39, 12, 123000)
    append_all_log(log, ts, Path("x"), "X")
    assert log.exists()


def test_append_handles_non_ascii(tmp_path):
    log = tmp_path / "all.log"
    ts = datetime(2026, 9, 18, 10, 39, 12, 123000)
    append_all_log(log, ts, Path("日本語.txt"), "内容\n改行あり")
    c = log.read_text(encoding="utf-8")
    assert "日本語.txt" in c
    assert "内容\n改行あり\n" in c


# --- unique_dest_path ---

def test_no_conflict_returns_same_path(tmp_path):
    p = tmp_path / "x.txt"
    assert unique_dest_path(p) == p


def test_single_conflict_appends_2(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("e")
    assert unique_dest_path(p) == tmp_path / "x_2.txt"


def test_multiple_conflicts_increment(tmp_path):
    base = tmp_path / "x.txt"
    base.write_text("1")
    (tmp_path / "x_2.txt").write_text("2")
    (tmp_path / "x_3.txt").write_text("3")
    assert unique_dest_path(base) == tmp_path / "x_4.txt"


def test_no_extension(tmp_path):
    p = tmp_path / "noext"
    p.write_text("e")
    assert unique_dest_path(p) == tmp_path / "noext_2"


# --- copy_backup ---

def test_copy_basic(tmp_path):
    src = tmp_path / "src.txt"
    src.write_bytes(b"hello")
    log_dir = tmp_path / "logs"
    ts = datetime(2026, 9, 18, 10, 39, 12, 123000)
    dest = copy_backup(src, log_dir, "OK", ts)
    assert dest == log_dir / "OK" / "20260918_103912_123_src.txt"
    assert dest.read_bytes() == b"hello"


def test_copy_creates_subdir(tmp_path):
    src = tmp_path / "x.txt"
    src.write_bytes(b"x")
    log_dir = tmp_path / "logs"
    ts = datetime(2026, 9, 18, 10, 39, 12, 0)
    dest = copy_backup(src, log_dir, "OK", ts)
    assert (log_dir / "OK").is_dir()
    assert dest.exists()


def test_copy_preserves_binary(tmp_path):
    src = tmp_path / "bin.txt"
    payload = bytes(range(256))
    src.write_bytes(payload)
    log_dir = tmp_path / "logs"
    ts = datetime(2026, 9, 18, 10, 39, 12, 0)
    dest = copy_backup(src, log_dir, "OK", ts)
    assert dest.read_bytes() == payload


def test_copy_avoids_name_collision(tmp_path):
    src = tmp_path / "same.txt"
    src.write_bytes(b"A")
    log_dir = tmp_path / "logs"
    ts = datetime(2026, 9, 18, 10, 39, 12, 123000)
    first = copy_backup(src, log_dir, "OK", ts)
    src.write_bytes(b"B")
    second = copy_backup(src, log_dir, "OK", ts)
    assert first.name == "20260918_103912_123_same.txt"
    assert second.name == "20260918_103912_123_same_2.txt"
    assert first.read_bytes() == b"A"
    assert second.read_bytes() == b"B"


# --- wait_for_unlock ---

def test_readable_file_returns_true(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"ok")
    assert wait_for_unlock(p, max_retries=3, interval=0.01) is True


def test_missing_file_returns_false(tmp_path):
    p = tmp_path / "nope.txt"
    assert wait_for_unlock(p, max_retries=3, interval=0.01) is False


def test_retries_configured_number_of_times(tmp_path, monkeypatch):
    p = tmp_path / "b.txt"
    calls = {"n": 0}

    def fake_sleep(_):
        calls["n"] += 1

    monkeypatch.setattr("core.time.sleep", fake_sleep)
    assert wait_for_unlock(p, max_retries=5, interval=0.5) is False
    assert calls["n"] == 4


# --- wait_for_stable_size ---

def test_stable_file_returns_true(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"stable")
    assert wait_for_stable_size(p, checks=3, interval=0.01) is True


def test_missing_size_returns_false(tmp_path):
    assert wait_for_stable_size(tmp_path / "nope.txt", checks=3, interval=0.01) is False


def test_growing_then_stable(tmp_path, monkeypatch):
    p = tmp_path / "b.txt"
    p.write_bytes(b"1")
    sleep_calls = {"n": 0}
    sizes = [1, 2, 3, 5, 5, 5]

    def fake_sleep(_):
        sleep_calls["n"] += 1
        idx = sleep_calls["n"]
        if idx < len(sizes):
            p.write_bytes(b"x" * sizes[idx])

    monkeypatch.setattr("core.time.sleep", fake_sleep)
    assert wait_for_stable_size(p, checks=3, interval=0.01) is True


def test_forever_growing_returns_false(tmp_path, monkeypatch):
    p = tmp_path / "c.txt"
    p.write_bytes(b"1")
    counter = {"n": 1}

    def fake_sleep(_):
        counter["n"] += 1
        p.write_bytes(b"x" * counter["n"])

    monkeypatch.setattr("core.time.sleep", fake_sleep)
    assert wait_for_stable_size(p, checks=3, interval=0.01, max_polls=10) is False


# --- load_config / save_config ---

def test_load_config_missing_returns_empty(tmp_path):
    assert load_config(tmp_path / "config.json") == {}


def test_save_and_load_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    save_config(p, {"base_dir": "C:\\Sanyo"})
    assert load_config(p) == {"base_dir": "C:\\Sanyo"}


def test_load_config_broken_json_returns_empty(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("not json")
    assert load_config(p) == {}


def test_save_config_creates_parent_dir(tmp_path):
    p = tmp_path / "sub" / "config.json"
    save_config(p, {"base_dir": "D:\\Data"})
    assert p.exists()


def test_save_config_uses_utf8(tmp_path):
    p = tmp_path / "config.json"
    save_config(p, {"base_dir": "C:\\日本語\\監視"})
    assert load_config(p) == {"base_dir": "C:\\日本語\\監視"}
```

- [ ] **Step 3: テスト実行 → 全 pass 確認**

```bash
cd ~/dev/nsips-watcher
source .venv/bin/activate
pytest tests/test_core.py -v
```

Expected: 全 27+ 件 pass (decode 4 + snapshot 4 + append 4 + unique 4 + copy 4 + wait_unlock 3 + wait_stable 4 + config 5 = 32 件程度)

- [ ] **Step 4: コミット**

```bash
git add core.py tests/test_core.py
git commit -m "feat(core): sips-watcher から core.py を複製、全テスト移植"
```

---

## Task 3: `main.py` にヘルパー関数を実装 (app_dir, config_path, resolve_base_dir)

GUI 実装の前に、テスト可能なヘルパー関数を切り出す。

**Files:**
- Create: `~/dev/nsips-watcher/main.py` (雛形)
- Create: `~/dev/nsips-watcher/tests/test_main_helpers.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_main_helpers.py`:

```python
from pathlib import Path

from core import save_config
from main import resolve_base_dir


def test_resolve_prefers_valid_config(tmp_path):
    cfg = tmp_path / "config.json"
    saved = tmp_path / "custom"
    saved.mkdir()
    save_config(cfg, {"base_dir": str(saved)})

    default = tmp_path / "default"
    default.mkdir()

    assert resolve_base_dir(cfg, default) == saved


def test_resolve_falls_back_to_default_when_config_missing(tmp_path):
    cfg = tmp_path / "config.json"
    default = tmp_path / "default"
    default.mkdir()
    assert resolve_base_dir(cfg, default) == default


def test_resolve_falls_back_when_config_path_not_dir(tmp_path):
    cfg = tmp_path / "config.json"
    save_config(cfg, {"base_dir": str(tmp_path / "missing")})
    default = tmp_path / "default"
    default.mkdir()
    assert resolve_base_dir(cfg, default) == default


def test_resolve_falls_back_when_config_path_is_empty_string(tmp_path):
    cfg = tmp_path / "config.json"
    save_config(cfg, {"base_dir": ""})
    default = tmp_path / "default"
    default.mkdir()
    assert resolve_base_dir(cfg, default) == default


def test_resolve_falls_back_when_config_path_is_file(tmp_path):
    cfg = tmp_path / "config.json"
    file_not_dir = tmp_path / "somefile.txt"
    file_not_dir.write_text("x")
    save_config(cfg, {"base_dir": str(file_not_dir)})
    default = tmp_path / "default"
    default.mkdir()
    assert resolve_base_dir(cfg, default) == default


def test_resolve_returns_none_when_both_invalid(tmp_path):
    cfg = tmp_path / "config.json"  # no file
    default = tmp_path / "missing"  # doesn't exist
    assert resolve_base_dir(cfg, default) is None
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
pytest tests/test_main_helpers.py -v
```

Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: `main.py` を作成 (ヘルパー関数のみ)**

```python
"""nsips-watcher エントリポイント。solamichi クライアントの NSIPS/OK 出力を監視する。"""
from __future__ import annotations

import sys
from pathlib import Path

from core import load_config

DEFAULT_BASE_DIR = Path(r"C:\solamichi\solamichiclient\client\LOG\NSIPS\OK")


def app_dir() -> Path:
    """.exe 実行時は sys.executable の親、開発実行時は main.py の親を返す。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def config_path() -> Path:
    return app_dir() / "config.json"


def resolve_base_dir(cfg_path: Path, default_base: Path) -> Path | None:
    """config → default の順で is_dir() を満たすパスを返す。両方 NG なら None。"""
    cfg = load_config(cfg_path)
    saved = cfg.get("base_dir")
    if isinstance(saved, str) and saved:
        p = Path(saved)
        if p.is_dir():
            return p
    if default_base.is_dir():
        return default_base
    return None
```

- [ ] **Step 4: テスト実行 → 成功確認**

```bash
pytest tests/test_main_helpers.py -v
```

Expected: 6 passed

- [ ] **Step 5: コミット**

```bash
git add main.py tests/test_main_helpers.py
git commit -m "feat: main.py に resolve_base_dir 等のヘルパーを実装"
```

---

## Task 4: `NsipsHandler` クラス実装 (watchdog + queue)

Handler は observer スレッドで動き、ファイル処理を完結させ、GUI に渡す情報を queue に put する。

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`
- Create: `~/dev/nsips-watcher/tests/test_nsips_handler.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_nsips_handler.py`:

```python
"""NsipsHandler の統合テスト。実 watchdog は使わず _process を直接呼ぶ。"""
import queue
from pathlib import Path
from types import SimpleNamespace

from main import NsipsHandler


def _make_handler(tmp_path: Path):
    base = tmp_path / "OK"
    base.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    q: queue.Queue = queue.Queue()
    handler = NsipsHandler(log_dir, base, existing=set(), event_queue=q)
    return handler, base, log_dir, q


def test_on_created_puts_ok_and_appends(tmp_path):
    handler, base, log_dir, q = _make_handler(tmp_path)
    src = base / "abc.txt"
    src.write_bytes("こんにちは".encode("cp932"))

    event = SimpleNamespace(src_path=str(src), dest_path=None, is_directory=False)
    handler.on_created(event)

    kind, _ts, _path, body = q.get_nowait()
    assert kind == "ok"
    assert body == "こんにちは"
    assert "こんにちは" in (log_dir / "all.log").read_text(encoding="utf-8")
    copies = list((log_dir / "OK").glob("*_abc.txt"))
    assert len(copies) == 1
    assert copies[0].read_bytes() == "こんにちは".encode("cp932")


def test_on_moved_txt_dest_triggers_processing(tmp_path):
    handler, base, log_dir, q = _make_handler(tmp_path)
    dest = base / "moved.txt"
    dest.write_text("moved body")

    event = SimpleNamespace(
        src_path=str(base / "tmp.tmp"),
        dest_path=str(dest),
        is_directory=False,
    )
    handler.on_moved(event)

    kind, _ts, _path, body = q.get_nowait()
    assert kind == "ok"
    assert body == "moved body"


def test_on_moved_non_txt_ignored(tmp_path):
    handler, base, log_dir, q = _make_handler(tmp_path)
    dest = base / "notatxt.log"
    dest.write_text("skip")

    event = SimpleNamespace(
        src_path=str(base / "x.tmp"),
        dest_path=str(dest),
        is_directory=False,
    )
    handler.on_moved(event)
    assert q.empty()


def test_existing_file_is_skipped(tmp_path):
    base = tmp_path / "OK"
    base.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    q: queue.Queue = queue.Queue()
    pre = base / "pre.txt"
    pre.write_text("PRE")

    handler = NsipsHandler(log_dir, base, existing={pre.resolve()}, event_queue=q)
    event = SimpleNamespace(src_path=str(pre), dest_path=None, is_directory=False)
    handler.on_created(event)

    assert q.empty()
    assert not (log_dir / "all.log").exists()


def test_second_event_on_same_path_is_skipped(tmp_path):
    handler, base, log_dir, q = _make_handler(tmp_path)
    src = base / "once.txt"
    src.write_bytes(b"data")

    event = SimpleNamespace(src_path=str(src), dest_path=None, is_directory=False)
    handler.on_created(event)
    handler.on_created(event)

    assert q.qsize() == 1
```

- [ ] **Step 2: テスト実行 → 失敗確認**

```bash
pytest tests/test_nsips_handler.py -v
```

Expected: `ImportError: cannot import name 'NsipsHandler' from 'main'`

- [ ] **Step 3: `main.py` に `NsipsHandler` を追記**

`main.py` の import 部と DEFAULT_BASE_DIR の間、または関数群の下に追記:

```python
import threading
import traceback
from datetime import datetime

from watchdog.events import FileSystemEvent, PatternMatchingEventHandler

from core import (
    append_all_log,
    copy_backup,
    decode_auto,
    wait_for_stable_size,
    wait_for_unlock,
)


class NsipsHandler(PatternMatchingEventHandler):
    """OK フォルダ直下の .txt を検知する watchdog ハンドラ。

    処理結果は event_queue に ("ok"|"error", timestamp, path, body_or_msg) を put する。
    """

    patterns = ["*.txt"]

    def __init__(
        self,
        log_dir: Path,
        base_dir: Path,
        existing: set[Path],
        event_queue,
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

    def _process(self, src_path: str) -> None:
        try:
            path = Path(src_path).resolve()
            with self._lock:
                if path in self.existing:
                    return
                self.existing.add(path)

            ts = datetime.now()
            if not wait_for_unlock(path, max_retries=20, interval=0.1):
                msg = "file remained locked"
                append_all_log(self.all_log, ts, path, f"[ERROR] {msg}")
                self.queue.put(("error", ts, path, msg))
                return
            if not wait_for_stable_size(path, checks=3, interval=0.1, max_polls=50):
                msg = "size did not stabilize"
                append_all_log(self.all_log, ts, path, f"[ERROR] {msg}")
                self.queue.put(("error", ts, path, msg))
                return

            body = decode_auto(path.read_bytes())
            append_all_log(self.all_log, ts, path, body)
            copy_backup(path, self.log_dir, "OK", ts)
            self.queue.put(("ok", ts, path, body))
        except Exception:
            try:
                append_all_log(
                    self.all_log,
                    datetime.now(),
                    Path(str(src_path)),
                    f"[ERROR] {traceback.format_exc()}",
                )
            except Exception:
                pass

    def on_created(self, event: FileSystemEvent) -> None:
        self._process(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        dest = getattr(event, "dest_path", None)
        if dest and str(dest).lower().endswith(".txt"):
            self._process(str(dest))
```

- [ ] **Step 4: テスト実行 → 成功確認**

```bash
pytest tests/test_nsips_handler.py -v
```

Expected: 5 passed

- [ ] **Step 5: 全テスト実行、回帰なし確認**

```bash
pytest -v
```

Expected: 全 pass (Task 2 の 32 件 + Task 3 の 6 件 + Task 4 の 5 件 = 43 件程度)

- [ ] **Step 6: コミット**

```bash
git add main.py tests/test_nsips_handler.py
git commit -m "feat: NsipsHandler で .txt 検知処理 (queue 経由で GUI に受け渡し)"
```

---

## Task 5: tkinter GUI シェル (ウィンドウ + メニュー + ScrolledText)

観察対象はまだ繋げず、GUI のガワを先に作る。手動でウィンドウを開いて見た目を確認できる状態にする。

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`

- [ ] **Step 1: `main.py` に GUI クラスと最小 `main()` を追記**

`main.py` の末尾に:

```python
import os
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

from core import save_config
from watchdog.observers import Observer


class NsipsWatcherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.event_queue: queue.Queue = queue.Queue()
        self.observer: Observer | None = None
        self.handler: NsipsHandler | None = None
        self.existing: set[Path] = set()
        self.base_dir: Path | None = None

        self.log_dir = app_dir() / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.cfg_path = config_path()

        self._build_ui()

    def _build_ui(self) -> None:
        self.root.title("nsips-watcher")
        self.root.geometry("800x600")

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

        self.text = scrolledtext.ScrolledText(
            self.root,
            wrap="word",
            font=("Consolas", 11),
            state="normal",
        )
        self.text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._show_body("info", None, None, "監視待機中...")
        self.text.config(state="disabled")

        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

    def _show_body(self, kind: str, ts, path, body: str) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        if kind == "ok":
            header = f"# {ts:%Y-%m-%d %H:%M:%S} {path}\n\n"
            self.text.insert("end", header + body)
        elif kind == "error":
            header = f"# ERROR {ts:%Y-%m-%d %H:%M:%S} {path}\n\n"
            self.text.insert("end", header + body)
        else:
            self.text.insert("end", body)
        self.text.config(state="disabled")

    def open_log_folder(self) -> None:
        try:
            os.startfile(str(self.log_dir))
        except AttributeError:
            # macOS 等での開発時
            pass

    def change_base_dir(self) -> None:
        pass  # 次のタスクで実装

    def quit_app(self) -> None:
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    NsipsWatcherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: import が壊れていないか確認**

```bash
cd ~/dev/nsips-watcher
source .venv/bin/activate
python3 -c "import main; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: 全テスト実行、回帰なし確認**

```bash
pytest -v
```

Expected: 全 pass

- [ ] **Step 4: コミット**

```bash
git add main.py
git commit -m "feat: tkinter GUI シェル (ウィンドウ, メニュー, ScrolledText)"
```

---

## Task 6: Observer 起動とキュー ポーリングの統合

App 起動時に base_dir を解決し、Observer を起動する。queue をポーリングして GUI を更新する。

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`

- [ ] **Step 1: `NsipsWatcherApp.__init__` の末尾に起動処理を追加**

`self._build_ui()` の直後に以下を追記:

```python
        self._start_or_prompt()
        self._poll_queue()
```

- [ ] **Step 2: App クラスに `_start_or_prompt`, `_start_observer`, `_stop_observer`, `_poll_queue`, `_prompt_base_dir` を追記**

`change_base_dir` の直前 (もしくは `open_log_folder` の下) に:

```python
    def _prompt_base_dir(self) -> Path | None:
        """フォルダ選択ダイアログを出す。キャンセルで None。"""
        chosen = filedialog.askdirectory(
            title="監視対象フォルダを選択",
            parent=self.root,
        )
        if not chosen:
            return None
        p = Path(chosen)
        if not p.is_dir():
            messagebox.showinfo(
                "フォルダが無効",
                f"{p} は有効なフォルダではありません。",
                parent=self.root,
            )
            return None
        return p

    def _start_or_prompt(self) -> None:
        """起動時: config → default → ダイアログ の順で有効な base_dir を得て監視開始。"""
        base = resolve_base_dir(self.cfg_path, DEFAULT_BASE_DIR)
        while base is None:
            chosen = self._prompt_base_dir()
            if chosen is None:
                # ユーザーがキャンセル → GUI に案内を出して待機
                self._show_body(
                    "info", None, None,
                    "監視パスが設定されていません。\n\nメニューから「監視パスを変更」を選んでください。",
                )
                return
            base = chosen

        # config 保存
        cfg = load_config(self.cfg_path)
        cfg["base_dir"] = str(base)
        save_config(self.cfg_path, cfg)

        self._start_observer(base)

    def _start_observer(self, base: Path) -> None:
        try:
            self.existing = set()
            self.existing.update(
                p.resolve()
                for p in base.iterdir()
                if p.is_file() and p.suffix.lower() == ".txt"
            )
            self.handler = NsipsHandler(
                self.log_dir, base, self.existing, self.event_queue
            )
            observer = Observer()
            observer.schedule(self.handler, str(base), recursive=False)
            observer.start()
            self.observer = observer
            self.base_dir = base
            self.status_var.set(f"監視中: {base}")
            self._show_body(
                "info", None, None,
                f"監視待機中... ({base})",
            )
        except Exception as e:
            self.status_var.set("監視エラー")
            self._show_body(
                "info", None, None,
                f"監視開始に失敗しました: {e}\n\n"
                "メニューから「監視パスを変更」で別のパスを選んでください。",
            )

    def _stop_observer(self) -> None:
        if self.observer is not None:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
            self.handler = None

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, ts, path, body = self.event_queue.get_nowait()
                self._show_body(kind, ts, path, body)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)
```

- [ ] **Step 3: `quit_app` を差し替え (Observer を止めてから destroy)**

```python
    def quit_app(self) -> None:
        self._stop_observer()
        self.root.destroy()
```

- [ ] **Step 4: import 確認 + 全テスト実行**

```bash
python3 -c "import main; print('ok')"
pytest -v
```

Expected: `ok` + 全 pass

- [ ] **Step 5: コミット**

```bash
git add main.py
git commit -m "feat: Observer 起動と queue ポーリングを GUI に統合"
```

---

## Task 7: 「監視パスを変更」の実装

**Files:**
- Modify: `~/dev/nsips-watcher/main.py`

- [ ] **Step 1: `change_base_dir` を差し替え**

```python
    def change_base_dir(self) -> None:
        chosen = self._prompt_base_dir()
        if chosen is None:
            return
        self._stop_observer()
        self._start_observer(chosen)
        if self.observer is not None:
            cfg = load_config(self.cfg_path)
            cfg["base_dir"] = str(chosen)
            save_config(self.cfg_path, cfg)
```

- [ ] **Step 2: import 確認**

```bash
python3 -c "import main; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: 全テスト実行**

```bash
pytest -v
```

Expected: 全 pass

- [ ] **Step 4: コミット**

```bash
git add main.py
git commit -m "feat: メニュー「監視パスを変更」を実装 (Observer 再起動 + config 保存)"
```

---

## Task 8: build.bat 作成

**Files:**
- Create: `~/dev/nsips-watcher/build.bat`

- [ ] **Step 1: `build.bat` を作成**

```bat
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
```

- [ ] **Step 2: コミット**

```bash
git add build.bat
git commit -m "chore: build.bat (PyInstaller onefile ビルド)"
```

---

## Task 9: GitHub private リポジトリへ push

**Files:**
- なし (gh CLI)

- [ ] **Step 1: GitHub private リポジトリを作成**

```bash
cd ~/dev/nsips-watcher
gh repo create hidemasa658/nsips-watcher --private --source=. --remote=origin
```

- [ ] **Step 2: main ブランチを push**

```bash
git branch -M main
git push -u origin main
```

- [ ] **Step 3: MEMORY.md に登録**

`~/.claude/projects/-Users-a/memory/nsips-watcher.md` を作成し、`MEMORY.md` の「アクティブプロジェクト」に 1 行追加。

---

## Task 10: Windows 実機での手動確認

**Files:**
- Modify: `~/dev/nsips-watcher/README.md`

- [ ] **Step 1: Windows PC に git clone**

```
git clone https://github.com/hidemasa658/nsips-watcher.git
cd nsips-watcher
```

- [ ] **Step 2: 依存インストール**

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

- [ ] **Step 3: 開発モードで起動**

```
python main.py
```

- ウィンドウが開き「監視中: C:\solamichi\solamichiclient\client\LOG\NSIPS\OK」ラベルが出ることを確認
- パスが存在しない場合はフォルダ選択ダイアログが出ること

- [ ] **Step 4: .txt 検知確認**

```
echo テスト内容 > C:\solamichi\solamichiclient\client\LOG\NSIPS\OK\test.txt
```

確認:
- ウィンドウの Text エリアに `# yyyy-mm-dd HH:MM:SS C:\...\test.txt` + 「テスト内容」が表示される
- `logs\all.log` に追記されている
- `logs\OK\<timestamp>_test.txt` に原本コピーが存在

- [ ] **Step 5: 既存ファイル無視確認**

起動前から `OK\` にあった .txt が起動時に処理されないことを確認 (all.log に載らない)。

- [ ] **Step 6: 「監視パスを変更」確認**

メニューから「監視パスを変更」→ 別フォルダを選ぶ → status ラベルが更新される、Observer が新パスを監視する。

- [ ] **Step 7: 「ログフォルダを開く」確認**

メニューから「ログフォルダを開く」→ explorer で `logs\` が開く。

- [ ] **Step 8: 終了確認**

- メニュー「終了」でウィンドウが閉じ、タスクマネージャからプロセスが消える
- ✕ ボタンでも同じ挙動

- [ ] **Step 9: PyInstaller ビルド**

```
build.bat
```

`dist\nsips-watcher.exe` を任意フォルダにコピーし、Step 3-8 を再確認。

- [ ] **Step 10: README に確認結果を追記してコミット**

`README.md` の末尾に:

```markdown
## 動作確認履歴

- 2026-MM-DD: Windows 10 (バージョン xxxx) 実機で手動確認完了
```

```bash
git add README.md
git commit -m "docs: Windows 実機での手動確認結果を記録"
git push
```

---

## 完了基準

- 全 Task の全 Step のチェックが埋まる
- `pytest -v` が全 pass (計 40 件超)
- Windows 実機で手動確認 (Task 10) 完了、README に記録済み
- GitHub private リポジトリへ push 済み
