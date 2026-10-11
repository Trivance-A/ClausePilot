import json
import os
import urllib.error

import pytest

from ai.extract import SCHEMA, extract_fields, select_lines
from ai.llm import LLMClient, LLMUnavailableError, prompt_hash
from ai.ocr import run_ocr
from ai.risk import (
    detect_risks,
    load_rules,
    merge_findings,
    penalty_rates,
    policy_query,
    severity_of,
)
from ai.tests.fixtures import contract_pdf
from ai.types import FIELD_CODES


class FakeLLM:
    """Routes by prompt_version; records calls."""

    model = "fake-7b"

    def __init__(self, extract=None, requery=None, risk=None):
        self.extract, self.requery, self.risk = extract or {}, requery or {"evidence_line_ids": []}, risk or {}
        self.calls = []

    def chat_json(self, system, prompt, schema, *, prompt_version, name="output"):
        self.calls.append((prompt_version, system, prompt))
        if prompt_version.startswith("extract"):
            return self.extract
        if prompt_version.startswith("requery"):
            return self.requery
        for code, out in self.risk.items():
            if code in system or code in prompt:
                return out
        return {"findings": []}


@pytest.fixture(scope="module")
def lines(tmp_path_factory):
    return run_ocr(contract_pdf(str(tmp_path_factory.mktemp("c") / "c.pdf")))


def f(raw, *ids, conf=1.0):
    return {"raw_value": raw, "evidence_line_ids": list(ids), "confidence": conf}


def test_schema_never_uses_anyof_null():
    assert "anyOf" not in json.dumps(SCHEMA)
    assert set(SCHEMA["required"]) == set(FIELD_CODES)


def test_extract_fields_end_to_end(lines):
    by_text = {ln["text"]: ln["line_id"] for ln in lines}
    amount_line = next(i for t, i in by_text.items() if "계약금액" in t)
    llm = FakeLLM(
        extract={
            "contract_name": f("한빛시 도로 확장공사", "[L1-2]"),
            "contract_amount": f("일금 삼억오천만원정 (₩350,000,000)", f"{amount_line}: 2. 계약금액"),
            "guarantee_amount": f("금 삼천오백만원정 (₩35,000,000)", "L1-1"),  # wrong line -> exact search
            "contract_date": f("2026년 3월 5일"),
            "performance_due_date": f("2026. 12. 31."),
            "guarantee_period": f("계약일로부터 준공일까지"),
            "creditor_name": f("주식회사 한빛도시공사"),
            "creditor_biz_no": f("없음"),  # blank-ish -> null
        }
    )
    fields, meta = extract_fields(lines, llm)
    by = {x["field_code"]: x for x in fields}
    assert [x["field_code"] for x in fields] == FIELD_CODES
    assert by["contract_name"]["mapping_method"] == "llm_ref"
    assert by["contract_amount"]["mapping_method"] == "llm_ref" and by["contract_amount"]["normalized_value"] == {"amount": 350_000_000}
    assert by["guarantee_amount"]["mapping_method"] == "exact"
    assert by["guarantee_period"]["normalized_value"] == {"start": "2026-03-05", "end": "2026-12-31", "derived": True}
    assert by["creditor_name"]["normalized_value"] == {"text": "(주)한빛도시공사"}
    assert by["creditor_biz_no"] == {
        "field_code": "creditor_biz_no",
        "raw_value": None,
        "normalized_value": None,
        "confidence": 0.0,
        "mapping_method": "none",
        "highlights": [],
    }
    assert all(h["ocr_line_id"] and len(h["bbox"]) == 4 for x in fields for h in x["highlights"])
    assert by["contract_name"]["confidence"] > by["guarantee_amount"]["confidence"] > 0
    assert meta == {"model_name": "fake-7b", "prompt_version": "extract-v1", "raw_llm_output": llm.extract}
    assert "L1-1: 공 사 도 급 계 약 서" in llm.calls[0][2]


def test_value_not_in_document_is_dropped_as_fabricated(lines):
    llm = FakeLLM(extract={"contract_name": f("존재하지 않는 공사명 ABC")}, requery={"evidence_line_ids": ["L1-2"]})
    fields, meta = extract_fields(lines, llm)
    assert fields[0] == {
        "field_code": "contract_name",
        "raw_value": None,
        "normalized_value": None,
        "confidence": 0.0,
        "mapping_method": "none",
        "highlights": [],
    }
    assert meta["raw_llm_output"]["contract_name"]["raw_value"] == "존재하지 않는 공사명 ABC"  # kept for audit only
    assert any(v.startswith("requery") for v, _, _ in llm.calls)


def test_ocr_garbled_lookalike_is_kept_for_manual_fix(lines):
    fields, _ = extract_fields(lines, FakeLLM(extract={"contract_name": f("한빛시 도로 확장공샤 2단계")}))
    assert fields[0]["raw_value"] == "한빛시 도로 확장공샤 2단계" and fields[0]["mapping_method"] == "none"


def test_long_documents_are_windowed():
    many = [
        {
            "page_no": p,
            "line_id": f"L{p}-{i}",
            "text": "계약금액 금 일억원" if (p, i) == (7, 5) else "본문",
            "bbox": [0, 0, 1, 1],
            "confidence": 1,
            "source": "pdf_text",
            "table_cell": None,
        }
        for p in range(1, 9)
        for i in range(1, 40)
    ]
    picked = select_lines(many)
    assert len(picked) == 21 and picked[10]["line_id"] == "L7-5"


def test_penalty_rate_parsing():
    assert penalty_rates("계약금액의 1000분의 3") == [0.003]
    assert penalty_rates("1천분의 0.5") == [0.0005]
    assert penalty_rates("3/1000") == [0.003]
    assert penalty_rates("0.3%") == [0.003]


def test_rule_engine(lines):
    fields = [
        {
            "field_code": "contract_amount",
            "raw_value": "금 삼억원정 (₩350,000,000)",
            "normalized_value": {"amount": 350_000_000},
            "highlights": [{"page_no": 1, "bbox": [0, 0, 1, 1], "ocr_line_id": "L1-99"}],
        },
        {"field_code": "contract_date", "raw_value": "2027.1.1", "normalized_value": {"date": "2027-01-01"}, "highlights": []},
        {"field_code": "performance_due_date", "raw_value": "2026.12.31", "normalized_value": {"date": "2026-12-31"}, "highlights": []},
    ]
    found = detect_risks(lines, fields, llm=None)
    codes = [r["rule_code"] for r in found]
    assert "PENALTY_RATE_HIGH" in codes and "AMOUNT_MISMATCH" in codes and "DATE_INCONSISTENT" in codes
    assert "MISSING_ARTICLE" not in codes  # fixture has all 5 required articles
    penalty = next(r for r in found if r["rule_code"] == "PENALTY_RATE_HIGH")
    assert penalty["severity"] == "HIGH" and penalty["category"] == "penalty"
    assert penalty["highlights"][0]["ocr_line_id"] and "1000분의 3" in penalty["evidence_text"]


def test_missing_articles():
    lines = [
        {
            "page_no": 1,
            "line_id": "L1-1",
            "text": "합병계약서 제1조(합병) 갑은 을을 합병한다",
            "bbox": [0, 0, 1, 1],
            "confidence": 1,
            "source": "pdf_text",
            "table_cell": None,
        }
    ]
    found = detect_risks(lines, [], llm=None)
    assert sorted(r["title"].split(": ")[1] for r in found) == ["계약금액", "계약기간", "계약해지", "지체상금", "하자담보"]
    assert all(r["highlights"] == [] and r["evidence_text"] is None and r["severity"] == "MEDIUM" for r in found)


def test_cap_clause_is_not_a_daily_rate():
    lines = [
        {
            "page_no": 1,
            "line_id": "L1-1",
            "text": "지체상금은 계약금액의 100분의 30을 초과할 수 없다.",
            "bbox": [0, 0, 1, 1],
            "confidence": 1,
            "source": "pdf_text",
            "table_cell": None,
        }
    ]
    assert not [r for r in detect_risks(lines, [], llm=None) if r["rule_code"] == "PENALTY_RATE_HIGH"]


def test_llm_findings_must_quote_the_contract(lines):
    toxic = {
        "findings": [
            {
                "title": "일방적 계약해지",
                "description": "갑만 사전 통보 없이 해지 가능",
                "evidence_line_ids": ["[L1-14]"],
                "evidence_quotes": ["사전 통보 없이 언제든지 계약을 해지할 수 있으며"],
                "score": 0.9,
            },
            {
                "title": "인용 불일치",
                "description": "환각",
                "evidence_line_ids": ["L1-14"],
                "evidence_quotes": ["을은 언제든지 위약금 없이 해지할 수 있다"],
                "score": 0.9,
            },
            {"title": "인용 없음", "description": "환각", "evidence_line_ids": ["L1-14"], "evidence_quotes": [], "score": 0.9},
            {"title": "없는 라인", "description": "환각", "evidence_line_ids": ["L9-9"], "evidence_quotes": ["존재하지 않는 조항"], "score": 0.9},
        ]
    }
    found = {r["title"]: r for r in detect_risks(lines, [], llm=FakeLLM(risk={"독소조항": toxic})) if r["category"] == "toxic"}
    assert set(found) == {"일방적 계약해지"}
    hit = found["일방적 계약해지"]
    assert hit["severity"] == "HIGH" and hit["highlights"][0]["ocr_line_id"] == "L1-14"
    assert hit["highlights"][0]["bbox"][0] > lines[13]["bbox"][0]  # bbox of the quoted words, not the whole line


def test_contradictions_need_two_lines_and_real_numbers(lines):
    contra = {
        "findings": [
            {
                "title": "계약기간과 준공기한 불일치",
                "description": "제3조는 2026년 11월 30일, 준공기한은 2026. 12. 31.",
                "evidence_line_ids": ["L1-10", "L1-5"],
                "evidence_quotes": ["2026년 11월 30일까지로 한다", "준공기한 : 2026. 12. 31."],
                "score": 0.8,
            },
            {
                "title": "지체상금 과다",
                "description": "제8조: 1일 0.3%, 3억5천만원 기준이며 제9조 하자 2년",
                "evidence_line_ids": ["L1-12", "L1-13"],
                "evidence_quotes": ["1000분의 3", "준공 후 2년간 하자보수 책임"],
                "score": 0.6,
            },
            {
                "title": "자본금 모순",
                "description": "자본금이 1,000만원 증가한다고 되어 있으나 40% 차이",
                "evidence_line_ids": ["L1-3", "L1-6"],
                "evidence_quotes": ["일금 삼억오천만원정", "금 삼천오백만원정"],
                "score": 0.8,
            },
            {"title": "한 줄 모순", "description": "x", "evidence_line_ids": ["L1-14"], "evidence_quotes": ["사전 통보 없이"], "score": 0.8},
            {
                "title": "한 문장 두 줄",
                "description": "x",
                "evidence_line_ids": ["L1-14", "L1-15"],
                "evidence_quotes": ["사전 통보 없이 언제든지", "어떠한 이의나 손해배상도"],
                "score": 0.9,
            },
        ]
    }
    found = {r["title"]: r for r in detect_risks(lines, [], llm=FakeLLM(risk={"모순": contra})) if r["rule_code"] == "CONTRADICTION_LLM"}
    assert set(found) == {"계약기간과 준공기한 불일치", "지체상금 과다", "조항 간 모순"}
    assert {h["ocr_line_id"] for h in found["계약기간과 준공기한 불일치"]["highlights"]} == {"L1-5", "L1-10"}
    fabricated = found["조항 간 모순"]  # title/description replaced: the model invented 1,000만원 and 40%
    assert fabricated["llm_reasoning"]["ungrounded_numbers"] == ["1000만", "40"]
    assert "1,000만원" not in fabricated["description"] and "1,000만원" in fabricated["llm_reasoning"]["original_description"]
    assert fabricated["evidence_text"].startswith("2. 계약금액")


def test_policy_violation_needs_a_regulation_reference(lines):
    policy = {
        "findings": [
            {
                "title": "보증금률 확인",
                "description": "규정은 100분의 10 이상, 계약보증금은 35,000,000원",
                "evidence_line_ids": ["L1-6"],
                "evidence_quotes": ["계약보증금 : 금 삼천오백만원정"],
                "score": 0.5,
                "regulation_refs": [1, 7],
            },
            {
                "title": "참조 없음",
                "description": "x",
                "evidence_line_ids": ["L1-9"],
                "evidence_quotes": ["미래건설 주식회사"],
                "score": 0.5,
                "regulation_refs": [9],
            },
        ]
    }
    regs = [
        {
            "chunk_id": "c1",
            "regulation_id": "r1",
            "regulation_title": "계약사무규정",
            "path": "제3장>제12조(계약보증금)",
            "node_id": "n1",
            "content": "계약보증금은 계약금액의 100분의 10 이상",
        }
    ]
    queries = []
    found = {
        r["title"]: r
        for r in detect_risks(lines, [], llm=FakeLLM(risk={"내부 규정": policy}), policy_search=lambda q: queries.append(q) or regs)
        if r["category"] == "policy"
    }
    assert set(found) == {"보증금률 확인"}
    assert found["보증금률 확인"]["severity"] == "MEDIUM" and "ungrounded_numbers" not in found["보증금률 확인"]["llm_reasoning"]
    assert found["보증금률 확인"]["llm_reasoning"]["regulation_refs"] == [
        {"chunk_id": "c1", "regulation_id": "r1", "regulation_title": "계약사무규정", "path": "제3장>제12조(계약보증금)", "node_id": "n1"}
    ]
    assert "계약기간" in queries[0] and "지체상금" in queries[0]


def test_llm_failure_does_not_drop_rule_findings(lines):
    class Down(FakeLLM):
        def chat_json(self, *a, **k):
            raise LLMUnavailableError("down")

    assert any(r["rule_code"] == "PENALTY_RATE_HIGH" for r in detect_risks(lines, [], llm=Down()))


def test_merge_and_severity():
    hl = [{"page_no": 1, "bbox": [0, 0, 1, 1], "ocr_line_id": "L1-3"}]
    a = {"category": "toxic", "score": 0.9, "title": "a", "highlights": hl}
    b = {"category": "toxic", "score": 0.5, "title": "b", "highlights": hl}
    c = {"category": "penalty", "score": 0.5, "title": "c", "highlights": hl}
    assert [x["title"] for x in merge_findings([b, a, c])] == ["a", "c"]
    assert (severity_of(0.75), severity_of(0.45), severity_of(0.44)) == ("HIGH", "MEDIUM", "LOW")
    assert {r["code"] for r in load_rules()} == {
        "PENALTY_RATE_HIGH",
        "MISSING_ARTICLE",
        "AMOUNT_MISMATCH",
        "DATE_INCONSISTENT",
        "TOXIC_CLAUSE",
        "CONTRADICTION_LLM",
        "POLICY_VIOLATION",
    }
    assert policy_query([]).startswith("계약보증금")


def test_llm_client_cache_and_retry(monkeypatch):
    client = LLMClient("http://llm.invalid/v1", "m", cache={}, retries=2, backoff=0)
    calls = []

    def post(path, body):
        calls.append(body)
        assert body["response_format"]["type"] == "json_schema" and body["temperature"] == 0
        if len(calls) == 1:
            raise urllib.error.URLError("refused")
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    monkeypatch.setattr(client, "_post", post)
    assert client.chat_json("s", "p", {}, prompt_version="v1") == {"ok": True}
    assert client.chat_json("s", "p", {}, prompt_version="v1") == {"ok": True}  # cache hit
    assert len(calls) == 2
    assert prompt_hash("m", "v1", "s\np") in client.cache

    monkeypatch.setattr(client, "_post", lambda path, body: {"choices": [{"message": {"content": "not json"}}]})
    with pytest.raises(LLMUnavailableError):
        client.chat_json("s", "other", {}, prompt_version="v1")


def test_from_env(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    assert LLMClient.from_env() is None
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b")
    assert LLMClient.from_env().model == "qwen2.5:7b"


@pytest.mark.skipif(not os.getenv("LLM_LIVE_TEST"), reason="set LLM_LIVE_TEST=1 and LLM_BASE_URL to hit a real model")
def test_live_llm_extraction(lines):
    fields, _ = extract_fields(lines, LLMClient.from_env())
    by = {x["field_code"]: x for x in fields}
    assert by["contract_amount"]["normalized_value"] == {"amount": 350_000_000}
    assert by["contract_date"]["normalized_value"] == {"date": "2026-03-05"}
    assert sum(x["mapping_method"] != "none" for x in fields) >= 7
