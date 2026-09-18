"""NSIPS .txt をレコード種別ごとにパース。record 1 (患者情報) は必ず破棄する。"""
from __future__ import annotations


# YJ コード 8 文字目 (剤形記号) の分類マップ
_FORM_INTERNAL = set("FKSGREDCLB")  # 内服系: 錠/カプセル/散/顆粒/咀嚼/内服液/エキス 等
_FORM_EXTERNAL = set("MNQXUP")      # 外用系: 軟膏/クリーム/ローション/貼付/パップ/坐剤


def classify_form(yj_code: str | None) -> str:
    """YJ コード 8 文字目から 剤形分類 (内服/外用/その他) を返す。"""
    if not yj_code or len(yj_code) < 8:
        return "その他"
    letter = yj_code[7]
    if letter in _FORM_EXTERNAL:
        return "外用"
    if letter in _FORM_INTERNAL:
        return "内服"
    return "その他"


def get_dosage_form_code(yj_code: str | None) -> str | None:
    """YJ コード 8 文字目 (剤形記号) を返す。"""
    if not yj_code or len(yj_code) < 8:
        return None
    return yj_code[7]


def sanitize_body(body: str) -> str:
    """NSIPS 本文から record 1 (患者情報) 行を削除して返す。"""
    return "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("1,")
    )


def _col(fields: list[str], idx: int) -> str | None:
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


def _extract_quantity(fields: list[str], form: str) -> float | None:
    """
    処方量を form 依存で抽出:
    - 外用: position 16 = 総処方量 (30g 等)
    - 内服: position 24 = 総処方量 (22 錠 等) を優先、無ければ 16
    """
    pos_16 = _to_float(_col(fields, 16))
    pos_24 = _to_float(_col(fields, 24))
    if form == "外用":
        return pos_16
    # 内服 / その他
    return pos_24 if pos_24 is not None else pos_16


def parse_nsips(body: str) -> dict:
    """NSIPS .txt をパースし、record 1 を除いた辞書を返す。

    Returns:
        {
          "prescription": {...},
          "drugs": [{"rp_no","yj_code","name","quantity","unit","form","dosage_form_code"}, ...],
          "fees": [{"fee_type","code","name","count","points"}, ...],
          "rps": [
            {
              "rp_no": "1",
              "usage_code": "244",
              "usage_text": "分3 毎食後服用",
              "site_text": "混合" or "",   # record 3 field 5 (混合フラグ用)
              "is_mixed": False,             # record 3 に "混合" 含む OR 同 RP に 2+ record 4
              "drug_count": 1,               # 集計後
            }, ...
          ],
        }
    """
    result: dict = {
        "prescription": {},
        "drugs": [],
        "fees": [],
        "rps": [],
    }
    rps_by_no: dict[str, dict] = {}

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split(",")
        rec = fields[0]

        if rec == "1":
            continue  # 患者情報破棄

        if rec == "2":
            result["prescription"] = {
                "prescription_date": _col(fields, 4),
                "clinic_code": _col(fields, 12),
                "clinic_name": _col(fields, 14),
                "doctor_name": None,
            }

        elif rec == "3":
            rp_no = _col(fields, 1)
            usage_code = _col(fields, 2)
            usage_text = _col(fields, 3)
            site_text = _col(fields, 5)  # 「混合」等
            is_mixed_marker = site_text == "混合"
            rps_by_no[rp_no or ""] = {
                "rp_no": rp_no,
                "usage_code": usage_code,
                "usage_text": usage_text,
                "site_text": site_text,
                "is_mixed": is_mixed_marker,  # あとで drug 数でも更新
                "drug_count": 0,
            }

        elif rec == "4":
            rp_no = _col(fields, 2)
            yj_code = _col(fields, 4)
            form = classify_form(yj_code)
            result["drugs"].append(
                {
                    "rp_no": rp_no,
                    "yj_code": yj_code,
                    "name": _col(fields, 8),
                    "quantity": _extract_quantity(fields, form),
                    "unit": _col(fields, 18),
                    "form": form,
                    "dosage_form_code": get_dosage_form_code(yj_code),
                }
            )
            # RP に drug count
            if rp_no and rp_no in rps_by_no:
                rps_by_no[rp_no]["drug_count"] += 1

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

    # RP を drug_count >= 2 でも 混合フラグ立てる
    for rp in rps_by_no.values():
        if rp["drug_count"] >= 2:
            rp["is_mixed"] = True
        result["rps"].append(rp)

    return result
