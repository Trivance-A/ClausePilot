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


def test_value_not_in_document_is_requeried_then_none(lines):
    llm = FakeLLM(extract={"contract_name": f("존재하지 않는 공사명 ABC")}, requery={"evidence_line_ids": ["L1-2"]})
    fields, _ = extract_fields(lines, llm)
    name = fields[0]
    assert name["mapping_method"] == "none" and name["highlights"] == [] and name["raw_value"] == "존재하지 않는 공사명 ABC"
    assert any(v.startswith("requery") for v, _, _ in llm.calls)


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


def test_llm_engine_keeps_only_evidenced_findings(lines):
    toxic = {
        "findings": [
            {"title": "일방적 계약해지", "description": "갑만 해지 가능", "evidence_line_ids": ["[L1-14]"], "score": 0.9},
            {"title": "근거 없음", "description": "환각", "evidence_line_ids": ["L9-9"], "score": 0.9},
        ]
    }
    policy = {
        "findings": [{"title": "보증금률 미달", "description": "규정은 10% 이상", "evidence_line_ids": ["L1-6"], "score": 0.5, "regulation_refs": [1, 7]}]
    }
    llm = FakeLLM(risk={"독소조항": toxic, "내부 규정": policy})
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
    found = detect_risks(lines, [], llm=llm, policy_search=lambda q: queries.append(q) or regs)
    titles = {r["title"]: r for r in found}
    assert "근거 없음" not in titles
    assert titles["일방적 계약해지"]["severity"] == "HIGH" and titles["일방적 계약해지"]["highlights"][0]["ocr_line_id"] == "L1-14"
    pv = titles["보증금률 미달"]
    assert pv["category"] == "policy" and pv["severity"] == "MEDIUM"
    assert pv["llm_reasoning"]["regulation_refs"] == [
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
