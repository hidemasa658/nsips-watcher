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
