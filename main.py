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


def main() -> None:
    """tkinter とその周辺は lazy import (macOS pyenv で _tkinter 未導入でも import main が壊れないため)。"""
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
            pass  # Task 7 で実装

        def quit_app(self) -> None:
            self.root.destroy()

    root = tk.Tk()
    NsipsWatcherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
