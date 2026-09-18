"""nsips-watcher のヘッドレス監視モード (GUI なし、Windows タスクトレイなし、バックグラウンド常駐)。

用途: 薬局 PC のスタートアップに登録して、監視 + VPS 送信だけをずっと裏で動かす。
GUI で見たいときは main.py または viewer.py を別途起動する。

ログ: <app_dir>/logs/all.log と <app_dir>/logs/service.log

停止: タスクマネージャで python.exe/nsips-watcher-service.exe を終了。
"""
from __future__ import annotations

import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from watchdog.observers import Observer

from core import (
    append_all_log,
    load_config,
    save_config,
)
from main import (
    DEFAULT_BASE_DIR,
    NsipsHandler,
    app_dir,
    config_path,
    resolve_base_dir,
)
from nsips_crypto import get_or_create_key
from stats_client import StatsClient


def log(msg: str) -> None:
    """service.log に追記 + stdout。"""
    log_dir = app_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n"
    (log_dir / "service.log").open("a", encoding="utf-8").write(line)
    try:
        print(line, end="", flush=True)
    except Exception:
        pass


def run_service() -> int:
    log("=== nsips-watcher service 起動 ===")
    log_dir = app_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    cfg_path = config_path()
    base_dir = resolve_base_dir(cfg_path, DEFAULT_BASE_DIR)
    if base_dir is None:
        log(f"[FATAL] 監視パスが見つかりません。config.json に base_dir を設定してください。")
        log(f"        検索したパス: config.json / {DEFAULT_BASE_DIR}")
        return 1
    log(f"監視パス: {base_dir}")

    cfg = load_config(cfg_path)
    cfg["base_dir"] = str(base_dir)
    save_config(cfg_path, cfg)

    crypto_key = get_or_create_key(app_dir() / ".key")

    stats_client: StatsClient | None = None
    url = cfg.get("api_base_url")
    token = cfg.get("api_token")
    cert_path = cfg.get("client_cert_path")
    key_path = cfg.get("client_key_path")
    if url and token and cert_path and key_path and Path(cert_path).is_file() and Path(key_path).is_file():
        stats_client = StatsClient(base_url=url, token=token, cert=(cert_path, key_path))
        log(f"VPS 送信有効: {url}")
    else:
        log("[WARN] API 設定不足、ローカル監視のみ (VPS 送信スキップ)")

    existing = set()
    for p in base_dir.iterdir():
        if p.is_file() and p.suffix.lower() == ".txt":
            existing.add(p.resolve())
    log(f"起動時既存 .txt: {len(existing)} 件 (無視リスト化済)")

    event_queue: queue.Queue = queue.Queue()
    handler = NsipsHandler(
        log_dir=log_dir,
        base_dir=base_dir,
        existing=existing,
        event_queue=event_queue,
        stats_client=stats_client,
        crypto_key=crypto_key,
    )
    observer = Observer()
    observer.schedule(handler, str(base_dir), recursive=False)
    observer.start()
    log("Observer 起動、監視中...")

    def drain_queue() -> None:
        while True:
            try:
                kind, ts, path, body = event_queue.get(timeout=1.0)
                if kind == "ok":
                    log(f"検知 [{ts:%H:%M:%S}]: {Path(path).name}")
                elif kind == "error":
                    log(f"[ERROR] {path}: {body}")
            except queue.Empty:
                continue

    drain_thread = threading.Thread(target=drain_queue, daemon=True)
    drain_thread.start()

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log("Ctrl+C 受信、終了処理中...")
    finally:
        observer.stop()
        observer.join(timeout=5)
        if stats_client is not None:
            stats_client.close()
        log("=== service 終了 ===")

    return 0


if __name__ == "__main__":
    sys.exit(run_service())
