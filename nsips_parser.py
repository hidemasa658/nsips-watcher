"""NSIPS .txt をレコード種別ごとにパース。record 1 (患者情報) は必ず破棄する。"""
from __future__ import annotations


def _col(fields: list[str], idx: int) -> str | None:
    """安全なフィールド取得。範囲外や空文字は None。"""
    if idx < 0 or idx >= len(fields):
        return None
    v = fields[idx].strip()
    return v if v else None


def _to_float(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _to_int(v: str | None) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def parse_nsips(body: str) -> dict:
    """NSIPS .txt 全体をパースし、record 1 を除いた辞書を返す。

    Returns:
        {
          "prescription": {"prescription_date","clinic_code","clinic_name","doctor_name"},
          "drugs": [{"rp_no","yj_code","name","quantity","unit"}, ...],
          "fees": [{"fee_type","code","name","count","points"}, ...],
        }
    """
    result: dict = {"prescription": {}, "drugs": [], "fees": []}

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split(",")
        rec = fields[0]

        if rec == "1":
            # 患者情報。破棄
            continue

        if rec == "2":
            result["prescription"] = {
                "prescription_date": _col(fields, 4),
                "clinic_code": _col(fields, 12),
                "clinic_name": _col(fields, 14),
                "doctor_name": None,  # 位置未確定のため MVP では None
            }

        elif rec == "4":
            result["drugs"].append(
                {
                    "rp_no": _col(fields, 2),
                    "yj_code": _col(fields, 4),
                    "name": _col(fields, 8),
                    "quantity": _to_float(_col(fields, 24)),
                    "unit": _col(fields, 18),
                }
            )

        elif rec in ("6", "7"):
            result["fees"].append(
                {
                    "fee_type": rec,
                    "code": _col(fields, 2),
                    "name": _col(fields, 3),
                    "count": _to_int(_col(fields, 4)),
                    "points": _to_int(_col(fields, 5)),
                }
            )

        # record 3, 5 は MVP 対象外 (skip)

    return result
