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
