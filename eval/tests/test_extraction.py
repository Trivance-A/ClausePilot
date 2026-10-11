import csv
import json

import pytest
from ai.extract.normalize import biz_no_checksum_ok, normalize_amount
from ai.types import FIELD_CODES

from eval import make_synthetic_gold as synth
from eval.extraction import compare_field, evaluate, llm_extractor, rule_extractor, score_doc, write_outputs
from eval.gold import load_gold, validate_gold


class FakeLLM:
    """Answers the extract prompt with fixed raw values (same contract as ai.llm.LLMClient.chat_json)."""

    model = "fake-7b"

    def __init__(self, raw: dict):
        self.raw = raw
        self.calls = 0

    def chat_json(self, system, prompt, schema, *, prompt_version, name="output"):
        self.calls += 1
        if prompt_version.startswith("requery"):
            return {"evidence_line_ids": []}
        return {code: {"raw_value": self.raw.get(code), "evidence_line_ids": [], "confidence": 1.0} for code in FIELD_CODES}


def label(value, page=1, bbox=(0.1, 0.1, 0.4, 0.12)):
    return {"value": value, "page": page, "bbox": list(bbox), "raw_text": str(value)}


def pred(raw, normalized, method="exact", hl=((1, (0.1, 0.1, 0.4, 0.12)),)):
    return {
        "raw_value": raw,
        "normalized_value": normalized,
        "mapping_method": method,
        "highlights": [{"page_no": p, "bbox": list(b), "ocr_line_id": None} for p, b in hl],
    }


# ---------- normalized comparison ----------


@pytest.mark.parametrize(
    ("code", "gold", "normalized"),
    [
        ("contract_amount", 350_000_000, {"amount": 350_000_000}),
        ("contract_amount", "일금 삼억오천만원정", {"amount": 350_000_000}),  # gold may be written text too
        ("contract_date", "2026-03-05", {"date": "2026-03-05"}),
        ("contract_date", "2026년 3월 5일", {"date": "2026-03-05"}),
        ("guarantee_period", {"start": "2026-03-05", "end": "2026-12-31"}, {"start": "2026-03-05", "end": "2026-12-31", "derived": True}),
        ("creditor_name", "주식회사 한빛도시공사", {"text": "(주) 한빛도시공사"}),
        ("creditor_name", "㈜한빛", {"text": "(주)한빛"}),
        ("creditor_biz_no", "2148611115", {"text": "214-86-11115", "checksum_valid": True}),
        ("contract_name", "한빛시  도로 확장공사", {"text": "한빛시 도로 확장공사"}),
    ],
)
def test_normalized_match(code, gold, normalized):
    assert compare_field(code, label(gold), pred("raw", normalized))[:2] == (True, None)


def test_failure_reasons():
    assert compare_field("contract_amount", label(100), pred(None, None))[1] == "missed"
    assert compare_field("contract_amount", label(100), pred("금 일백원", None))[1] == "normalize_failed"
    assert compare_field("contract_amount", label(100), pred("금 200원", {"amount": 200}))[1:] == ("value_mismatch", 100, 200)
    assert compare_field("guarantee_amount", None, pred("금 200원", {"amount": 200}))[1] == "unexpected_value"
    assert compare_field("guarantee_amount", None, pred(None, None))[:2] == (True, None)  # null label + null value is correct
    assert compare_field("guarantee_period", label({"start": "2026-01-01", "end": "2026-12-31"}), pred("x", {"start": "2026-01-01"}))[1] == "normalize_failed"


def test_score_doc_bbox_reasons_and_string_values():
    gold = {
        "doc_id": "d1",
        "source_type": "native",
        "labels": {"contract_amount": label(100), "contract_date": label("2026-01-02"), "creditor_name": label("(주)가"), "guarantee_amount": None},
    }
    fields = [
        {"field_code": "contract_amount", **pred("금 100원", {"amount": 100})},
        {"field_code": "contract_date", **pred("2026.1.2", {"date": "2026-01-02"}, method="none", hl=())},
        {"field_code": "creditor_name", **pred("(주)가", {"text": "(주)가"}, hl=((1, (0.5, 0.5, 0.9, 0.6)),))},
        {"field_code": "guarantee_amount", **pred("금 9원", {"amount": 9})},
    ]
    records, failures = score_doc(gold, fields)
    assert [r["correct"] for r in records] == [True, True, True, False]
    assert {f["field_code"]: f["reason"] for f in failures} == {
        "contract_date": "bbox_unmapped",
        "creditor_name": "bbox_iou_low",
        "guarantee_amount": "unexpected_value",
    }
    unexpected = next(f for f in failures if f["field_code"] == "guarantee_amount")
    assert unexpected["expected"] == "null" and unexpected["got"] == "9"  # backend EvalFailure: expected str, got str|None
    assert all(isinstance(f["expected"], str) for f in failures)


def test_validate_gold_rejects_bad_labels(tmp_path):
    ok = {"doc_id": "d", "source_type": "scan", "labels": {"contract_amount": label(1)}}
    validate_gold(ok, tmp_path)
    for bad in (
        {**ok, "source_type": "photo"},
        {**ok, "labels": {"amount": label(1)}},
        {**ok, "labels": {"contract_amount": label(1, bbox=(0.5, 0.1, 0.2, 0.2))}},
        {**ok, "labels": {"contract_amount": {"page": 1, "bbox": [0, 0, 1, 1]}}},
    ):
        with pytest.raises(ValueError):
            validate_gold(bad, tmp_path)


# ---------- synthetic gold ----------


def test_amount_formats_round_trip():
    import random

    rng = random.Random(1)
    assert synth.korean_amount(350_000_000) == "삼억오천만" and synth.korean_amount(110_000) == "십일만"
    for n in (350_000_000, 1_189_900_000, 10_000_000, 4_999_900_000, 110_000):
        for _ in range(20):
            assert normalize_amount(synth.amount_text(n, rng)) == {"amount": n}
    assert all(biz_no_checksum_ok(synth.biz_no(rng).replace("-", "")) for _ in range(20))


@pytest.fixture(scope="module")
def gold_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("gold")
    synth.main(["--out", str(out), "-n", "3", "--seed", "5"])
    return out


def test_synthetic_gold_is_valid_and_has_a_scan(gold_dir):
    docs = load_gold(gold_dir)
    assert [g["source_type"] for g, _ in docs] == ["native", "native", "scan"]
    for gold, _ in docs:
        assert set(gold["labels"]) == set(FIELD_CODES) and gold["synthetic"] is True
        assert all(0 <= c <= 1 for lb in gold["labels"].values() if lb for c in lb["bbox"])
        assert gold["text_lines"] and gold["text_lines"][0]["text"] == synth.NOTICE  # fabricated-data notice on every doc


def test_llm_path_with_fake_client_scores_perfectly_on_native(gold_dir):
    """Fake LLM answers with the gold raw_text: values and bboxes must come out exact through the real
    OCR -> extract_fields -> map_value -> normalize path, which also proves the gold boxes sit on the text."""
    gold, _ = load_gold(gold_dir)[0]
    llm = FakeLLM({code: lb["raw_text"] for code, lb in gold["labels"].items() if lb})
    metrics, failures = evaluate(gold_dir, llm_extractor(llm), limit=1)
    assert failures == []
    assert metrics["field_accuracy"]["overall"] == 1.0
    assert metrics["bbox_mapping_rate"] == 1.0 and metrics["bbox_iou_at_0_5"] == 1.0
    assert metrics["by_source_type"]["native"]["n_fields"] == len(FIELD_CODES)
    assert llm.calls >= 1 and metrics["seconds_per_doc"]["mean"] >= 0


def test_rule_path_writes_outputs(gold_dir, tmp_path):
    metrics, failures = evaluate(gold_dir, rule_extractor, limit=2)
    write_outputs(tmp_path, metrics, failures)
    saved = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert {"field_accuracy", "bbox_mapping_rate", "bbox_iou_at_0_5", "by_source_type", "seconds_per_doc"} <= set(saved)
    assert set(saved["field_accuracy"]) == {"overall", "by_field"} and saved["n_docs"] == 2
    with open(tmp_path / "failures.csv", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(failures) and (not rows or set(rows[0]) == {"doc_id", "doc_name", "field_code", "expected", "got", "reason"})
