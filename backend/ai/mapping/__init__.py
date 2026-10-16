"""⑥ Value <-> bbox reverse mapping, 4-stage fallback (05_OCR_Pipeline §3-⑦, FR-05):

  1. llm_ref  - the value is found inside the LLM's evidence lines
  2. exact    - normalized substring of one line (or two adjacent lines) anywhere in the document
  3. fuzzy    - rapidfuzz partial_ratio >= 85 against lines / adjacent line pairs
  4. re-query - ask the LLM only for this field's evidence line IDs, verified again (stored as llm_ref)
  else none   - no highlight, failure reason logged (value error / OCR misread / multi line / table cell)

A value inside a longer line gets a partial bbox: x0 + (start/len) * width (no char boxes from the engines).
"""

import logging
import re
import unicodedata
from collections.abc import Callable

from rapidfuzz import fuzz

from ai.types import HighlightDict, OcrLineDict

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 85
REQUERY_THRESHOLD = 70  # a re-queried line must still resemble the value; anything weaker is a guess
_DROP = set(" \t\r\n,원₩\\()[]{}<>\"'“”‘’「」『』·:：;")
_DATE_SEP = set("-/.년월")
LINE_ID_RE = re.compile(r"L\d+-\d+")


def norm_map(text: str) -> tuple[str, list[int]]:
    """normalize() that also returns, for every kept char, its index in the original text.
    Drops spaces, commas, 원, ₩, brackets, quotes; NFKC (full-width -> half-width); date separators -> '.'."""
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKC", ch).lower():
            if c in _DATE_SEP:
                c = "."
            if c == "일" and out and out[-1].isdigit():  # "5일" -> "5"
                continue
            if c in _DROP or (c == "." and out and out[-1] == "."):
                continue
            out.append(c)
            idx.append(i)
    return "".join(out), idx


def normalize(text: str) -> str:
    return norm_map(text)[0].strip(".")


def _span_highlights(lines: list[OcrLineDict], start: int, end: int) -> list[HighlightDict]:
    """Highlights for normalized span [start, end) of the concatenation of `lines`, partial where possible."""
    out: list[HighlightDict] = []
    offset = 0
    for line in lines:
        n, idx = norm_map(line["text"])
        lo, hi = max(start, offset), min(end, offset + len(n))
        if lo < hi:
            text_len = len(line["text"]) or 1
            a, b = idx[lo - offset], idx[hi - offset - 1] + 1
            x0, y0, x1, y1 = line["bbox"]
            w = x1 - x0
            bbox = [round(x0 + w * a / text_len, 5), y0, round(x0 + w * b / text_len, 5), y1]
            out.append({"page_no": line["page_no"], "bbox": bbox, "ocr_line_id": line["line_id"]})
        offset += len(n)
    return out


def locate(value: str, lines: list[OcrLineDict]) -> list[HighlightDict] | None:
    """Exact (normalized) substring search over the concatenated `lines`."""
    target = normalize(value)
    if not target:
        return None
    joined = "".join(norm_map(ln["text"])[0] for ln in lines)
    pos = joined.find(target)
    return _span_highlights(lines, pos, pos + len(target)) if pos >= 0 else None


def _windows(lines: list[OcrLineDict]) -> list[list[OcrLineDict]]:
    """Single lines, then adjacent pairs on one page (values broken across a line wrap)."""
    singles = [[ln] for ln in lines]
    pairs = [[a, b] for a, b in zip(lines, lines[1:], strict=False) if a["page_no"] == b["page_no"]]
    return singles + pairs


def line_highlights(line_ids: list[str], by_id: dict[str, OcrLineDict]) -> list[HighlightDict]:
    return [{"page_no": by_id[i]["page_no"], "bbox": by_id[i]["bbox"], "ocr_line_id": i} for i in line_ids if i in by_id]


def clean_line_ids(ids: list[str] | None, by_id: dict[str, OcrLineDict]) -> list[str]:
    """LLMs return '[L1-2]' or 'L1-2: text'; keep real IDs only, document order, no duplicates."""
    found = {m for raw in ids or [] for m in LINE_ID_RE.findall(str(raw)) if m in by_id}
    order = {lid: n for n, lid in enumerate(by_id)}
    return sorted(found, key=order.__getitem__)


def _fuzzy(target: str, lines: list[OcrLineDict]) -> tuple[float, list[HighlightDict]]:
    best_score, best = 0.0, []
    for window in _windows(lines):
        joined = "".join(norm_map(ln["text"])[0] for ln in window)
        if not joined:
            continue
        al = fuzz.partial_ratio_alignment(target, joined)
        if al and al.score > best_score:
            best_score, best = al.score, _span_highlights(window, al.dest_start, al.dest_end)
    return best_score, best


def map_value(
    value: str | None,
    lines: list[OcrLineDict],
    evidence_ids: list[str] | None = None,
    requery: Callable[[], list[str]] | None = None,
    field_code: str = "",
) -> tuple[str, list[HighlightDict], float]:
    """Returns (mapping_method, highlights, match score 0~100)."""
    if not value or not normalize(value):
        return "none", [], 0.0
    by_id = {ln["line_id"]: ln for ln in lines}

    evidence = [by_id[i] for i in clean_line_ids(evidence_ids, by_id)]
    if evidence and (hl := locate(value, evidence)):
        return "llm_ref", hl, 100.0

    hits = [hl for window in _windows(lines) if (hl := locate(value, window))]
    if hits:
        return "exact", [h for hl in hits[:2] for h in hl], 100.0

    target = normalize(value)
    score, hl = _fuzzy(target, lines) if len(target) >= 2 else (0.0, [])
    if score >= FUZZY_THRESHOLD:
        return "fuzzy", hl, score

    if requery is not None:
        ids = clean_line_ids(requery(), by_id)
        if ids:
            cand = [by_id[i] for i in ids]
            again, _ = _fuzzy(target, cand)
            if again >= REQUERY_THRESHOLD:
                return "llm_ref", locate(value, cand) or line_highlights(ids, by_id), again

    reason = "value_error" if score < 50 else "ocr_misread"
    near = [by_id[i] for h in hl if (i := h["ocr_line_id"])]
    if any(ln["table_cell"] for ln in near):
        reason = "table_cell"
    elif near and len(target) > max(len(normalize(ln["text"])) for ln in near):
        reason = "multi_line"
    logger.info("bbox mapping failed field=%s reason=%s best_fuzzy=%.1f value=%r", field_code, reason, score, value)
    return "none", [], score
