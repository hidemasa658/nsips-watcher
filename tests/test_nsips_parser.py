from pathlib import Path

from nsips_parser import (
    classify_form,
    get_dosage_form_code,
    parse_nsips,
    sanitize_body,
)


def test_classify_form_external_ointment():
    assert classify_form("2646730M1059") == "外用"  # M = 軟膏


def test_classify_form_external_lotion():
    assert classify_form("3339950Q1147") == "外用"  # Q = ローション


def test_classify_form_external_cream():
    assert classify_form("2655709N1096") == "外用"  # N = クリーム


def test_classify_form_unknown_letter_returns_other():
    assert classify_form("YYYYYYYZ0000") == "その他"  # Z は該当マップ外


def test_classify_form_external_patch():
    assert classify_form("YYYYYYYX1000") == "外用"  # X = 貼付


def test_classify_form_internal_tablet():
    assert classify_form("6152004F2089") == "内服"  # F = 錠


def test_classify_form_internal_syrup():
    assert classify_form("6135001R2110") == "内服"  # R = 咀嚼/散/顆粒等 内服


def test_classify_form_short_yj_returns_other():
    assert classify_form(None) == "その他"
    assert classify_form("") == "その他"
    assert classify_form("ABC") == "その他"


def test_get_dosage_form_code():
    assert get_dosage_form_code("2646730M1059") == "M"
    assert get_dosage_form_code("6152004F2089") == "F"
    assert get_dosage_form_code(None) is None
    assert get_dosage_form_code("AB") is None


def test_parse_extracts_ointment_quantity_from_position_16():
    # 軟膏の処方量 30g が position 16 に入る
    body = (
        "4,1,1,1,2646730M1059,620008965,,21340,アンテベート軟膏,ベタメタゾン,"
        "0,0,0,0,0,0,30,1,ｇ,0,0,0,0,1,18.9,,,,,,,,0,0,,0,,,,,,0\n"
    )
    result = parse_nsips(body)
    d = result["drugs"][0]
    assert d["form"] == "外用"
    assert d["quantity"] == 30.0  # 外用は position 16 (30g)
    assert d["unit"] == "ｇ"


def test_parse_extracts_tablet_quantity_and_unit_price():
    """内服錠: position 16 = 1回量、position 24 = 薬価。"""
    body = (
        "4,1,1,1,6152004F2089,620006084,,7315,ビブラマイシン錠100mg,ドキシサイクリン,"
        "0,0,0,0,0,0,1,1,錠,0,0,0,0,1,22,,,,,,,0,0,,,0,,,,,,0\n"
    )
    result = parse_nsips(body)
    d = result["drugs"][0]
    assert d["form"] == "内服"
    assert d["quantity"] == 1.0  # 1回量
    assert d["unit_price"] == 22.0  # 薬価 22円/錠
    assert d["unit"] == "錠"


def test_parse_extracts_ointment_unit_price():
    """外用軟膏: position 16 = 総処方量、position 24 = 薬価。
    例: テラ・コートリル軟膏 10g 処方、薬価 25.1円/g
    """
    body = (
        "4,1,4,1,2647705M1023,662640163,,15007,テラ・コートリル軟膏,オキシテトラサイクリン,"
        "0,0,0,0,0,0,10,1,ｇ,0,0,0,0,1,25.1\n"
    )
    result = parse_nsips(body)
    d = result["drugs"][0]
    assert d["form"] == "外用"
    assert d["quantity"] == 10.0  # 10g 処方
    assert d["unit_price"] == 25.1  # 薬価 25.1円/g


def test_parse_extracts_rps_from_record_3():
    body = (
        "3,1,244,分3 毎食後服用,,,,,2,1,7,3,,1,0,0,,,,,,\n"
        "4,1,1,1,6135001R2110,616130333,,8367,ホスミシン,ホスホマイシン,"
        "0,0,0,0,0,0,3,1,ｇ,0,0,0,0,1,86.2\n"
    )
    result = parse_nsips(body)
    assert len(result["rps"]) == 1
    rp = result["rps"][0]
    assert rp["rp_no"] == "1"
    assert rp["usage_text"] == "分3 毎食後服用"
    assert rp["drug_count"] == 1
    assert rp["is_mixed"] is False


def test_parse_detects_mixed_rp_by_site_text_only():
    """is_mixed は record 3 field 5 == "混合" のときのみ。drug_count>=2 では判定しない。"""
    # Case 1: "混合" テキスト あり → is_mixed=True
    body_mixed = (
        "3,4,7914,1日2回塗布,477,混合,522,体幹四肢,4,3,0,0,,2,0,0,,,,,,\n"
        "4,1,4,1,2646701M2202,x,x,x,ベタメタゾン軟膏,x,0,0,0,0,0,0,50,1,ｇ,0,0,0,0,1,8\n"
        "4,2,4,1,3339950M1153,x,x,x,ヘパリン油性クリーム,x,0,0,0,0,0,0,50,1,ｇ,0,0,0,0,1,6.3\n"
    )
    result = parse_nsips(body_mixed)
    assert result["rps"][0]["is_mixed"] is True

    # Case 2: 内服の複数剤で "混合" 無し → is_mixed=False
    body_not_mixed = (
        "3,1,244,分3 毎食後,,,,,2,1,7,3,,1,0,0,,,,,,\n"
        "4,1,1,1,6152004F2089,x,x,x,ビブラマイシン錠,x,0,0,0,0,0,0,1,1,錠,0,0,0,0,1,22\n"
        "4,2,1,1,2316004F1020,x,x,x,ビオフェルミンR錠,x,0,0,0,0,0,0,1,1,錠,0,0,0,0,1,21\n"
    )
    result = parse_nsips(body_not_mixed)
    assert result["rps"][0]["is_mixed"] is False


def test_sanitize_body_removes_record_1_lines():
    body = "2,x,y\n1,タナベ,田辺 太郎\n4,drug\n"
    result = sanitize_body(body)
    assert "田辺" not in result
    assert "1,タナベ" not in result
    assert "2,x,y" in result
    assert "4,drug" in result


def test_sanitize_body_keeps_records_containing_1_in_middle():
    body = "2,260819000294101,210\n"
    result = sanitize_body(body)
    assert "260819000294101" in result


def test_sanitize_body_empty():
    assert sanitize_body("") == ""


FIXTURE = Path(__file__).parent / "fixtures" / "sample_nsips.txt"


def _load() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_returns_dict_with_expected_keys():
    result = parse_nsips(_load())
    assert set(result.keys()) == {"prescription", "drugs", "fees", "rps", "drug_pricings", "totals"}


def test_parse_extracts_prescription_from_record_2():
    result = parse_nsips(_load())
    p = result["prescription"]
    assert p["prescription_date"] == "20260918"
    assert p["clinic_code"] == "2605566"
    assert p["clinic_name"] == "タナベ 皮フ科医院"


def test_parse_drops_record_1():
    result = parse_nsips(_load())
    all_values = str(result)
    assert "テスト 太郎" not in all_values
    assert "15bf078c" not in all_values


def test_parse_extracts_all_record_4_drugs():
    result = parse_nsips(_load())
    drugs = result["drugs"]
    assert len(drugs) == 3
    d0 = drugs[0]
    assert d0["rp_no"] == "1"
    assert d0["yj_code"] == "6152004F2089"
    assert d0["name"] == "ビブラマイシン錠100mg"
    assert d0["quantity"] == 1.0  # 1回量
    assert d0["unit_price"] == 22.0  # 薬価
    assert d0["unit"] == "錠"
    assert drugs[2]["yj_code"] == "2655709N1096"
    assert drugs[2]["unit"] == "g"


def test_parse_extracts_record_7_fees():
    result = parse_nsips(_load())
    fees = result["fees"]
    assert len(fees) == 3
    codes = {f["code"] for f in fees}
    assert "470000210" in codes
    assert "999999999" in codes


def test_parse_extracts_record_6_fee_with_code_name():
    """record 6 でも code/name (position 8/9) が入っている行は fee 記録する。"""
    body = "6,2,10,63,1,73,80,153,430003670,計量混合加算　軟・硬膏剤,,,,,,,,,,,,,,,,,,,0\n"
    result = parse_nsips(body)
    assert len(result["fees"]) == 1
    fee = result["fees"][0]
    assert fee["fee_type"] == "6"
    assert fee["code"] == "430003670"
    assert "計量混合加算" in fee["name"]
    assert fee["points"] == 80


def test_parse_skips_record_6_without_code_name():
    """record 6 で code/name 無しは 調剤料内訳、skip。"""
    body = "6,1,10,19,1,29,0,29,,,,,,,,,,,,,,10\n"
    result = parse_nsips(body)
    assert result["fees"] == []


def test_parse_defensive_short_line():
    txt = "4,1\n"
    result = parse_nsips(txt)
    assert result["drugs"][0]["yj_code"] is None


def test_parse_empty_input():
    result = parse_nsips("")
    assert result == {
        "prescription": {}, "drugs": [], "fees": [], "rps": [], "drug_pricings": [], "totals": {},
    }


def test_parse_extracts_totals_from_record_5():
    """record 5 の全体集計 (請求点数、患者負担金 等) を抽出。"""
    body = "5,84,24,119,0,329,0,62,40,59,0,60,329,990,0,0,0,990,990,990,0,0,0\n"
    result = parse_nsips(body)
    t = result["totals"]
    assert t["total_points"] == 329
    assert t["dispensing_base_fee"] == 62
    assert t["night_holiday_fee"] == 40
    assert t["management_fee"] == 59
    assert t["long_prescription_fee"] == 60
    assert t["patient_copay"] == 990


def test_parse_extracts_drug_pricing_from_record_6():
    """record 6 の 基本料バリアント (code/name なし) を drug_pricings に格納。
    24 + 3*28 = 108 の検証。
    """
    body = "6,1,24,3,28,108,0,108,,,,,,,,,,,,,,,,,,,,,60\n"
    result = parse_nsips(body)
    assert len(result["drug_pricings"]) == 1
    dp = result["drug_pricings"][0]
    assert dp["dispensing_fee"] == 24
    assert dp["drug_fee_per_unit"] == 3
    assert dp["quantity"] == 28
    assert dp["total"] == 108
    # fees は空 (加算料ではない)
    assert result["fees"] == []


def test_parse_record_6_external_beyond_3rd_has_zero_dispensing():
    """外用 4 剤目以降は 調剤料=0 (実データ通り記録するだけ)"""
    body = "6,5,0,32,1,32,0,32,,,,,,,,,,,,,,,,,,,,,0\n"
    result = parse_nsips(body)
    dp = result["drug_pricings"][0]
    assert dp["dispensing_fee"] == 0
    assert dp["drug_fee_per_unit"] == 32
    assert dp["total"] == 32
