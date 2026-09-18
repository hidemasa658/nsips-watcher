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
