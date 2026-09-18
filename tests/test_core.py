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
