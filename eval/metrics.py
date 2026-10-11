"""Geometry and text-distance metrics shared by eval/extraction.py and eval/ocr_benchmark.py.
Dependency-free (no rapidfuzz / ai.extract) so the OCR benchmark also runs in the separate PaddleOCR venv."""

from collections.abc import Sequence

IOU_THRESHOLD = 0.5


# ---------- geometry ----------


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def union_box(boxes: Sequence[Sequence[float]]) -> list[float]:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def best_iou(highlights: list[dict], page: int, gold: Sequence[float]) -> float:
    """Best of: each highlight alone (exact search may return 2 hits) and the union (value split over 2 lines)."""
    boxes = [h["bbox"] for h in highlights if h["page_no"] == page]
    if not boxes:
        return 0.0
    return max([iou(b, gold) for b in boxes] + [iou(union_box(boxes), gold)])


# ---------- text ----------


def edit_distance(a: Sequence, b: Sequence) -> int:
    """Levenshtein over chars (str) or tokens (list). Pure Python so it also runs in the PaddleOCR venv."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def char_errors(ref: str, hyp: str) -> tuple[int, int]:
    """(edit distance, reference length) with whitespace removed: Korean OCR spacing is scored by WER, not CER."""
    r, h = "".join(ref.split()), "".join(hyp.split())
    return edit_distance(r, h), len(r)


def word_errors(ref: str, hyp: str) -> tuple[int, int]:
    r, h = ref.split(), hyp.split()
    return edit_distance(r, h), len(r)
