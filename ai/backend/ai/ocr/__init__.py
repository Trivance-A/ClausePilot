"""②~⑤ Page router, native text / OCR line extraction, line normalization and line IDs (05_OCR_Pipeline §3).

Output lines are in reading order with IDs L{page}-{line}; bbox [x0,y0,x1,y1] normalized 0~1,
top-left origin, rotation applied (same frame as the rendered page / pdf.js viewport).
"""

import os

import cv2
import numpy as np
import pymupdf as fitz

from ai.ocr.engines import OcrEngine, OcrUnavailableError, get_engine
from ai.ocr.preprocess import cell_of, deskew, detect_table_cells, map_box
from ai.types import OcrLineDict

__all__ = ["OcrUnavailableError", "classify_page", "looks_garbled", "run_ocr", "source_type_of"]

MIN_NATIVE_CHARS = 50
MAX_RENDER_PX = 3508  # long side of A4 at 300dpi; image-only PDFs often carry oversized page boxes
MERGE_GAP_RATIO = 3.0  # fragments on one row closer than 3x line height are one line
CELL_MERGE_MAX_CHARS = 40  # "계약" / "금액" split inside one cell -> merged


def pdf_to_norm(rect: fitz.Rect, page: fitz.Page) -> list[float]:
    """PyMuPDF rect (unrotated page space) -> 0~1 in the rotated (displayed) page frame."""
    r = rect * page.rotation_matrix
    w, h = page.rect.width, page.rect.height
    return [_clip(r.x0 / w), _clip(r.y0 / h), _clip(r.x1 / w), _clip(r.y1 / h)]


def px_to_norm(box, img_w: int, img_h: int) -> list[float]:
    x0, y0, x1, y1 = box
    return [_clip(x0 / img_w), _clip(y0 / img_h), _clip(x1 / img_w), _clip(y1 / img_h)]


def _clip(v: float) -> float:
    return min(1.0, max(0.0, float(v)))


# ---------- ③ router ----------


def looks_garbled(text: str) -> bool:
    """Broken-font PDF: many U+FFFD or Hangul ratio < 30%. Pages that are mostly ASCII (English) are not garbled."""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return True
    if chars.count("�") / len(chars) > 0.05:
        return True
    letters = sum(c.isalpha() for c in chars) or 1
    hangul = sum("가" <= c <= "힣" for c in chars)
    ascii_alnum = sum(c.isascii() and c.isalnum() for c in chars)
    return hangul / letters < 0.3 and ascii_alnum / len(chars) < 0.6


def classify_page(page: fitz.Page) -> str:
    text = page.get_text("text")
    if len(text.strip()) >= MIN_NATIVE_CHARS and page.get_fonts() and not looks_garbled(text):
        return "native"
    return "scan"


def source_type_of(kinds: list[str]) -> str:
    return kinds[0] if kinds and len(set(kinds)) == 1 else "mixed"


# ---------- native pages ----------


def _native_cells(page: fitz.Page) -> list[tuple[str, list[float]]]:
    try:
        tables = page.find_tables().tables
    except Exception:  # noqa: BLE001 - table finder failing must not lose the text itself
        return []
    return [
        (f"{t}/r{r},c{c}", pdf_to_norm(fitz.Rect(cell), page))
        for t, table in enumerate(tables)
        for r, row in enumerate(table.rows, start=1)
        for c, cell in enumerate(row.cells, start=1)
        if cell
    ]


def native_lines(page: fitz.Page) -> list[dict]:
    cells = _native_cells(page)
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"]).strip()
            if not text:
                continue
            bbox = pdf_to_norm(fitz.Rect(line["bbox"]), page)
            lines.append({"text": text, "bbox": bbox, "confidence": 1.0, "source": "pdf_text", "table_cell": cell_of(bbox, cells), "block": block["number"]})
    return lines


# ---------- scan pages ----------


def ocr_page(page: fitz.Page, engine: OcrEngine, dpi: int | None = None) -> list[dict]:
    dpi = dpi or int(os.getenv("OCR_DPI", "300"))
    dpi = min(dpi, int(MAX_RENDER_PX * 72 / max(page.rect.width, page.rect.height)))
    pix = page.get_pixmap(dpi=dpi, alpha=False)  # rotation applied
    rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)
    image, inv = deskew(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    ruling, cells = detect_table_cells(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    image = image.copy()
    image[ruling > 0] = 255
    out = []
    for line in engine.run(image):
        cell = f"{line.block_no}/{line.table_cell}" if line.table_cell else cell_of(line.bbox, cells)
        bbox = px_to_norm(map_box(line.bbox, inv, pix.w, pix.h), pix.w, pix.h)
        out.append(
            {"text": line.text.strip(), "bbox": bbox, "confidence": line.confidence, "source": engine.source, "table_cell": cell, "block": line.block_no}
        )
    return out


# ---------- ⑤ line normalization ----------


def _same_row(a: list[float], b: list[float]) -> bool:
    overlap = min(a[3], b[3]) - max(a[1], b[1])
    return overlap >= 0.5 * min(a[3] - a[1], b[3] - b[1])


def _rows(lines: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for line in sorted(lines, key=lambda ln: ln["bbox"][1]):
        if rows and any(_same_row(m["bbox"], line["bbox"]) for m in rows[-1]):  # chains along slightly skewed rows
            rows[-1].append(line)
        else:
            rows.append([line])
    return [sorted(r, key=lambda ln: ln["bbox"][0]) for r in rows]


def _merge(a: dict, b: dict, sep: str = " ") -> dict:
    la, lb = len(a["text"]), len(b["text"])
    return {
        **a,
        "text": f"{a['text']}{sep}{b['text']}",
        "bbox": [min(a["bbox"][0], b["bbox"][0]), min(a["bbox"][1], b["bbox"][1]), max(a["bbox"][2], b["bbox"][2]), max(a["bbox"][3], b["bbox"][3])],
        "confidence": (a["confidence"] * la + b["confidence"] * lb) / ((la + lb) or 1),
    }


def merge_fragments(lines: list[dict], aspect: float = 842 / 595) -> list[dict]:
    """Join engine fragments of one visual line (same row, same cell, small gap), then short pieces of one cell.
    aspect = page height / width, so a normalized x-gap and a normalized line height compare in the same units."""
    merged: list[dict] = []
    for row in _rows(lines):
        cur = row[0]
        for nxt in row[1:]:
            height = min(cur["bbox"][3] - cur["bbox"][1], nxt["bbox"][3] - nxt["bbox"][1]) * aspect
            gap = nxt["bbox"][0] - cur["bbox"][2]
            if nxt["table_cell"] == cur["table_cell"] and gap < MERGE_GAP_RATIO * height:
                cur = _merge(cur, nxt, "" if gap < 0.15 * height else " ")  # touching glyph runs are one word
            else:
                merged.append(cur)
                cur = nxt
        merged.append(cur)

    out: list[dict] = []
    for line in merged:  # merged is row-major, so pieces of one cell appear in top-down order
        prev = next((o for o in reversed(out) if line["table_cell"] and o["table_cell"] == line["table_cell"]), None)
        if prev is not None and len(prev["text"]) + len(line["text"]) <= CELL_MERGE_MAX_CHARS:
            out[out.index(prev)] = _merge(prev, line)
        else:
            out.append(line)
    return out


def reading_order(lines: list[dict]) -> list[dict]:
    """Rows top->bottom, left->right. Two-column layout (wide non-table lines on both halves, none crossing the
    centre) is read left column first."""
    free = [ln for ln in lines if not ln["table_cell"]]
    left = [ln for ln in free if ln["bbox"][2] <= 0.5]
    right = [ln for ln in free if ln["bbox"][0] >= 0.5]
    crossing = len(free) - len(left) - len(right)
    if crossing == 0 and len(left) >= 5 and len(right) >= 5 and _median_width(left) > 0.3 and _median_width(right) > 0.3:
        return [ln for r in _rows([ln for ln in lines if ln["bbox"][0] < 0.5]) for ln in r] + [
            ln for r in _rows([ln for ln in lines if ln["bbox"][0] >= 0.5]) for ln in r
        ]
    return [ln for r in _rows(lines) for ln in r]


def _median_width(lines: list[dict]) -> float:
    widths = sorted(ln["bbox"][2] - ln["bbox"][0] for ln in lines)
    return widths[len(widths) // 2]


def finalize(lines: list[dict], page_no: int, aspect: float = 842 / 595) -> list[OcrLineDict]:
    ordered = reading_order(merge_fragments([ln for ln in lines if ln["text"]], aspect))
    return [
        {
            "page_no": page_no,
            "line_id": f"L{page_no}-{i}",
            "text": ln["text"],
            "bbox": [round(v, 5) for v in ln["bbox"]],
            "confidence": round(float(ln["confidence"]), 4),
            "source": ln["source"],
            "table_cell": ln["table_cell"].split("/")[-1] if ln["table_cell"] else None,  # drop internal table key
        }
        for i, ln in enumerate(ordered, start=1)
    ]


def run_ocr(pdf_path: str, engine: str | None = None) -> list[OcrLineDict]:
    """Native pages: PyMuPDF text layer (no OCR errors, <1s). Scan pages: render -> deskew -> OCR engine."""
    result: list[OcrLineDict] = []
    ocr_engine: OcrEngine | None = None
    with fitz.open(pdf_path) as doc:
        for page in doc:
            if page.rect.width <= 0 or page.rect.height <= 0:
                continue
            if classify_page(page) == "native":
                lines = native_lines(page)
            else:
                ocr_engine = ocr_engine or get_engine(engine)
                lines = ocr_page(page, ocr_engine)
            result.extend(finalize(lines, page.number + 1, page.rect.height / page.rect.width))
    return result
