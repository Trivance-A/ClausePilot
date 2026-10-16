import shutil

import cv2
import numpy as np
import pymupdf as fitz
import pytest

from ai.ocr import (
    classify_page,
    finalize,
    looks_garbled,
    merge_fragments,
    reading_order,
    run_ocr,
    source_type_of,
)
from ai.ocr.engines import OcrLine
from ai.ocr.preprocess import deskew, detect_table_cells, estimate_skew, map_box
from ai.tests.fixtures import contract_pdf


def frag(text, bbox, cell=None):
    return {"text": text, "bbox": list(bbox), "confidence": 0.9, "source": "paddle", "table_cell": cell}


def test_garbled_detection():
    assert looks_garbled("ÇÑ±ÛÆÄÀÏ ¹®¼­ º¯È¯ " * 5)
    assert looks_garbled("�� 계약 ��")
    assert not looks_garbled("공사도급계약서 계약금액 금 삼억원정")
    assert not looks_garbled("CONSTRUCTION CONTRACT AGREEMENT Contract Amount KRW 350,000,000")


def test_source_type():
    assert source_type_of(["native", "native"]) == "native"
    assert source_type_of(["scan"]) == "scan"
    assert source_type_of(["native", "scan"]) == "mixed"


def test_native_lines_ids_and_bbox(tmp_path):
    lines = run_ocr(contract_pdf(str(tmp_path / "c.pdf")))
    assert [ln["line_id"] for ln in lines[:3]] == ["L1-1", "L1-2", "L1-3"]
    assert lines[1]["text"] == "1. 공사명 : 한빛시 도로 확장공사"
    assert all(ln["source"] == "pdf_text" for ln in lines)
    x0, y0, x1, y1 = lines[1]["bbox"]
    assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
    assert abs(x0 - 40 / 595) < 0.01  # text starts at x=40pt


@pytest.mark.parametrize("rotate", [90, 180, 270])
def test_rotated_page_bbox_is_in_display_frame(tmp_path, rotate):
    lines = run_ocr(contract_pdf(str(tmp_path / "r.pdf"), rotate=rotate))
    width = 842 if rotate in (90, 270) else 595  # page.rect after rotation
    x0, y0, x1, y1 = lines[0]["bbox"]
    assert lines[0]["text"].replace(" ", "") == "공사도급계약서"
    assert abs(x0 - 40 / width) < 0.01 and x1 - x0 > y1 - y0  # upright, top-left, horizontal


def test_native_table_cells(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((40, 60), "계 약 보 증 금 지 급 각 서 — 표 아래 항목 확인용 본문 텍스트입니다 충분히 길게", fontsize=10, fontname="korea-s")
    for r, (k, v) in enumerate([("계약보증금", "금 삼천오백만원정"), ("보증기간", "2026.3.5 ~ 2027.3.4")]):
        for c, text in enumerate((k, v)):
            rect = fitz.Rect(40 + c * 200, 100 + r * 30, 240 + c * 200, 130 + r * 30)
            page.draw_rect(rect, color=(0, 0, 0), width=1)
            page.insert_text((rect.x0 + 5, rect.y0 + 20), text, fontsize=10, fontname="korea-s")
    path = str(tmp_path / "t.pdf")
    doc.save(path)
    cells = {ln["text"]: ln["table_cell"] for ln in run_ocr(path)}
    assert cells["계약보증금"] == "r1,c1" and cells["금 삼천오백만원정"] == "r1,c2" and cells["2026.3.5 ~ 2027.3.4"] == "r2,c2"


def test_fragments_of_a_row_are_merged_but_cells_kept_apart():
    lines = [
        frag("1.", (0.10, 0.10, 0.12, 0.12)),
        frag("공사명 :", (0.14, 0.10, 0.25, 0.12)),
        frag("도로 확장공사", (0.27, 0.10, 0.45, 0.12)),
        frag("계약", (0.10, 0.20, 0.15, 0.21), "0/r1,c1"),
        frag("금액", (0.10, 0.215, 0.15, 0.225), "0/r1,c1"),
        frag("금 삼억원", (0.30, 0.20, 0.45, 0.21), "0/r1,c2"),
    ]
    out = finalize(lines, 1)
    assert [ln["text"] for ln in out] == ["1. 공사명 : 도로 확장공사", "계약 금액", "금 삼억원"]
    assert [ln["table_cell"] for ln in out] == [None, "r1,c1", "r1,c2"]


def test_far_fragments_stay_separate():
    out = merge_fragments([frag("계약번호 제2026-01호", (0.05, 0.1, 0.3, 0.12)), frag("2026. 3. 5.", (0.8, 0.1, 0.95, 0.12))])
    assert len(out) == 2


def test_two_column_reading_order():
    left = [frag(f"왼쪽 단 문장 {i}", (0.05, 0.1 + i * 0.03, 0.45, 0.12 + i * 0.03)) for i in range(6)]
    right = [frag(f"오른쪽 단 문장 {i}", (0.55, 0.1 + i * 0.03, 0.95, 0.12 + i * 0.03)) for i in range(6)]
    ordered = [ln["text"] for ln in reading_order(right + left)]
    assert ordered[:6] == [f"왼쪽 단 문장 {i}" for i in range(6)]


def _text_image(angle: float) -> np.ndarray:
    img = np.full((1400, 1000, 3), 255, np.uint8)
    for i in range(12):
        cv2.putText(img, "CONTRACT AMOUNT 350,000,000 KRW", (60, 120 + i * 90), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
    m = cv2.getRotationMatrix2D((500, 700), angle, 1.0)
    return cv2.warpAffine(img, m, (1000, 1400), borderValue=(255, 255, 255))


def test_deskew_estimates_and_inverts():
    skewed = _text_image(-2.0)  # cv2: negative = clockwise -> text slopes down to the right
    assert estimate_skew(cv2.cvtColor(skewed, cv2.COLOR_BGR2GRAY)) == pytest.approx(2.0, abs=0.4)
    fixed, inv = deskew(skewed)
    assert inv is not None
    assert abs(estimate_skew(cv2.cvtColor(fixed, cv2.COLOR_BGR2GRAY))) < 0.4
    assert map_box((100, 100, 200, 120), None, 1000, 1400) == (100, 100, 200, 120)
    x0, y0, x1, y1 = map_box((100, 100, 200, 120), inv, 1000, 1400)
    assert x0 < x1 and y0 < y1


def test_ruled_table_cells():
    img = np.full((800, 1000), 255, np.uint8)
    for r in range(4):
        cv2.line(img, (100, 100 + r * 60), (900, 100 + r * 60), 0, 2)
    for x in (100, 400, 900):
        cv2.line(img, (x, 100), (x, 280), 0, 2)
    ruling, cells = detect_table_cells(img)
    keys = sorted(k.split("/")[1] for k, _ in cells)
    assert keys == ["r1,c1", "r1,c2", "r2,c1", "r2,c2", "r3,c1", "r3,c2"]
    assert ruling.any()


class FakeEngine:
    name, source = "fake", "paddle"

    def run(self, image):
        h, w = image.shape[:2]
        return [OcrLine("2. 계약금액 :", (0.1 * w, 0.1 * h, 0.3 * w, 0.12 * h), 0.9), OcrLine("금 삼억원정", (0.32 * w, 0.1 * h, 0.5 * w, 0.12 * h), 0.8)]


def test_scan_page_goes_through_engine(tmp_path, monkeypatch):
    doc = fitz.open()
    doc.new_page(width=595, height=842)  # no text layer -> scan
    path = str(tmp_path / "scan.pdf")
    doc.save(path)
    assert classify_page(fitz.open(path)[0]) == "scan"
    monkeypatch.setattr("ai.ocr.get_engine", lambda name=None: FakeEngine())
    lines = run_ocr(path)
    assert len(lines) == 1 and lines[0]["text"] == "2. 계약금액 : 금 삼억원정"
    assert lines[0]["source"] == "paddle" and lines[0]["bbox"][0] == pytest.approx(0.1, abs=0.01)


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_tesseract_reads_rendered_scan(tmp_path):
    src = fitz.open(contract_pdf(str(tmp_path / "c.pdf")))
    png = str(tmp_path / "p.png")
    src[0].get_pixmap(dpi=200).save(png)
    scan = str(tmp_path / "scan.pdf")
    with fitz.open(png) as img:
        open(scan, "wb").write(img.convert_to_pdf())
    lines = run_ocr(scan, engine="tesseract")
    assert lines and all(ln["source"] == "tesseract" for ln in lines)
    assert any("2026" in ln["text"] for ln in lines)
