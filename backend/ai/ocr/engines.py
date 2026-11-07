"""OCR engine abstraction: OcrEngine.run(image) -> list[OcrLine] (05_OCR_Pipeline §3-④).

| engine     | role                         | runs on                    |
| paddle_vl  | PaddleOCR-VL 0.9B (main)     | GPU, ocr container         |
| paddle     | PaddleOCR PP-OCRv5 korean    | CPU ok (no-GPU substitute) |
| tesseract  | Tesseract 5 kor+eng baseline | CPU, benchmark reference   |
| remote     | HTTP client of ai.ocr.server | worker -> ocr container    |

All boxes are pixel boxes in the image that was passed to run().
"""

import csv
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Protocol

import cv2
import numpy as np


logger = logging.getLogger(__name__)
WORD_GAP_RATIO = 0.45  # a gap wider than 0.45 x the median glyph width between two word boxes is a space


def spaced_text(words: list[str], boxes: list) -> str:
    """Rebuild a line from PP-OCR word boxes, putting a space where the glyphs are visibly apart.
    PP-OCRv5's korean recognizer drops most spaces ("새솔군정수장노후관교체공사"); the gold/printed value keeps
    them and contract names are compared space-sensitively, so the geometry decides instead of a dictionary
    (Kiwi spacing re-split compound words: 5/35 gold names right)."""
    pieces = [(w, b) for w, b in zip(words, boxes, strict=False) if w and w.strip()]
    if len(pieces) < 2:
        return "".join(w for w, _ in pieces)
    widths = sorted((float(b[2]) - float(b[0])) / max(len(w.strip()), 1) for w, b in pieces)
    glyph = widths[len(widths) // 2] or 1.0
    out = pieces[0][0].strip()
    for (_, prev), (word, box) in zip(pieces, pieces[1:], strict=False):
        gap = float(box[0]) - float(prev[2])
        out += (" " if gap > WORD_GAP_RATIO * glyph else "") + word.strip()
    return out


class OcrUnavailableError(RuntimeError):
    """No usable OCR engine / OCR server unreachable (API: 503 OCR_UNAVAILABLE)."""


@dataclass
class OcrLine:
    text: str
    bbox: tuple[float, float, float, float]  # px, top-left origin
    confidence: float
    block_no: int | None = None
    table_cell: str | None = None


class OcrEngine(Protocol):
    name: str
    source: str  # value stored in ocr_lines.source

    def run(self, image: np.ndarray) -> list[OcrLine]: ...


class TesseractEngine:
    name, source = "tesseract", "tesseract"

    def __init__(self, lang: str = "kor+eng", psm: int = 6, timeout: int = 60):
        if not shutil.which("tesseract"):
            raise OcrUnavailableError("tesseract binary not found")
        self.lang, self.psm, self.timeout = lang, psm, timeout

    def run(self, image: np.ndarray) -> list[OcrLine]:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "page.png")
            cv2.imwrite(path, image)
            cmd = ["tesseract", path, "stdout", "-l", self.lang, "--psm", str(self.psm), "tsv"]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, check=True).stdout
        # word-level output: finalize() re-joins words per visual line *and* per table cell
        return [
            OcrLine(
                w["text"],
                (int(w["left"]), int(w["top"]), int(w["left"]) + int(w["width"]), int(w["top"]) + int(w["height"])),
                max(float(w["conf"]), 0) / 100,
                int(w["block_num"]),
            )
            for w in csv.DictReader(io.StringIO(out), delimiter="\t", quoting=csv.QUOTE_NONE)
            if w["level"] == "5" and w["text"].strip()
        ]


class PaddleEngine:
    """PP-OCRv5 korean: line-level text boxes + recognition scores."""

    name, source = "paddle", "paddle"

    def __init__(self, lang: str = "korean"):
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OcrUnavailableError("paddleocr is not installed") from exc
        # mobile detector + capped input side: the default server detector on a 300dpi A4 page was SIGKILLed (OOM)
        # on a 16GB Mac with the LLM loaded; PADDLE_DET_MODEL=PP-OCRv5_server_det on a bigger box
        self._ocr = PaddleOCR(  # model names given explicitly -> paddleocr ignores `lang`, so pin the korean recognizer
            text_recognition_model_name=f"{lang}_PP-OCRv5_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_detection_model_name=os.getenv("PADDLE_DET_MODEL", "PP-OCRv5_mobile_det"),
            text_det_limit_side_len=int(os.getenv("PADDLE_DET_MAX_SIDE", "2000")),
            text_det_limit_type="max",
        )

    def run(self, image: np.ndarray) -> list[OcrLine]:
        res = None
        if os.getenv("PADDLE_WORD_SPACING", "1") == "1":
            try:  # word boxes -> spaces from glyph gaps (spaced_text); older paddleocr has no such option
                res = self._ocr.predict(image, return_word_box=True)[0]
            except TypeError:
                res = None
        res = res if res is not None else self._ocr.predict(image)[0]
        words = res.get("text_word") if hasattr(res, "get") else None
        word_boxes = (res.get("text_word_boxes") or res.get("text_word_region")) if hasattr(res, "get") else None
        out = []
        for i, (text, score, box) in enumerate(zip(res["rec_texts"], res["rec_scores"], res["rec_boxes"], strict=True)):
            if words and word_boxes and i < len(words) and i < len(word_boxes) and " " not in text.strip():
                try:
                    text = spaced_text(list(words[i]), [_xyxy(b) for b in word_boxes[i]]) or text
                except (TypeError, ValueError, IndexError):
                    pass
            if text.strip():
                out.append(OcrLine(text, (float(box[0]), float(box[1]), float(box[2]), float(box[3])), float(score)))
        return out


def _xyxy(box) -> tuple[float, float, float, float]:
    """[x0, y0, x1, y1] or a 4-point polygon -> axis-aligned box."""
    arr = np.asarray(box, dtype=float).reshape(-1)
    if arr.size == 4:
        return tuple(arr)  # type: ignore[return-value]
    xs, ys = arr[0::2], arr[1::2]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


class _TableHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self.rows:
            self.rows[-1].append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


class PaddleVLEngine:
    """PaddleOCR-VL: layout blocks with content. VL gives block boxes only, so line boxes inside a block are
    split evenly and table cells evenly over the table box.
    shortcut: even split is approximate; upgrade to PP-OCRv5 det boxes inside each block if IoU eval < 0.5."""

    name, source = "paddle_vl", "paddle"

    def __init__(self):
        try:
            from paddleocr import PaddleOCRVL
        except ImportError as exc:
            raise OcrUnavailableError("paddleocr (PaddleOCR-VL) is not installed") from exc
        server = os.getenv("PADDLE_VL_SERVER_URL")  # e.g. vLLM serving the VL recognizer
        self._vl = PaddleOCRVL(vl_rec_backend="vllm-server", vl_rec_server_url=server) if server else PaddleOCRVL()

    def run(self, image: np.ndarray) -> list[OcrLine]:
        res = self._vl.predict(image)[0]
        out: list[OcrLine] = []
        for no, block in enumerate(res["parsing_res_list"]):
            x0, y0, x1, y1 = block.bbox
            if block.label == "table":
                parser = _TableHTML()
                parser.feed(block.content or "")
                rows = [r for r in parser.rows if r]
                for r, cells in enumerate(rows):
                    rh, cw = (y1 - y0) / len(rows), (x1 - x0) / len(cells)
                    for c, text in enumerate(cells):
                        if text:
                            box = (x0 + c * cw, y0 + r * rh, x0 + (c + 1) * cw, y0 + (r + 1) * rh)
                            out.append(OcrLine(text, box, 1.0, no, f"r{r + 1},c{c + 1}"))  # VL has no score
                continue
            texts = [t for t in re.sub(r"<[^>]+>", "", block.content or "").splitlines() if t.strip()]
            for i, text in enumerate(texts):
                lh = (y1 - y0) / len(texts)
                out.append(OcrLine(text.strip(), (x0, y0 + i * lh, x1, y0 + (i + 1) * lh), 1.0, no))
        return out


class RemoteEngine:
    """Client of the OCR serving container (ai.ocr.server). 60s per page, 3 retries with backoff."""

    name = "remote"

    def __init__(self, base_url: str, timeout: float = 60.0, retries: int = 3):
        self.base_url, self.timeout, self.retries = base_url.rstrip("/"), timeout, retries
        self.source = "paddle"

    def run(self, image: np.ndarray) -> list[OcrLine]:
        ok, png = cv2.imencode(".png", image)
        if not ok:
            raise ValueError("failed to encode page image")
        req = urllib.request.Request(self.base_url + "/ocr", data=png.tobytes(), headers={"Content-Type": "image/png"})
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - OCR_BASE_URL config
                    body = json.loads(resp.read())
                self.source = body.get("source", self.source)
                return [OcrLine(ln["text"], tuple(ln["bbox"]), ln["confidence"], ln.get("block_no"), ln.get("table_cell")) for ln in body["lines"]]
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt + 1 == self.retries:
                    raise OcrUnavailableError(f"OCR server unreachable: {exc}") from exc
                time.sleep(2**attempt)
        raise AssertionError("unreachable")


class FallbackEngine:
    """OCR server first (GPU container, OCR_BASE_URL); when it is down, this page runs on the local CPU engine
    instead of failing the document. The server is tried again after RETRY_AFTER seconds."""

    name = "remote+fallback"
    RETRY_AFTER = 60.0

    def __init__(self, remote: "RemoteEngine"):
        self.remote, self._local, self._down_until = remote, None, 0.0
        self.source = remote.source

    def _local_engine(self) -> OcrEngine:
        if self._local is None:
            for candidate in ("paddle", "tesseract"):
                try:
                    self._local = _LOCAL[candidate]()
                    break
                except OcrUnavailableError:
                    continue
            else:
                raise OcrUnavailableError("OCR server unreachable and no local OCR engine installed")
        return self._local

    def run(self, image: np.ndarray) -> list[OcrLine]:
        if time.monotonic() >= self._down_until:
            try:
                lines = self.remote.run(image)
                self.source = self.remote.source
                return lines
            except OcrUnavailableError as exc:
                self._down_until = time.monotonic() + self.RETRY_AFTER
                logger.warning("OCR server down, using local CPU OCR for %.0fs: %s", self.RETRY_AFTER, exc)
        local = self._local_engine()
        self.source = local.source
        return local.run(image)


def line_to_json(line: OcrLine) -> dict:
    return {**asdict(line), "bbox": [float(v) for v in line.bbox]}


_LOCAL = {"paddle_vl": PaddleVLEngine, "paddle": PaddleEngine, "tesseract": TesseractEngine}
_cache: dict[str, OcrEngine] = {}


def get_engine(name: str | None = None, *, allow_remote: bool = True) -> OcrEngine:
    """name: auto | paddle_vl | paddle | tesseract (None -> OCR_ENGINE env, default auto).
    auto = OCR_BASE_URL (serving) -> paddle (PP-OCRv5) -> tesseract."""
    name = (name or os.getenv("OCR_ENGINE") or "auto").lower()
    if name in _cache:
        return _cache[name]
    if name == "auto":
        base_url = os.getenv("OCR_BASE_URL") if allow_remote else None
        if base_url:  # GPU OCR container; CPU fallback unless OCR_FALLBACK=0
            remote = RemoteEngine(base_url)
            engine: OcrEngine = FallbackEngine(remote) if os.getenv("OCR_FALLBACK", "1") == "1" else remote
        else:
            for candidate in ("paddle", "tesseract"):
                try:
                    engine = _LOCAL[candidate]()
                    break
                except OcrUnavailableError:
                    continue
            else:
                raise OcrUnavailableError("no OCR engine available (set OCR_BASE_URL, install paddleocr or tesseract)")
    elif name in _LOCAL:
        engine = _LOCAL[name]()
    else:
        raise OcrUnavailableError(f"unknown OCR engine '{name}'")
    _cache[name] = engine
    return engine
