"""nsips-stats-api の統計を CLI で見るビューア。tkinter 不要。

使い方:
    python viewer.py drugs    # 薬剤別累計
    python viewer.py clinics  # 医療機関別 (復号は .key があるときのみ)
    python viewer.py mix      # 計量混合加算
    python viewer.py          # 全部表示
"""
from __future__ import annotations

import sys
from pathlib import Path

from core import load_config
from main import app_dir, config_path
from nsips_crypto import decrypt_field, get_or_create_key
from stats_client import StatsClient


def _client() -> StatsClient:
    cfg = load_config(config_path())
    return StatsClient(
        base_url=cfg["api_base_url"],
        token=cfg["api_token"],
        cert=(cfg["client_cert_path"], cfg["client_key_path"]),
    )


def show_drugs(c: StatsClient) -> None:
    print("\n=== 薬剤別累計 ===")
    rows = c.get_drugs()
    if not rows:
        print("(データなし)")
        return
    print(f"{'YJコード':<15} {'薬品名':<40} {'回数':>4} {'総数量':>8} 単位")
    print("-" * 80)
    for r in rows:
        yj = r.get("yj_code") or ""
        name = (r.get("name") or "")[:38]
        n = r.get("n") or 0
        qty = r.get("qty") or 0
        unit = r.get("unit") or ""
        print(f"{yj:<15} {name:<40} {n:>4} {qty:>8.2f} {unit}")
    print(f"\n合計 {len(rows)} 品目")


def show_clinics(c: StatsClient) -> None:
    print("\n=== 医療機関別 ===")
    rows = c.get_clinics()
    if not rows:
        print("(データなし)")
        return
    key = get_or_create_key(app_dir() / ".key")
    print(f"{'医療機関コード':<20} {'医療機関名':<40} 件数")
    print("-" * 80)
    for r in rows:
        try:
            code = decrypt_field(key, r.get("clinic_code_enc")) or ""
            name = decrypt_field(key, r.get("clinic_name_enc")) or ""
        except Exception:
            code = "[復号エラー]"
            name = "[復号エラー]"
        print(f"{code:<20} {name[:38]:<40} {r.get('n', 0)}")


def show_mix(c: StatsClient) -> None:
    print("\n=== 計量混合加算 ===")
    result = c.get_mix()
    print(f"総件数: {result.get('total', 0)} 件")
    breakdown = result.get("breakdown", [])
    if breakdown:
        print("\n品目数別内訳:")
        for row in breakdown:
            print(f"  {row['drug_count']} 品目混合: {row['n']} 件")


def main() -> None:
    c = _client()
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "drugs":
        show_drugs(c)
    elif arg == "clinics":
        show_clinics(c)
    elif arg == "mix":
        show_mix(c)
    else:
        show_drugs(c)
        show_clinics(c)
        show_mix(c)
    c.close()


if __name__ == "__main__":
    main()
