"""Gold set loading (03_데이터정의 §3.2 schema, see data/gold/README.md). Imports only ai.types."""

import json
from pathlib import Path

from ai.types import FIELD_CODES

DOC_EXTENSIONS = ("pdf", "hwp", "hwpx", "docx", "xlsx", "png", "jpg", "jpeg")
SOURCE_TYPES = ("native", "scan")


def validate_gold(gold: dict, path: Path) -> None:
    """Fail loudly on malformed hand-made gold instead of scoring against it."""
    if not gold.get("doc_id") or gold.get("source_type") not in SOURCE_TYPES or not isinstance(gold.get("labels"), dict):
        raise ValueError(f"{path}: needs doc_id, source_type in {SOURCE_TYPES}, labels")
    for code, label in gold["labels"].items():
        if code not in FIELD_CODES:
            raise ValueError(f"{path}: unknown field {code}")
        if label is None:
            continue
        if label.get("value") is None:
            raise ValueError(f"{path}: {code} label without value (use null for an absent field)")
        bbox = label.get("bbox")
        if bbox is not None and not (len(bbox) == 4 and 0 <= bbox[0] < bbox[2] <= 1 and 0 <= bbox[1] < bbox[3] <= 1 and isinstance(label.get("page"), int)):
            raise ValueError(f"{path}: {code} bbox must be [x0,y0,x1,y1] in 0~1 with page")


def document_path(gold: dict, gold_dir: Path) -> Path:
    if gold.get("file"):
        return gold_dir / gold["file"]
    for ext in DOC_EXTENSIONS:
        if (path := gold_dir / f"{gold['doc_id']}.{ext}").exists():
            return path
    raise FileNotFoundError(f"no document for {gold['doc_id']} in {gold_dir} (set 'file' or name it <doc_id>.pdf)")


def load_gold(gold_dir: Path) -> list[tuple[dict, Path]]:
    """Every *.json with doc_id + labels, sorted by file name (other JSON files, e.g. manifests, are skipped)."""
    out = []
    for path in sorted(gold_dir.glob("*.json")):
        gold = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(gold, dict) or "labels" not in gold:
            continue
        validate_gold(gold, path)
        doc = document_path(gold, gold_dir)
        if not doc.exists():
            raise FileNotFoundError(f"{doc} missing (synthetic set: run `python -m eval.make_synthetic_gold` first)")
        out.append((gold, doc))
    return out
