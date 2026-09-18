"""nsips-watcher エントリポイント。solamichi クライアントの NSIPS/OK 出力を監視する。"""
from __future__ import annotations

import hashlib
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
from nsips_crypto import encrypt_field
from nsips_parser import parse_nsips

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

            # ---- Stats 送信 ----
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
    import csv
    import os
    import queue
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    from core import save_config
    from nsips_crypto import decrypt_field, get_or_create_key
    from stats_client import StatsClient
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

            # 暗号鍵と stats client
            self.crypto_key = get_or_create_key(app_dir() / ".key")
            self.stats_client: StatsClient | None = None

            self._build_ui()
            self._init_stats_client()
            self._start_or_prompt()
            self._poll_queue()

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

            # タブ 2: 薬剤別累計
            tab_drugs = tk.Frame(self.notebook)
            self.tree_drugs = ttk.Treeview(
                tab_drugs, columns=("yj", "name", "n", "qty", "unit"), show="headings",
            )
            for col, heading, w in [
                ("yj", "YJコード", 130), ("name", "薬品名", 300),
                ("n", "調剤回数", 80), ("qty", "総数量", 100), ("unit", "単位", 80),
            ]:
                self.tree_drugs.heading(col, text=heading)
                self.tree_drugs.column(col, width=w, anchor="w")
            self.tree_drugs.pack(fill="both", expand=True)
            self.notebook.add(tab_drugs, text="薬剤別累計")

            # タブ 3: 医療機関別
            tab_clinics = tk.Frame(self.notebook)
            self.tree_clinics = ttk.Treeview(
                tab_clinics, columns=("code", "name", "n"), show="headings",
            )
            for col, heading, w in [
                ("code", "医療機関コード", 150), ("name", "医療機関名", 400), ("n", "件数", 80),
            ]:
                self.tree_clinics.heading(col, text=heading)
                self.tree_clinics.column(col, width=w, anchor="w")
            self.tree_clinics.pack(fill="both", expand=True)
            self.notebook.add(tab_clinics, text="医療機関別")

            # タブ 4: 計量混合加算
            tab_mix = tk.Frame(self.notebook)
            self.mix_total_var = tk.StringVar(value="計量混合加算がついた処方: -")
            tk.Label(tab_mix, textvariable=self.mix_total_var, font=("Meiryo", 12)).pack(
                anchor="w", padx=8, pady=8,
            )
            self.tree_mix = ttk.Treeview(
                tab_mix, columns=("cnt", "n"), show="headings",
            )
            for col, heading, w in [
                ("cnt", "混合品目数", 120), ("n", "該当件数", 120),
            ]:
                self.tree_mix.heading(col, text=heading)
                self.tree_mix.column(col, width=w, anchor="center")
            self.tree_mix.pack(fill="both", expand=True, padx=8, pady=8)
            self.notebook.add(tab_mix, text="計量混合加算")

            # タブ 5: エクスポート
            tab_export = tk.Frame(self.notebook)
            tk.Button(tab_export, text="薬剤別累計を CSV 保存",
                      command=self.export_drugs_csv, width=30).pack(pady=8, padx=8, anchor="w")
            tk.Button(tab_export, text="医療機関別を CSV 保存",
                      command=self.export_clinics_csv, width=30).pack(pady=8, padx=8, anchor="w")
            tk.Button(tab_export, text="全 prescriptions を CSV 保存",
                      command=self.export_prescriptions_csv, width=30).pack(pady=8, padx=8, anchor="w")
            self.notebook.add(tab_export, text="エクスポート")

            self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
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
                base_url=url, token=token, cert=(cert_path, key_path),
            )

        def open_log_folder(self) -> None:
            try:
                os.startfile(str(self.log_dir))
            except AttributeError:
                pass

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

        def refresh_clinics_tab(self) -> None:
            if self.stats_client is None:
                return
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
                self.tree_mix.insert("", "end", values=(f"{row['drug_count']} 品目", row["n"]))

        def _refresh_current_tab(self) -> None:
            idx = self.notebook.index("current")
            if idx == 1:
                self.refresh_drugs_tab()
            elif idx == 2:
                self.refresh_clinics_tab()
            elif idx == 3:
                self.refresh_mix_tab()

        def _on_tab_changed(self, event) -> None:
            self._refresh_current_tab()

        def _save_csv(self, default_name: str, header: list, rows: list) -> None:
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
            try:
                rows = self.stats_client.get_export_prescriptions()
            except Exception as e:
                messagebox.showerror("エラー", f"取得失敗: {e}", parent=self.root)
                return

            def _dec(v):
                try:
                    return decrypt_field(self.crypto_key, v) or ""
                except Exception:
                    return "[decrypt error]"

            data = []
            for r in rows:
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
                    self._show_body(
                        "info", None, None,
                        "監視パスが設定されていません。\n\n"
                        "メニューから「監視パスを変更」を選んでください。",
                    )
                    return
                base = chosen

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
                    self.log_dir, base, self.existing, self.event_queue,
                    stats_client=self.stats_client,
                    crypto_key=self.crypto_key,
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
            got_event = False
            try:
                while True:
                    kind, ts, path, body = self.event_queue.get_nowait()
                    self._show_body(kind, ts, path, body)
                    got_event = True
            except queue.Empty:
                pass
            if got_event:
                self._refresh_current_tab()
            self.root.after(200, self._poll_queue)

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

        def quit_app(self) -> None:
            self._stop_observer()
            if self.stats_client is not None:
                self.stats_client.close()
            self.root.destroy()

    root = tk.Tk()
    NsipsWatcherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
