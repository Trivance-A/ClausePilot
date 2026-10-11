"""FR-18 extraction evaluation (05_OCR_Pipeline §5): gold/*.json + pipeline output -> metrics.json, failures.json/.csv.

    PYTHONPATH=backend python -m eval.extraction --gold data/gold/synthetic --extractor rule
    PYTHONPATH=backend python -m eval.extraction --gold data/gold/synthetic --extractor llm --limit 10

Per doc: normalize_to_pdf (non-PDF only) -> run_ocr -> extractor -> compare each labeled field.
- field_accuracy (NFR-01): exact match after normalization with the pipeline's own functions
  (backend/ai/extract/normalize.py): amounts int, dates YYYY-MM-DD, guarantee_period (start, end),
  names via normalize_company / normalize_text, biz no ###-##-#####.
  A null label is correct only if raw_value is null; a field key absent from `labels` is not evaluated.
- bbox_mapping_rate / bbox_iou_at_0_5 (NFR-02): mapping_method != 'none' (and IoU >= 0.5 vs the gold bbox on the
  gold page) over non-null labels that have a bbox.
- seconds_per_doc (NFR-06): OCR + extraction wall time.
failures: one row per wrong field; the value reason wins, otherwise bbox_unmapped / bbox_iou_low.
"""

import argparse
import csv
import json
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ai.extract import extract_fields
from ai.extract.normalize import normalize_amount, normalize_biz_no, normalize_company, normalize_date, normalize_text
from ai.llm import LLMClient
from ai.ocr import run_ocr
from ai.parser import normalize_to_pdf
from ai.types import FIELD_CODES

from eval.gold import SOURCE_TYPES, load_gold
from eval.metrics import IOU_THRESHOLD, best_iou

Extractor = Callable[[list], list[dict]]
AMOUNT_FIELDS = {"contract_amount", "guarantee_amount"}
DATE_FIELDS = {"contract_date", "performance_due_date"}
FAILURE_COLUMNS = ["doc_id", "doc_name", "field_code", "expected", "got", "reason"]


# ---------- field comparison ----------


def _text(fn, value) -> str | None:
    return (fn(str(value)) or {}).get("text") if value not in (None, "") else None


def canon_gold(code: str, value):
    """Gold label value -> comparable form. Accepts the canonical JSON types or a written form."""
    if value is None:
        return None
    if code in AMOUNT_FIELDS:
        return int(value) if isinstance(value, int) else (normalize_amount(str(value)) or {}).get("amount")
    if code in DATE_FIELDS:
        return (normalize_date(str(value)) or {}).get("date")
    if code == "guarantee_period":
        start, end = canon_gold("contract_date", value.get("start")), canon_gold("contract_date", value.get("end"))
        return (start, end) if start and end else None
    if code == "creditor_biz_no":
        return _text(normalize_biz_no, value)
    if code == "creditor_name":
        return _text(normalize_company, value)
    return _text(normalize_text, value)


def canon_pred(code: str, normalized: dict | None):
    """Pipeline normalized_value -> comparable form (names re-normalized so both sides use one rule)."""
    nv = normalized or {}
    if code in AMOUNT_FIELDS:
        return nv.get("amount")
    if code in DATE_FIELDS:
        return nv.get("date")
    if code == "guarantee_period":
        return (nv["start"], nv["end"]) if nv.get("start") and nv.get("end") else None
    return canon_gold(code, nv.get("text"))


def compare_field(code: str, label: dict | None, pred: dict | None) -> tuple[bool, str | None, object, object]:
    """Returns (correct, failure reason, expected, got). A null label means the right answer is raw_value null.
    reasons: missed | unexpected_value | normalize_failed | value_mismatch"""
    expected = canon_gold(code, label["value"]) if label else None
    raw = (pred or {}).get("raw_value")
    got = canon_pred(code, (pred or {}).get("normalized_value")) if raw is not None else None
    if expected is None:
        return raw is None, None if raw is None else "unexpected_value", None, got if got is not None else raw
    if raw is None:
        return False, "missed", expected, None
    if got is None:
        return False, "normalize_failed", expected, raw
    return got == expected, None if got == expected else "value_mismatch", expected, got


def check_bbox(label: dict, pred: dict | None) -> tuple[bool, float]:
    """(mapped, best IoU). mapped = mapping_method != 'none' with at least one highlight."""
    pred = pred or {}
    mapped = pred.get("mapping_method", "none") != "none" and bool(pred.get("highlights"))
    return mapped, best_iou(pred.get("highlights") or [], label["page"], label["bbox"]) if mapped else 0.0


# ---------- extractors ----------


def rule_extractor(lines: list) -> list[dict]:
    from app.services.ai_client import _extract_rule_based  # backend app module: imported only when used

    return _extract_rule_based(lines)


def llm_extractor(llm) -> Extractor:
    return lambda lines: extract_fields(lines, llm)[0]


def document_lines(doc: Path, ocr_engine: str | None) -> list:
    ext = doc.suffix.lower().lstrip(".")
    if ext == "pdf":
        return run_ocr(str(doc), ocr_engine)
    with tempfile.TemporaryDirectory() as tmp:
        normalized = normalize_to_pdf(str(doc), ext, str(Path(tmp) / "normalized.pdf"))
        return run_ocr(normalized["normalized_pdf_path"], ocr_engine)


# ---------- scoring ----------


def _show(value) -> str | None:
    """Failure values as strings (backend EvalFailure: expected str, got str | None)."""
    return value if value is None or isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def score_doc(gold: dict, fields: list[dict]) -> tuple[list[dict], list[dict]]:
    """(per-field records, failures) for one document."""
    by_code = {f["field_code"]: f for f in fields}
    name = gold.get("doc_name") or gold["doc_id"]
    records, failures = [], []
    for code, label in gold["labels"].items():
        pred = by_code.get(code)
        ok, reason, expected, got = compare_field(code, label, pred)
        rec = {"field_code": code, "correct": ok, "has_bbox": bool(label and label.get("bbox")), "mapped": False, "iou": 0.0}
        if rec["has_bbox"]:
            rec["mapped"], rec["iou"] = check_bbox(label, pred)
            if ok and not rec["mapped"]:
                reason = "bbox_unmapped"
            elif ok and rec["iou"] < IOU_THRESHOLD:
                reason, expected, got = "bbox_iou_low", label["bbox"], f"iou={rec['iou']:.2f}"
        records.append(rec)
        if reason:
            failures.append(
                {"doc_id": gold["doc_id"], "doc_name": name, "field_code": code, "expected": _show(expected) or "null", "got": _show(got), "reason": reason}
            )
    return records, failures


def _rate(hits: int, total: int) -> float | None:
    return round(hits / total, 4) if total else None


def summarize(records: list[dict]) -> dict:
    boxed = [r for r in records if r["has_bbox"]]
    by_field = {code: _rate(sum(r["correct"] for r in rs), len(rs)) for code in FIELD_CODES if (rs := [r for r in records if r["field_code"] == code])}
    return {
        "field_accuracy": {"overall": _rate(sum(r["correct"] for r in records), len(records)), "by_field": by_field},
        "bbox_mapping_rate": _rate(sum(r["mapped"] for r in boxed), len(boxed)),
        "bbox_iou_at_0_5": _rate(sum(r["mapped"] and r["iou"] >= IOU_THRESHOLD for r in boxed), len(boxed)),
        "n_fields": len(records),
        "n_bbox_labels": len(boxed),
    }


def _seconds(values: list[float]) -> dict:
    return {"mean": round(statistics.mean(values), 2), "median": round(statistics.median(values), 2), "max": round(max(values), 2)} if values else {}


def evaluate(gold_dir: Path, extractor: Extractor, ocr_engine: str | None = None, limit: int | None = None) -> tuple[dict, list[dict]]:
    docs = load_gold(gold_dir)[:limit]
    records, failures, per_doc = [], [], []
    for gold, path in docs:
        t0 = time.perf_counter()
        lines = document_lines(path, ocr_engine)
        t1 = time.perf_counter()
        fields = extractor(lines)
        t2 = time.perf_counter()
        recs, fails = score_doc(gold, fields)
        for r in recs:
            r["source_type"] = gold["source_type"]
        records += recs
        failures += fails
        per_doc.append(
            {
                "doc_id": gold["doc_id"],
                "doc_name": gold.get("doc_name") or gold["doc_id"],
                "source_type": gold["source_type"],
                "correct": sum(r["correct"] for r in recs),
                "n_fields": len(recs),
                "ocr_seconds": round(t1 - t0, 2),
                "extract_seconds": round(t2 - t1, 2),
                "seconds": round(t2 - t0, 2),
            }
        )
        print(f"{gold['doc_id']}: {per_doc[-1]['correct']}/{len(recs)} fields, {per_doc[-1]['seconds']}s", file=sys.stderr)
    metrics = summarize(records)
    metrics["by_source_type"] = {
        st: {
            **summarize([r for r in records if r["source_type"] == st]),
            "seconds_per_doc": _seconds([d["seconds"] for d in per_doc if d["source_type"] == st]),
        }
        for st in SOURCE_TYPES
        if any(d["source_type"] == st for d in per_doc)
    }
    metrics["seconds_per_doc"] = _seconds([d["seconds"] for d in per_doc])
    metrics["n_docs"] = len(per_doc)
    metrics["docs"] = per_doc
    return metrics, failures


def write_outputs(out_dir: Path, metrics: dict, failures: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out_dir / "failures.csv", "w", encoding="utf-8-sig", newline="") as fh:  # BOM: opens in Excel
        writer = csv.DictWriter(fh, FAILURE_COLUMNS)
        writer.writeheader()
        writer.writerows(failures)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", required=True, type=Path, help="directory of gold *.json (+ documents)")
    ap.add_argument("--extractor", choices=["rule", "llm"], default="rule")
    ap.add_argument("--llm-url", default="http://localhost:11434/v1")
    ap.add_argument("--llm-model", default="qwen2.5:7b")
    ap.add_argument("--ocr-engine", default=None, help="auto | paddle | tesseract | paddle_vl (default: OCR_ENGINE env / auto)")
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N docs (sorted by file name)")
    ap.add_argument("--out", type=Path, default=None, help="default: eval/out/<gold dir name>-<extractor>")
    args = ap.parse_args(argv)

    if args.extractor == "llm":
        llm = LLMClient(args.llm_url, args.llm_model)
        extractor, model = llm_extractor(llm), args.llm_model
    else:
        extractor, model = rule_extractor, "rule-based-v1"
    metrics, failures = evaluate(args.gold, extractor, args.ocr_engine, args.limit)
    metrics["meta"] = {
        "gold": str(args.gold),
        "extractor": args.extractor,
        "model": model,
        "ocr_engine": args.ocr_engine or "auto",
        "run_at": datetime.now().isoformat(timespec="seconds"),
    }
    out = args.out or Path("eval/out") / f"{args.gold.name}-{args.extractor}"
    write_outputs(out, metrics, failures)
    summary = {k: metrics[k] for k in ("field_accuracy", "bbox_mapping_rate", "bbox_iou_at_0_5", "seconds_per_doc", "n_docs")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"wrote {out}/metrics.json, failures.json, failures.csv ({len(failures)} failures)")


if __name__ == "__main__":
    main()
