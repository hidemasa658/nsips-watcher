"""nsips-watcher エントリポイント。solamichi クライアントの NSIPS/OK 出力を監視する。"""
from __future__ import annotations

import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEvent, PatternMatchingEventHandler

from core import (
    append_all_log,
    copy_backup,
    decode_auto,
    load_config,
    wait_for_stable_size,
    wait_for_unlock,
)

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
