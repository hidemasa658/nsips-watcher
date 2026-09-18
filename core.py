"""sips-watcher の純粋ロジック層。Windows 依存を含まない。"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path


def decode_auto(data: bytes) -> str:
    """UTF-8 → CP932 → Latin-1 の順に decode を試す。Latin-1 は必ず成功する。"""
    for encoding in ("utf-8", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def snapshot_existing(roots: list[Path]) -> set[Path]:
    """指定ルート配下の既存 .txt を絶対パスの set で返す。存在しないルートは無視。"""
    result: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.txt"):
            if path.is_file():
                result.add(path.resolve())
    return result


def append_all_log(log_path: Path, timestamp: datetime, source: Path, body: str) -> None:
    """all.log に 1 エントリ追記する。UTF-8, LF 改行。親ディレクトリが無ければ作成。

    書式:
        [YYYY-MM-DD HH:MM:SS.mmm] <source>
        <body>
        ---
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ms = timestamp.microsecond // 1000
    header = f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}.{ms:03d}] {source}\n"
    entry = f"{header}{body}\n---\n"
    with log_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(entry)


def unique_dest_path(candidate: Path) -> Path:
    """候補パスが既存なら stem に _2, _3, ... を付けて衝突しないパスを返す。"""
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    parent = candidate.parent
    n = 2
    while True:
        new_path = parent / f"{stem}_{n}{suffix}"
        if not new_path.exists():
            return new_path
        n += 1


def copy_backup(source: Path, log_dir: Path, sips_name: str, timestamp: datetime) -> Path:
    """検知ファイルを logs/<sips_name>/<YYYYMMDD_HHMMSS_mmm>_<元名> にコピー。"""
    dest_dir = log_dir / sips_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    ms = timestamp.microsecond // 1000
    prefix = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{ms:03d}"
    candidate = dest_dir / f"{prefix}_{source.name}"
    final = unique_dest_path(candidate)
    shutil.copy2(source, final)
    return final


def wait_for_unlock(path: Path, max_retries: int = 20, interval: float = 0.1) -> bool:
    """ファイルを read-open できるまでリトライ。成功したら True、諦めたら False。

    最終試行の後は sleep しない。
    """
    for attempt in range(max_retries):
        try:
            with path.open("rb"):
                return True
        except (OSError, PermissionError):
            if attempt < max_retries - 1:
                time.sleep(interval)
    return False


def load_config(path: Path) -> dict:
    """config.json を読む。存在しない or 壊れていたら空 dict。"""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_config(path: Path, data: dict) -> None:
    """config.json を UTF-8 で書き出す。親ディレクトリが無ければ作成。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def wait_for_stable_size(
    path: Path,
    checks: int = 3,
    interval: float = 0.1,
    max_polls: int = 50,
) -> bool:
    """`checks` 回連続でファイルサイズが同じになるまで待つ (書き込み完了判定)。

    Windows で共有読み取り可能なまま書き込み中のファイルを部分読み込みしてしまう
    ケースを避ける。存在しない/`max_polls` 超過で False。
    """
    stable = 0
    last_size = -1
    for _ in range(max_polls):
        try:
            size = path.stat().st_size
        except (OSError, FileNotFoundError):
            return False
        if size == last_size:
            stable += 1
            if stable >= checks:
                return True
        else:
            stable = 1
            last_size = size
        time.sleep(interval)
    return False
