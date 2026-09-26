"""nsips-stats-api への HTTP クライアント (mTLS 対応)。"""
from __future__ import annotations

import httpx


class StatsClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        cert: tuple[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        client_kwargs: dict = dict(
            base_url=self.base_url,
            timeout=timeout,
            headers={"X-API-Token": self.token},
        )
        if transport is not None:
            client_kwargs["transport"] = transport
        if cert is not None:
            client_kwargs["cert"] = cert
        self._client = httpx.Client(**client_kwargs)

    def close(self) -> None:
        self._client.close()

    def post_ingest(self, payload: dict) -> dict:
        r = self._client.post("/ingest", json=payload)
        r.raise_for_status()
        return r.json()

    def get_drugs(self) -> list[dict]:
        r = self._client.get("/stats/drugs")
        r.raise_for_status()
        return r.json()["rows"]

    def get_clinics(self) -> list[dict]:
        r = self._client.get("/stats/clinics")
        r.raise_for_status()
        return r.json()["rows"]

    def get_mix(self) -> dict:
        r = self._client.get("/stats/mix")
        r.raise_for_status()
        return r.json()

    def get_export_prescriptions(self) -> list[dict]:
        r = self._client.get("/stats/export/prescriptions")
        r.raise_for_status()
        return r.json()["rows"]

    def check_source_ids(self, source_ids: list[str]) -> set[str]:
        """指定 source_id のうち サーバに既存のものだけ set で返す。
        500 件ずつバッチ処理。未送信スキャン用。"""
        existing: set[str] = set()
        BATCH = 500
        for i in range(0, len(source_ids), BATCH):
            batch = source_ids[i:i + BATCH]
            r = self._client.post("/api/check_source_ids", json={"source_ids": batch})
            r.raise_for_status()
            existing.update(r.json().get("existing", []))
        return existing
