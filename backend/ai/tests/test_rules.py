"""Label–value pairing, rule-based extraction, label fill of the LLM path, OCR fallback and word-box spacing."""

import numpy as np
import pytest

from ai.extract import extract_fields, format_lines
from ai.extract.rules import cell_pairs, extract_rule_based, has_content, inline_pairs, rule_values, table_label_hints
from ai.ocr.engines import FallbackEngine, OcrLine, OcrUnavailableError, spaced_text
from ai.tests.test_extract_risk import FakeLLM


def ln(i: int, text: str, bbox=(0.1, 0.0, 0.9, 0.0), cell=None, page=1) -> dict:
    x0, _, x1, _ = bbox
    y0 = bbox[1] if bbox[1] else 0.05 + i * 0.02
    y1 = bbox[3] if bbox[3] else y0 + 0.012
    return {"page_no": page, "line_id": f"L{page}-{i}", "text": text, "bbox": [x0, y0, x1, y1], "confidence": 1.0, "source": "pdf_text", "table_cell": cell}


def test_blank_form_values_have_no_content():
    for blank in ("일금          원정 (￦            )", "제   호", ".     .     .", "(     )%", "년   월   일", "(인)", ""):
        assert not has_content(blank), blank
    assert has_content("금 칠억육천만원정(￦760,000,000)")


def test_inline_pairs_cut_at_the_next_label_and_carry_the_role():
    assert inline_pairs("5. 계 약 금 액 : 일금 육억팔천칠백만원정 (￦687,000,000)") == [("계약금액", "일금 육억팔천칠백만원정 (￦687,000,000)")]
    pairs = dict(inline_pairs("* 원사업자 주소 : 상호 : 가온산업(주) 등록번호 및 신고번호 : 전화 및 팩스 :"))
    assert pairs["원사업자.상호"] == "가온산업(주)"
    pairs = dict(inline_pairs("상호 또는 명칭 : (주)미래기계 전화번호 : 주 소 : 대표자 성명 : (인)"))
    assert pairs["상호또는명칭"] == "(주)미래기계"


def test_merged_label_cell_pairs_with_both_value_rows():
    # "계약기간" spans two rows; its text sits between them
    lines = [
        ln(1, "계약기간", (0.10, 0.30, 0.20, 0.32), "r3,c1"),
        ln(2, "착공 2026. 3. 2.", (0.30, 0.285, 0.50, 0.297), "r3,c2"),
        ln(3, "준공 2026. 9. 30.", (0.30, 0.322, 0.50, 0.334), "r4,c2"),
        ln(4, "하자담보책임기간", (0.60, 0.40, 0.75, 0.412), "r5,c4"),
        ln(5, "2026. 10. 1.~2028. 9. 30.", (0.58, 0.43, 0.76, 0.442), "r6,c4"),
    ]
    got = {(lab["text"], val["text"], kind) for lab, val, kind in cell_pairs(lines)}
    assert ("계약기간", "착공 2026. 3. 2.", "cell") in got
    assert ("계약기간", "준공 2026. 9. 30.", "cell") in got
    assert ("하자담보책임기간", "2026. 10. 1.~2028. 9. 30.", "header") in got
    hints = table_label_hints(lines)
    assert hints["L1-5"] == "하자담보책임기간"
    assert "[표 r6,c4 · 하자담보책임기간] 2026. 10. 1.~2028. 9. 30." in format_lines(lines, hints)


def table_form() -> list[dict]:
    """국가계약법 공사도급표준계약서 layout: label cells left, values right, blanks in between."""
    return [
        ln(1, "공사도급표준계약서", (0.2, 0.12, 0.4, 0.14), "r1,c2"),
        ln(2, "발주처", (0.18, 0.169, 0.235, 0.18), "r2,c2"),
        ln(3, "누리도 건설본부장", (0.30, 0.167, 0.41, 0.181), "r2,c3"),
        ln(4, "공사명", (0.18, 0.249, 0.235, 0.261), "r6,c2"),
        ln(5, "새솔군 정수장 노후관 교체 공사", (0.30, 0.247, 0.48, 0.262), "r6,c3"),
        ln(6, "계약금액", (0.17, 0.28, 0.245, 0.292), "r7,c2"),
        ln(7, "금 칠억육천만원정(￦760,000,000)", (0.30, 0.278, 0.50, 0.293), "r7,c3"),
        ln(8, "총공사부기금액", (0.16, 0.311, 0.256, 0.323), "r8,c2"),
        ln(9, "금                  원정(￦             )", (0.30, 0.311, 0.58, 0.323), "r8,c3"),
        ln(10, "계약보증금", (0.16, 0.343, 0.256, 0.354), "r9,c2"),
        ln(11, "금 일억천사백만원정(￦114,000,000)", (0.30, 0.34, 0.51, 0.355), "r9,c3"),
        ln(12, "준공연월일", (0.16, 0.499, 0.256, 0.511), "r16,c2"),
        ln(13, "2027. 3. 2.", (0.30, 0.497, 0.36, 0.512), "r16,c3"),
        ln(14, "의 증거로서 계약서를 작성하여 당사자가 기명날인한 후 각각 1통씩 보관한다.", (0.1, 0.736, 0.6, 0.748)),
        ln(15, "2026. 6. 23.", (0.31, 0.846, 0.38, 0.861)),
        ln(16, "계약담당공무원                (인)", (0.4, 0.874, 0.75, 0.886)),
    ]


def test_rule_values_on_a_table_form():
    got = {code: (rv.raw if rv else None) for code, rv in rule_values(table_form()).items()}
    assert got == {
        "contract_name": "새솔군 정수장 노후관 교체 공사",
        "contract_amount": "금 칠억육천만원정(￦760,000,000)",
        "guarantee_amount": "금 일억천사백만원정(￦114,000,000)",
        "contract_date": "2026. 6. 23.",
        "performance_due_date": "2027. 3. 2.",
        "guarantee_period": None,
        "creditor_name": "누리도 건설본부장",
        "creditor_biz_no": None,
    }


def test_rule_values_on_an_inline_subcontract_form():
    lines = [
        ln(1, "건설업종 표준하도급계약서(전문)"),
        ln(2, "1. 발   주   자 :"),
        ln(3, "ㅇ 도급공사명 :"),
        ln(4, "2. 하도급공사명 : 새솔군 정수장 노후관 교체 공사"),
        ln(5, "4. 공 사 기 간 : 착공 2026년 2월 28일"),
        ln(6, "준공 2026년 8월 15일"),
        ln(7, "5. 계 약 금 액 : 일금 육억팔천칠백만원정 (￦687,000,000)"),
        ln(8, "9. 계약이행보증금"),
        ln(9, "ㅇ 계약금액의 (  )%, 일금 일억삼백오만원정 (￦103,050,000)"),
        ln(10, "다. 하자담보책임기간 :       년"),
        ln(11, "등에 따라 하도급 계약을 체결하고 계약서 2통을 작성하여 기명날"),
        ln(12, "2026년 2월 24일"),
        ln(13, "원사업자 | 수급사업자"),
        ln(14, "상호 또는 명칭 : (주)서해엔지니어링 전화번호 : 주 소 : 대표자 성명 : (인) 사 | 상호 또는 명칭 : (주)솔빛화학 전화번호 :"),
        ln(15, "업자(법인)번호 : 898-26-37336 | 사업자(법인)번호 : 214-86-11115"),
    ]
    got = {code: (rv.raw if rv else None) for code, rv in rule_values(lines).items()}
    assert got["contract_name"] == "새솔군 정수장 노후관 교체 공사"
    assert got["contract_amount"] == "일금 육억팔천칠백만원정 (￦687,000,000)"
    assert got["guarantee_amount"] == "계약금액의 (  )%, 일금 일억삼백오만원정 (￦103,050,000)"
    assert got["performance_due_date"] == "2026년 8월 15일"
    assert got["contract_date"] == "2026년 2월 24일"
    assert got["guarantee_period"] is None  # "      년" is a blank
    assert got["creditor_name"] == "(주)서해엔지니어링"  # 원사업자 column, not 수급사업자
    assert got["creditor_biz_no"] == "898-26-37336"


def test_period_end_is_the_due_date_and_the_highlight_covers_only_it():
    lines = [ln(1, "물 품 계 약 서"), ln(2, "◇ 계약명 : 제설용 염화칼슘 구매"), ln(3, "◇ 계약기간  :    2026년 1월 14일부터 2026년 7월 20일까지")]
    fields = {f["field_code"]: f for f in extract_rule_based(lines)}
    due = fields["performance_due_date"]
    assert due["raw_value"] == "2026년 7월 20일" and due["normalized_value"] == {"date": "2026-07-20"}
    assert due["highlights"][0]["bbox"][0] > 0.4  # partial box over the end date, not the whole line


def test_payment_slip_creditor_is_the_addressee_and_has_no_contract_date():
    lines = [
        ln(1, "계 약 보 증 금 납 부 서"),
        ln(2, "계약건명 : 가람초등학교 강당 증축 공사"),
        ln(3, "위의 금액을 계약보증금으로 납부합니다. 2026. 2. 6."),
        ln(4, "주민(법인)등록번호 : 새솔군 상하수도사업소장 귀하"),
    ]
    got = {code: (rv.raw if rv else None) for code, rv in rule_values(lines).items()}
    assert got["creditor_name"] == "새솔군 상하수도사업소장"
    assert got["contract_date"] is None


def test_prose_and_official_titles_are_not_values():
    lines = [
        ln(1, "하도급계약명 :"),
        ln(2, "제1조(목적) 이 계약은 원사업자와 수급사업자가 체결한 위의 하도급계약(이하 하도급계약"),
        ln(3, "발주자 : 세입세출외현금출납원"),
    ]
    got = rule_values(lines)
    assert got["contract_name"] is None and got["creditor_name"] is None


def test_llm_empty_fields_are_filled_from_labels():
    lines = table_form()
    extract = {code: {"raw_value": None, "evidence_line_ids": [], "confidence": 1} for code in rule_values(lines)}
    extract["contract_name"] = {"raw_value": "새솔군 정수장 노후관 교체 공사", "evidence_line_ids": ["L1-5"], "confidence": 1}
    llm = FakeLLM(extract=extract)
    fields, meta = extract_fields(lines, llm)
    by = {f["field_code"]: f for f in fields}
    assert by["contract_amount"]["normalized_value"]["amount"] == 760_000_000
    assert by["guarantee_amount"]["normalized_value"]["amount"] == 114_000_000
    assert by["creditor_name"]["raw_value"] == "누리도 건설본부장"
    assert by["contract_amount"]["mapping_method"] == "llm_ref"
    assert "contract_name" not in meta["raw_llm_output"]["_label_fill"]  # the model's own answer is kept
    assert "[표 r6,c3 · 공사명] 새솔군" in llm.calls[0][2]


def test_spaced_text_from_word_gaps():
    words = ["새솔군", "정수장", "노후관", "교체", "공사"]
    boxes, x = [], 0.0
    for w in words:
        boxes.append([x, 0, x + 30 * len(w), 30])
        x += 30 * len(w) + 14  # ~half a glyph apart
    assert spaced_text(words, boxes) == "새솔군 정수장 노후관 교체 공사"
    tight = [[i * 30.0, 0, i * 30.0 + 30, 30] for i in range(3)]
    assert spaced_text(["확", "장", "공"], tight) == "확장공"


class _Remote:
    source = "paddle"

    def __init__(self, fail):
        self.fail, self.calls = fail, 0

    def run(self, image):
        self.calls += 1
        if self.fail:
            raise OcrUnavailableError("down")
        return [OcrLine("원격", (0, 0, 1, 1), 1.0)]


class _Local:
    name, source = "tesseract", "tesseract"

    def run(self, image):
        return [OcrLine("로컬", (0, 0, 1, 1), 0.9)]


@pytest.mark.parametrize("fail", [False, True])
def test_fallback_engine_uses_cpu_when_the_gpu_server_is_down(fail):
    engine = FallbackEngine(_Remote(fail))
    engine._local = _Local()
    img = np.zeros((4, 4, 3), np.uint8)
    assert engine.run(img)[0].text == ("로컬" if fail else "원격")
    assert engine.source == ("tesseract" if fail else "paddle")
    engine.run(img)
    assert engine.remote.calls == 1 if fail else 2  # down -> not retried within RETRY_AFTER
