from pathlib import Path

from nsips_parser import parse_nsips


FIXTURE = Path(__file__).parent / "fixtures" / "sample_nsips.txt"


def _load() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_returns_dict_with_expected_keys():
    result = parse_nsips(_load())
    assert set(result.keys()) == {"prescription", "drugs", "fees"}


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
    assert d0["quantity"] == 22.0
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


def test_parse_defensive_short_line():
    txt = "4,1\n"
    result = parse_nsips(txt)
    assert result["drugs"][0]["yj_code"] is None


def test_parse_empty_input():
    result = parse_nsips("")
    assert result == {"prescription": {}, "drugs": [], "fees": []}
