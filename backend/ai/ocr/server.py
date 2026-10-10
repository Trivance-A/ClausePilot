"""OCR serving for the `ocr` container (PaddleOCR-VL on GPU, PP-OCRv5 / Tesseract otherwise).

    uvicorn ai.ocr.server:app --host 0.0.0.0 --port 8001

POST /ocr   body = PNG/JPEG bytes (already rendered + deskewed by the worker)
            -> {"engine", "source", "width", "height", "lines": [{text, bbox(px), confidence, block_no, table_cell}]}
GET /health -> {"status": "ok", "engine"}
The worker talks to it through RemoteEngine (OCR_BASE_URL); geometry/line IDs stay in the worker.
"""

import os
import threading

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from ai.ocr.engines import OcrUnavailableError, get_engine, line_to_json

MAX_IMAGE_BYTES = 50 * 1024 * 1024

app = FastAPI(title="contract-ai OCR")
_lock = threading.Lock()  # Paddle predictors are not thread-safe; one page at a time per process


def _engine():
    try:
        return get_engine(os.getenv("OCR_ENGINE", "auto"), allow_remote=False)
    except OcrUnavailableError as exc:
        raise HTTPException(503, {"code": "OCR_UNAVAILABLE", "message": str(exc)}) from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine": _engine().name}


@app.post("/ocr")
async def ocr(request: Request) -> dict:
    body = await request.body()
    if not body or len(body) > MAX_IMAGE_BYTES:
        raise HTTPException(413 if body else 400, {"code": "VALIDATION_ERROR", "message": "image body required (<= 50MB)"})
    image = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(415, {"code": "UNSUPPORTED_FORMAT", "message": "not a PNG/JPEG image"})
    engine = _engine()

    def run():
        with _lock:
            return engine.run(image)

    lines = await run_in_threadpool(run)  # engines are blocking (GPU/CPU bound)
    h, w = image.shape[:2]
    return {"engine": engine.name, "source": engine.source, "width": w, "height": h, "lines": [line_to_json(ln) for ln in lines]}
