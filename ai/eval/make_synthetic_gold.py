"""Synthetic gold set: N Korean contracts with exact gold labels (가공 데이터 — every value is fabricated, NFR-09).

Each doc is a PDF drawn with PyMuPDF (fontname="korea-s") plus `<doc_id>.json` in the 03_데이터정의 §3.2 gold schema.
Gold bboxes come from where the value text was drawn (not from OCR). Every third doc is a scan variant:
rasterized at 200dpi, rotated ±1~3°, light noise, JPEG; its gold bboxes are transformed with the same matrix.
`text_lines` (every drawn line) is an optional gold extension used by eval/ocr_benchmark.py for CER/WER.

    PYTHONPATH=backend python -m eval.make_synthetic_gold --out data/gold/synthetic -n 30
"""

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

import cv2
import numpy as np
import pymupdf as fitz
from ai.extract.normalize import biz_no_checksum_ok
from ai.types import FIELD_CODES

W, H = 595, 842
FONT, FS, LH = "korea-s", 10, 20
ASCENT, DESCENT = 1.0, 0.2  # korea-s glyph box relative to font size, as PyMuPDF's text extraction reports it
NOTICE = "※ 평가용 가공 데이터 — 실존 기관·금액·번호가 아닙니다"
SCAN_DPI = 200

ORGS = ["한빛도시공사", "새솔개발", "푸른강건설", "다온엔지니어링", "미르시설관리", "가람정보기술", "누리환경", "해솔물산", "온새미로산업", "버들기술"]
CITIES = ["한빛시", "가람군", "새솔시", "누리구", "푸른시"]
WORKS = {
    "공사": ["하수관로 정비공사", "도로 확장공사", "청사 리모델링 공사", "체육관 신축공사", "노후 상수도관 교체 및 블록시스템 구축공사"],
    "용역": ["정보시스템 유지관리 용역", "도시계획 수립 용역", "시설물 정밀안전진단 용역", "통합관제센터 운영 및 영상분석 고도화 용역"],
    "물품": ["사무용 전산장비 구매", "제설장비 구매", "공공도서관 열람석 및 서가 일괄 구매"],
}
# kind -> (title, name label, due label, creditor label, contractor label)
KINDS = {
    "공사": ("공 사 도 급 계 약 서", "공사명", "준공기한", "발주자(갑)", "수급인(을)"),
    "용역": ("용 역 계 약 서", "용역명", "계약이행기일", "발주기관(갑)", "계약상대자(을)"),
    "물품": ("물 품 구 매 계 약 서", "계약건명", "납품기한", "발주자(갑)", "공급자(을)"),
}
_DIGITS = "영일이삼사오육칠팔구"


# ---------- value formats ----------


def korean_amount(n: int) -> str:
    """350000000 -> '삼억오천만' (n < 1조)."""

    def four(m: int) -> str:
        s = ""
        for v, u in ((1000, "천"), (100, "백"), (10, "십"), (1, "")):
            d, m = divmod(m, v)
            if d:
                s += ("" if d == 1 and u else _DIGITS[d]) + u
        return s

    out = ""
    for v, u in ((10**8, "억"), (10**4, "만"), (1, "")):
        part, n = divmod(n, v)
        if part:
            out += four(part) + u
    return out


def mixed_amount(n: int) -> str:
    """350000000 -> '3억 5,000만' (digit groups with Korean units)."""
    eok, man = divmod(n // 10**4, 10**4)
    return " ".join(p for p in (f"{eok:,}억" if eok else "", f"{man:,}만" if man else "") if p)


def amount_text(n: int, rng: random.Random) -> str:
    k = korean_amount(n)
    return rng.choice([f"일금 {k}원정 (₩{n:,})", f"금 {n:,}원", f"₩{n:,}", f"금 {k}원정", f"{mixed_amount(n)}원", f"금{k}원정(₩{n:,})"])


def date_text(d: date, rng: random.Random) -> str:
    return rng.choice(
        [
            f"{d.year}년 {d.month}월 {d.day}일",
            f"{d.year}. {d.month}. {d.day}.",
            d.isoformat(),
            f"{d:%Y.%m.%d}",
            f"{d:%y.%m.%d}",
            f"{d.year}년 {d:%m}월 {d:%d}일",
        ]
    )


def biz_no(rng: random.Random) -> str:
    while True:
        digits = "".join(str(rng.randint(0, 9)) for _ in range(10))
        if digits[0] != "0" and biz_no_checksum_ok(digits):
            return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


def company(org: str, rng: random.Random) -> str:
    return rng.choice([f"(주){org}", f"주식회사 {org}", f"{org} 주식회사", f"㈜{org}", f"(주) {org}"])


def make_values(rng: random.Random) -> dict:
    kind = rng.choice(list(KINDS))
    city = rng.choice(CITIES)
    name = f"{city} {rng.choice(WORKS[kind])}"
    amount = rng.randint(100, 50_000) * 100_000
    cdate = date(2025, 1, 1) + timedelta(days=rng.randint(0, 600))
    due = cdate + timedelta(days=rng.randint(60, 400))
    orgs = rng.sample(ORGS, 2)
    v = {
        "kind": kind,
        "layout": rng.choice(["list", "table"]),
        "two_pages": rng.random() < 0.3,
        "contract_name": name,
        "wrap_name": len(name) > 22,  # long names are drawn over two lines
        "contract_amount": (amount, amount_text(amount, rng)),
        "guarantee_amount": None,
        "contract_date": (cdate.isoformat(), date_text(cdate, rng)),
        "performance_due_date": (due.isoformat(), date_text(due, rng)) if rng.random() > 0.1 else None,
        "guarantee_period": None,
        "creditor_name": rng.choice([company(orgs[0], rng), f"{city}청"]),
        "creditor_biz_no": biz_no(rng) if rng.random() > 0.2 else None,
        "contractor": company(orgs[1], rng),
        "contractor_biz_no": biz_no(rng),
        "blank_style": rng.random() < 0.3,  # missing value: label printed with an empty value instead of no row
    }
    if rng.random() > 0.15:
        g = amount * rng.choice([10, 15]) // 100
        v["guarantee_amount"] = (g, amount_text(g, rng))
    r = rng.random()
    if r < 0.4 and v["performance_due_date"]:
        v["guarantee_period"] = ({"start": cdate.isoformat(), "end": due.isoformat()}, "계약일로부터 준공일까지")
    elif r < 0.85:
        end = due + timedelta(days=rng.choice([0, 30, 60]))
        v["guarantee_period"] = ({"start": cdate.isoformat(), "end": end.isoformat()}, f"{date_text(cdate, rng)} ~ {date_text(end, rng)}")
    return v


# ---------- drawing ----------


class Sheet:
    """Draws text and records every drawn line (text_lines) and value box (labels) in PDF points."""

    def __init__(self):
        self.doc = fitz.open()
        self.lines: list[dict] = []
        self.labels: dict[str, dict | None] = {}

    def page(self, no: int) -> fitz.Page:
        while len(self.doc) < no:
            self.doc.new_page(width=W, height=H)
        return self.doc[no - 1]

    def put(self, page: int, x: float, y: float, text: str, fs: float = FS) -> None:
        if not text:
            return
        self.page(page).insert_text((x, y), text, fontsize=fs, fontname=FONT)
        self.lines.append({"page": page, "text": text, "bbox": self.box(x, y, "", text, fs)})

    @staticmethod
    def box(x: float, y: float, prefix: str, value: str, fs: float = FS) -> list[float]:
        x0 = x + fitz.get_text_length(prefix, fontname=FONT, fontsize=fs)
        return [x0, y - ASCENT * fs, x0 + fitz.get_text_length(value, fontname=FONT, fontsize=fs), y + DESCENT * fs]

    def label(self, code: str, value, page: int, boxes: list[list[float]], raw: str) -> None:
        bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
        self.labels[code] = {"value": value, "page": page, "bbox": bbox, "raw_text": raw}


def split_name(name: str) -> tuple[str, str]:
    words = name.split(" ")
    cut = max(1, len(words) // 2)
    return " ".join(words[:cut]), " ".join(words[cut:])


def rows_of(v: dict) -> list[tuple[str, str, str | None, object]]:
    """(label, written value, field code, gold value) in document order; missing optional fields drop out
    or keep an empty value (blank_style)."""
    _, name_label, due_label, cred_label, con_label = KINDS[v["kind"]]
    rows: list[tuple[str, str, str | None, object]] = [
        (name_label, v["contract_name"], "contract_name", v["contract_name"]),
        ("계약금액", v["contract_amount"][1], "contract_amount", v["contract_amount"][0]),
        ("계약일자", v["contract_date"][1], "contract_date", v["contract_date"][0]),
    ]
    for label, code in ((due_label, "performance_due_date"), ("계약보증금", "guarantee_amount"), ("보증기간", "guarantee_period")):
        if v[code]:
            rows.append((label, v[code][1], code, v[code][0]))
        elif v["blank_style"]:
            rows.append((label, "", code, None))
    rows.append((cred_label, v["creditor_name"], "creditor_name", v["creditor_name"]))
    if v["creditor_biz_no"] or v["blank_style"]:
        rows.append((f"{cred_label[:-3]} 사업자등록번호", v["creditor_biz_no"] or "", "creditor_biz_no", v["creditor_biz_no"]))
    rows.append((con_label, v["contractor"], None, None))
    rows.append((f"{con_label[:-3]} 사업자등록번호", v["contractor_biz_no"], None, None))
    return rows


def draw_contract(v: dict) -> Sheet:
    s = Sheet()
    title = KINDS[v["kind"]][0]
    s.put(1, W - 40 - fitz.get_text_length(NOTICE, fontname=FONT, fontsize=7), 30, NOTICE, fs=7)
    s.put(1, (W - fitz.get_text_length(title, fontname=FONT, fontsize=16)) / 2, 70, title, fs=16)
    y = 110.0
    rows = rows_of(v)
    if v["layout"] == "list":
        for i, (label, text, code, gold) in enumerate(rows, 1):
            prefix = f"{i}. {label} : "
            if code == "contract_name" and v["wrap_name"]:
                a, b = split_name(text)
                s.put(1, 50, y, prefix + a)
                xv = 50 + fitz.get_text_length(prefix, fontname=FONT, fontsize=FS)
                s.put(1, xv, y + LH, b)
                s.label("contract_name", gold, 1, [s.box(50, y, prefix, a), s.box(xv, y + LH, "", b)], f"{a} {b}")
                y += LH
            else:
                s.put(1, 50, y, prefix + text)
                if code and gold is not None:
                    s.label(code, gold, 1, [s.box(50, y, prefix, text)], text)
            y += LH
    else:  # ruled two-column table
        page = s.page(1)
        x0, xm, x1 = 50, 190, 545
        for label, text, code, gold in rows:
            wrap = code == "contract_name" and v["wrap_name"]
            h = 38 if wrap else 22
            for rect in (fitz.Rect(x0, y, xm, y + h), fitz.Rect(xm, y, x1, y + h)):
                page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            s.put(1, x0 + 6, y + 15, label)
            if wrap:
                a, b = split_name(text)
                s.put(1, xm + 6, y + 15, a)
                s.put(1, xm + 6, y + 31, b)
                s.label("contract_name", gold, 1, [s.box(xm + 6, y + 15, "", a), s.box(xm + 6, y + 31, "", b)], f"{a} {b}")
            else:
                s.put(1, xm + 6, y + 15, text)
                if code and gold is not None:
                    s.label(code, gold, 1, [s.box(xm + 6, y + 15, "", text)], text)
            y += h

    clauses = [
        "제1조(목적) 본 계약은 계약의 이행에 필요한 사항을 정한다.",
        "제2조(계약기간) 계약기간은 착공일로부터 이행기한까지로 한다.",
        "제3조(지체상금) 을이 기한 내에 이행하지 못한 때에는 지체일수",
        f"1일마다 계약금액의 1000분의 {v['contract_amount'][0] % 3 + 1}에 해당하는 지체상금을 납부한다.",
        "제4조(하자담보) 을은 준공 후 2년간 하자보수 책임을 진다.",
        "제5조(계약보증금) 을은 계약보증금을 계약체결 전까지 납부한다.",
        "제6조(분쟁해결) 분쟁은 갑의 소재지 관할 법원에서 해결한다.",
        "위 계약을 증명하기 위하여 계약서 2통을 작성하여 보관한다.",
    ]
    page_no, y = (2, 70.0) if v["two_pages"] else (1, y + 30)
    for line in clauses:
        s.put(page_no, 50, y, line)
        y += LH
    y += 10
    s.put(page_no, 250, y, v["contract_date"][1])
    s.put(page_no, 300, y + 2 * LH, f"갑 : {v['creditor_name']} (인)")
    s.put(page_no, 300, y + 3 * LH, f"을 : {v['contractor']} (인)")
    return s


# ---------- scan variant ----------


def _transform(box: list[float], m: np.ndarray, w: int, h: int) -> list[float]:
    """Normalized box -> axis-aligned bounds after the 2x3 pixel affine `m` (same rule as ai.ocr.preprocess.map_box)."""
    x0, y0, x1, y1 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x0, y1, 1], [x1, y1, 1]]) @ m.T
    return [max(0.0, pts[:, 0].min() / w), max(0.0, pts[:, 1].min() / h), min(1.0, pts[:, 0].max() / w), min(1.0, pts[:, 1].max() / h)]


def to_scan(doc: fitz.Document, labels: dict, lines: list[dict], rng: random.Random) -> fitz.Document:
    """Rasterize, rotate ±1~3°, add noise; gold boxes (already normalized) are transformed in place."""
    noise = np.random.default_rng(rng.randint(0, 2**31))
    out = fitz.open()
    for page in doc.pages():
        pix = page.get_pixmap(dpi=SCAN_DPI, colorspace=fitz.csGRAY, alpha=False)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w)
        angle = rng.choice([-1, 1]) * rng.uniform(1, 3)
        m = cv2.getRotationMatrix2D((pix.w / 2, pix.h / 2), angle, 1.0)
        rotated = cv2.warpAffine(img, m, (pix.w, pix.h), flags=cv2.INTER_LINEAR, borderValue=255)
        noisy = np.clip(rotated.astype(np.float32) + noise.normal(0, 10, rotated.shape), 0, 255).astype(np.uint8)
        jpg = cv2.imencode(".jpg", noisy, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=jpg)
        page_no = page.number + 1
        for item in [lb for lb in labels.values() if lb] + lines:
            if item["page"] == page_no:
                item["bbox"] = _transform(item["bbox"], m, pix.w, pix.h)
    return out


def _norm(box: list[float]) -> list[float]:
    return [box[0] / W, box[1] / H, box[2] / W, box[3] / H]


def make_doc(i: int, rng: random.Random, out_dir: Path) -> dict:
    v = make_values(rng)
    sheet = draw_contract(v)
    labels = {code: (lb := sheet.labels.get(code)) and {**lb, "bbox": _norm(lb["bbox"])} for code in FIELD_CODES}
    lines = sorted(({**ln, "bbox": _norm(ln["bbox"])} for ln in sheet.lines), key=lambda ln: (ln["page"], round(ln["bbox"][1], 3), ln["bbox"][0]))
    scan = i % 3 == 0
    doc = to_scan(sheet.doc, labels, lines, rng) if scan else sheet.doc
    doc_id = f"synthetic_{i:04d}"
    doc.save(out_dir / f"{doc_id}.pdf", garbage=3, deflate=True)
    for item in [lb for lb in labels.values() if lb] + lines:
        item["bbox"] = [round(c, 5) for c in item["bbox"]]
    return {
        "doc_id": doc_id,
        "doc_name": f"가공 {KINDS[v['kind']][0].replace(' ', '')} #{i} ({'scan' if scan else 'native'}, {v['layout']})",
        "source_type": "scan" if scan else "native",
        "file": f"{doc_id}.pdf",
        "synthetic": True,
        "labels": labels,
        "text_lines": lines,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/gold/synthetic")
    ap.add_argument("-n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261012)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    for i in range(1, args.n + 1):
        gold = make_doc(i, rng, out)
        (out / f"{gold['doc_id']}.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.n} synthetic gold docs to {out}")


if __name__ == "__main__":
    main()
