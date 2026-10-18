from ai.mapping import clean_line_ids, locate, map_value, normalize


def line(no, text, bbox=(0.1, 0.1, 0.9, 0.12), page=1, cell=None):
    return {"page_no": page, "line_id": f"L{page}-{no}", "text": text, "bbox": list(bbox), "confidence": 1.0, "source": "pdf_text", "table_cell": cell}


LINES = [
    line(1, "공 사 도 급 계 약 서", (0.3, 0.05, 0.7, 0.07)),
    line(2, "2. 계약금액 : 일금 삼억오천만원정 (₩350,000,000)", (0.1, 0.10, 0.9, 0.12)),
    line(3, "3. 계약일자 : 2026년 3월 5일", (0.1, 0.13, 0.5, 0.15)),
    line(4, "7. 발주자 : 주식회사 한빛도시공사", (0.1, 0.16, 0.6, 0.18)),
    line(5, "(사업자등록번호 214-86-", (0.1, 0.19, 0.4, 0.21)),
    line(6, "11115)", (0.1, 0.22, 0.2, 0.24)),
]


def test_normalize_ignores_spacing_commas_and_date_separators():
    assert normalize("₩350,000,000") == normalize("350000000")
    assert normalize("2026년 3월 5일") == normalize("2026.3.5")
    assert normalize("ＡＢＣ") == "abc"  # full-width -> half-width


def test_llm_ref_with_partial_bbox():
    method, hl, _ = map_value("2026년 3월 5일", LINES, ["[L1-3]"])
    assert method == "llm_ref"
    assert hl[0]["ocr_line_id"] == "L1-3"
    x0, y0, x1, y1 = hl[0]["bbox"]
    assert 0.1 < x0 < x1 <= 0.5 + 1e-9 and (y0, y1) == (0.13, 0.15)  # value only, not the label


def test_exact_when_llm_cites_wrong_line():
    method, hl, _ = map_value("일금 삼억오천만원정 (₩350,000,000)", LINES, ["L1-1"])
    assert method == "exact" and hl[0]["ocr_line_id"] == "L1-2"


def test_value_broken_over_two_lines():
    method, hl, _ = map_value("214-86-11115", LINES, [])
    assert method == "exact"
    assert [h["ocr_line_id"] for h in hl] == ["L1-5", "L1-6"]


def test_fuzzy_on_ocr_misread():
    ocr = [line(1, "계약금액 : 금 삼억오천만원정 (W350, 000, 0O0)")]
    method, hl, score = map_value("금 삼억오천만원정 (₩350,000,000)", ocr, [])
    assert method == "fuzzy" and score >= 85 and hl[0]["ocr_line_id"] == "L1-1"


def test_requery_then_none():
    calls = []

    def requery():
        calls.append(1)
        return ["L1-4"]

    method, hl, _ = map_value("(주)한빛도시공사", LINES, [], requery)
    assert method in ("exact", "fuzzy", "llm_ref") and hl  # "주식회사 한빛도시공사" still resembles it

    method, hl, _ = map_value("전혀 없는 값입니다", LINES, [], requery)
    assert (method, hl) == ("none", [])
    assert calls  # 4th stage was tried


def test_null_value_maps_to_none():
    assert map_value(None, LINES, ["L1-2"]) == ("none", [], 0.0)


def test_clean_line_ids_strips_llm_noise():
    by_id = {ln["line_id"]: ln for ln in LINES}
    assert clean_line_ids(["[L1-3]", "L1-2: 계약금액", "L9-9", "L1-3"], by_id) == ["L1-2", "L1-3"]


def test_locate_returns_none_when_missing():
    assert locate("없음", LINES) is None
