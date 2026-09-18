"""NsipsHandler が検知時に stats_client.post_ingest を呼ぶことを検証。"""
import queue
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from cryptography.fernet import Fernet

from main import NsipsHandler


def test_process_calls_post_ingest_with_encrypted_payload(tmp_path):
    base = tmp_path / "OK"
    base.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    q: queue.Queue = queue.Queue()

    src = base / "t.txt"
    src.write_bytes(
        (
            "2,x,x,x,20260918,,x,x,x,x,x,x,CLINIC01,x,タナベ 皮フ科医院,x,x,x,x,x,x,x\n"
            "1,人名,テスト 太郎,,,,,,,,,,,uuid,x\n"
            "4,1,1,1,YJ001,x,x,x,ビブラマイシン錠100mg,x,x,x,x,x,x,x,1,1,錠,x,x,x,x,x,22\n"
            "7,1,470000210,調剤物価対応料,1,1\n"
            "7,2,999999999,計量混合加算(液剤),1,45\n"
        ).encode("utf-8")
    )

    stats_client = MagicMock()
    stats_client.post_ingest.return_value = {"status": "ok", "prescription_id": 1}
    key = Fernet.generate_key()

    handler = NsipsHandler(
        log_dir=log_dir,
        base_dir=base,
        existing=set(),
        event_queue=q,
        stats_client=stats_client,
        crypto_key=key,
    )
    event = SimpleNamespace(src_path=str(src), dest_path=None, is_directory=False)
    handler.on_created(event)

    stats_client.post_ingest.assert_called_once()
    payload = stats_client.post_ingest.call_args[0][0]

    # 患者名 record 1 は絶対に含まれない
    assert "テスト 太郎" not in str(payload)

    # 医療機関名は平文で含まれない (暗号化されているはず)
    assert payload["clinic_name_enc"] is not None
    assert "タナベ 皮フ科医院" not in payload["clinic_name_enc"]

    # YJコードと薬品名は平文
    assert payload["drugs"][0]["yj_code"] == "YJ001"
    assert payload["drugs"][0]["name"] == "ビブラマイシン錠100mg"

    # is_mix_flag が正しく立つ
    mix_fees = [f for f in payload["fees"] if f["is_mix_flag"]]
    assert len(mix_fees) == 1


def test_process_skips_stats_when_client_is_none(tmp_path):
    """stats_client=None のときは post_ingest しない (テストや旧構成互換)。"""
    base = tmp_path / "OK"
    base.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    q: queue.Queue = queue.Queue()

    src = base / "t.txt"
    src.write_text("2,x\n4,1,1,1,YJ,x,x,x,名,x,x,x,x,x,x,x,1,1,錠,x,x,x,x,x,1\n")

    handler = NsipsHandler(
        log_dir=log_dir, base_dir=base, existing=set(), event_queue=q,
        stats_client=None, crypto_key=None,
    )
    event = SimpleNamespace(src_path=str(src), dest_path=None, is_directory=False)
    handler.on_created(event)
    assert not q.empty()
