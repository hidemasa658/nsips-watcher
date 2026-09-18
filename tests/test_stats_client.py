import httpx
import pytest

from stats_client import StatsClient


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_post_ingest_sends_token_and_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["token"] = request.headers.get("X-API-Token")
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"status": "ok", "prescription_id": 1})

    client = StatsClient(
        base_url="https://example.test/nsips-stats",
        token="TOK",
        transport=_mock_transport(handler),
    )
    result = client.post_ingest({"source_id": "s1", "detected_at": "x", "drugs": [], "fees": []})
    assert result == {"status": "ok", "prescription_id": 1}
    assert captured["url"].endswith("/ingest")
    assert captured["token"] == "TOK"
    assert '"source_id":"s1"' in captured["body"] or '"source_id": "s1"' in captured["body"]


def test_get_drugs_returns_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/stats/drugs")
        return httpx.Response(
            200, json={"rows": [{"yj_code": "Y", "name": "A", "unit": "錠", "n": 3, "qty": 30}]}
        )

    client = StatsClient(
        base_url="https://example.test/nsips-stats", token="T",
        transport=_mock_transport(handler),
    )
    rows = client.get_drugs()
    assert rows[0]["yj_code"] == "Y"


def test_get_clinics_returns_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/stats/clinics")
        return httpx.Response(
            200, json={"rows": [{"clinic_code_enc": "E", "clinic_name_enc": "N", "n": 5}]}
        )

    client = StatsClient(
        base_url="https://example.test/nsips-stats", token="T",
        transport=_mock_transport(handler),
    )
    rows = client.get_clinics()
    assert rows[0]["n"] == 5


def test_get_mix_returns_total_and_breakdown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"total": 4, "breakdown": [{"drug_count": 2, "n": 3}]}
        )

    client = StatsClient(
        base_url="https://example.test/nsips-stats", token="T",
        transport=_mock_transport(handler),
    )
    result = client.get_mix()
    assert result["total"] == 4


def test_401_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid token"})

    client = StatsClient(
        base_url="https://example.test/nsips-stats", token="wrong",
        transport=_mock_transport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.get_drugs()
