"""AI·Document <-> Backend contact points: 03_데이터정의 columns (extractions meta, pages.image_path, risk_rules doc rows,
llm_cache) and the FR-09 POLICY_VIOLATION path (regulation RAG search -> LLM engine -> finding with regulation refs)."""

import uuid

import pymupdf as fitz

from ai.llm import LLMClient
from app.db.session import SessionLocal
from app.models.document import Page
from app.models.extraction import Extraction
from app.models.llm_cache import LlmCache
from app.models.regulation import RegulationChunk
from app.models.risk_rule import RiskRule
from app.services import ai_client
from app.services.llm_cache import DbLlmCache
from tests.helpers import upload_and_wait_document, upload_and_wait_regulation
from tests.pdf_fixtures import CONTRACT_LINES


def test_extraction_meta_and_page_images_are_stored(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    with SessionLocal() as db:
        extraction = db.query(Extraction).filter(Extraction.document_id == uuid.UUID(doc_id)).one()
        assert (extraction.model_name, extraction.prompt_version, extraction.raw_llm_output) == ("rule-based-v1", "rule-based-v1", None)
        page = db.query(Page).filter(Page.document_id == uuid.UUID(doc_id), Page.page_no == 1).one()

    assert page.image_path and page.image_path.endswith(f"{doc_id}/1.png")
    pix = fitz.Pixmap(page.image_path)
    assert (pix.width, pix.height) == (round(page.width_pt * 200 / 72), round(page.height_pt * 200 / 72))  # 200dpi

    r = client.get(f"/api/v1/documents/{doc_id}/pages/1/image", headers=admin_headers)
    assert r.status_code == 200
    with open(page.image_path, "rb") as f:
        assert r.content == f.read()  # served from the stored file, not re-rendered


def test_doc_risk_rules_are_seeded_from_rules_yaml(client):
    with SessionLocal() as db:
        rows = {r.rule_code: r for r in db.query(RiskRule).filter(RiskRule.engine.is_not(None)).all()}
        legacy_keyword = db.query(RiskRule).filter(RiskRule.rule_type == "keyword", RiskRule.engine.is_(None)).count()
    assert set(rows) == {"PENALTY_RATE_HIGH", "MISSING_ARTICLE", "AMOUNT_MISMATCH", "DATE_INCONSISTENT", "TOXIC_CLAUSE", "CONTRADICTION_LLM", "POLICY_VIOLATION"}
    assert rows["PENALTY_RATE_HIGH"].params["max_rate_per_day"] == 0.001
    assert rows["POLICY_VIOLATION"].engine == "llm" and rows["POLICY_VIOLATION"].default_severity == "MEDIUM"
    assert legacy_keyword >= 2  # offline keyword rows keep their role


def test_only_passed_doc_rules_run():
    lines = [{"page_no": 1, "line_id": f"L1-{i}", "text": t, "bbox": [0, 0, 1, 1], "confidence": 1.0, "source": "pdf_text", "table_cell": None} for i, t in enumerate(CONTRACT_LINES, 1)]
    penalty = {k: v for k, v in ai_client.doc_risk_rules()[0].items() if k != "enabled"}
    assert penalty["rule_code"] == "PENALTY_RATE_HIGH"
    assert {f["rule_code"] for f in ai_client.detect_risks(lines, [], [penalty])} == {"PENALTY_RATE_HIGH"}  # 3/1000 > 1/1000
    assert ai_client.detect_risks(lines, [], []) == []


def test_db_llm_cache_stores_and_reuses_responses(client, monkeypatch):
    calls = []

    def post(path, body):
        calls.append(body)
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    model = f"cache-test-{uuid.uuid4().hex[:8]}"
    llm = LLMClient("http://unused", model, cache=DbLlmCache(model))
    monkeypatch.setattr(llm, "_post", post)
    assert llm.chat_json("sys", "prompt", {}, prompt_version="v1") == {"ok": True}
    assert llm.chat_json("sys", "prompt", {}, prompt_version="v1") == {"ok": True}
    assert len(calls) == 1
    with SessionLocal() as db:
        row = db.query(LlmCache).filter(LlmCache.model_name == model).one()
    assert row.response == {"ok": True} and len(row.prompt_hash) == 64


class _PolicyFakeLLM:
    """Answers only the POLICY_VIOLATION prompt (the one carrying [내부 규정]); other LLM rules find nothing."""

    model = "fake-llm"

    def __init__(self):
        self.policy_prompts: list[str] = []

    def chat_json(self, system, prompt, schema, *, prompt_version, name="output"):
        if not prompt.startswith("[내부 규정]"):
            return {"findings": []}
        self.policy_prompts.append(prompt)
        finding = {
            "title": "Guarantee amount below the regulation minimum",
            "description": "The contract guarantee is lower than the internal regulation requires.",
            "evidence_line_ids": ["L1-6"],
            "evidence_quotes": ["Contract Guarantee Amount : KRW 35,000,000"],
            "score": 0.8,
            "regulation_refs": [1],
        }
        return {"findings": [finding]}


def test_policy_violation_uses_regulation_search_and_stores_refs(client, admin_headers, monkeypatch):
    upload_and_wait_regulation(client, admin_headers, title="계약사무규정")
    doc_id = upload_and_wait_document(client, admin_headers)

    fake = _PolicyFakeLLM()
    monkeypatch.setattr(ai_client.LLMClient, "from_env", classmethod(lambda cls, cache=None: fake))
    assert client.post(f"/api/v1/documents/{doc_id}/risks/rerun", headers=admin_headers).status_code == 202
    assert client.get(f"/api/v1/documents/{doc_id}/status", headers=admin_headers).json()["status"] == "DONE"

    items = client.get(f"/api/v1/documents/{doc_id}/risks", headers=admin_headers).json()["items"]
    policy = next(i for i in items if i["rule_code"] == "POLICY_VIOLATION")
    assert policy["category"] == "policy" and policy["highlights"][0]["ocr_line_id"] == "L1-6"
    refs = policy["llm_reasoning"]["regulation_refs"]
    assert len(refs) == 1 and refs[0]["path"]

    with SessionLocal() as db:
        chunk = db.get(RegulationChunk, uuid.UUID(refs[0]["chunk_id"]))
    assert chunk is not None and str(chunk.regulation_id) == refs[0]["regulation_id"]
    # policy_search returned real regulation chunks: the cited one was in the LLM prompt as [규정 1]
    assert f"[규정 1] {refs[0]['regulation_title']} > {refs[0]['path']}\n{chunk.content}" in fake.policy_prompts[0]
