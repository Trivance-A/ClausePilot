"""Build the form gold set: fill fabricated values into public contract forms (data/samples) and record exact bboxes.

Run from the repo root:  backend/.venv/bin/python data/gold/forms/make_gold.py
- law/*.pdf : official PDF layout. Template text in the value cell is redacted (ruling kept) and the value is
              written with PyMuPDF (korea-s); the gold bbox is read back from the page text layer.
- *.hwp     : HWP 5.x has no LibreOffice filter, so normalize_to_pdf renders the parsed text
              (blocks_to_lines -> render_lines_to_pdf). Values are substituted into the parsed blocks and rendered the
              same way, i.e. exactly what the pipeline produces for a filled HWP upload.
- scans     : 200dpi raster, rotated 1-3 deg, gaussian noise, JPEG; bboxes go through the same affine matrix.
All values are fabricated (deterministic per doc_id); business numbers pass biz_no_checksum_ok.
"""

import json
import random
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import cv2
import numpy as np
import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ai.extract.normalize import biz_no_checksum_ok, korean_to_int
from ai.parser import blocks_to_lines, parse_hwp, render_lines_to_pdf

SAMPLES = ROOT / "data" / "samples"
OUT = Path(__file__).resolve().parent
FIELDS = [
    "contract_name",
    "contract_amount",
    "guarantee_amount",
    "contract_date",
    "performance_due_date",
    "guarantee_period",
    "creditor_name",
    "creditor_biz_no",
]
FONT = fitz.Font("korea")

# ---------- fabricated values ----------

AGENCIES = ["한빛시 도로관리사업소장", "새솔군 상하수도사업소장", "가람시 시설관리공단 이사장", "누리도 건설본부장", "다온시 교육지원청 교육장", "미르구청장"]
COMPANIES = ["(주)한빛건설", "대성테크 주식회사", "(주)누리정보시스템", "가온산업(주)", "(주)서해엔지니어링", "다솜물산 주식회사", "(주)미래기계", "청람전기(주)", "주식회사 바른물류", "(주)솔빛화학"]
NAMES = {
    "works": ["한빛시 중앙로 도로 확장 공사", "새솔군 정수장 노후관 교체 공사", "가람초등학교 강당 증축 공사", "누리천 제방 보강 공사"],
    "goods": ["청사 업무용 노트북 구매", "소방용 방화복 제조·구매", "도서관 서가 및 열람대 구매", "제설용 염화칼슘 구매"],
    "services": ["통합민원시스템 유지관리 용역", "하천 수질 모니터링 용역", "청사 시설 경비 용역", "교통량 조사 및 분석 용역"],
}


def kor_amount(n: int) -> str:
    """350000000 -> 삼억오천만 (일 omitted before 십/백/천, kept before 억/만)."""
    digits = "영일이삼사오육칠팔구"
    parts = []
    for unit, size in (("억", 10**8), ("만", 10**4), ("", 1)):
        group, n = divmod(n, size)
        if not group:
            continue
        s = ""
        for u, p in (("천", 1000), ("백", 100), ("십", 10), ("", 1)):
            d, group = divmod(group, p)
            if d:
                s += ("" if d == 1 and u else digits[d]) + u
        parts.append(s + unit)
    return "".join(parts)


def fake_biz_no(rng: random.Random) -> str:
    while True:
        head = str(rng.randint(101, 899)) + f"{rng.randint(1, 99):02d}" + f"{rng.randint(0, 9999):04d}"
        for check in "0123456789":
            if biz_no_checksum_ok(head + check):
                s = head + check
                return f"{s[:3]}-{s[3:5]}-{s[5:]}"


def values(doc_id: str, kind: str) -> dict:
    rng = random.Random(doc_id)
    amount = rng.randrange(20, 950) * 1_000_000 + rng.choice([0, 0, 500_000, 250_000])
    c_date = date(2026, rng.randint(1, 9), rng.randint(1, 28))
    start = c_date + timedelta(days=rng.randint(3, 12))  # differs from the contract date so dates stay unambiguous
    due = start + timedelta(days=rng.randint(90, 420))
    g_start = due + timedelta(days=1)
    v = {
        "name": rng.choice(NAMES[kind]),
        "amount": amount,
        "g_amount": amount * rng.choice([10, 15]) // 100,
        "d_amount": amount * 3 // 100,  # 하자보수보증금 (3%)
        "c_date": c_date,
        "start": start,
        "due": due,
        "g_period": (g_start, g_start + timedelta(days=729)),
        "agency": rng.choice(AGENCIES),
        "creditor": rng.choice(COMPANIES),
        "biz_no": fake_biz_no(rng),
        "other": rng.choice(COMPANIES),
        "other_biz_no": fake_biz_no(rng),
    }
    while v["other"] == v["creditor"]:
        v["other"] = rng.choice(COMPANIES)
    assert korean_to_int(kor_amount(amount)) == amount
    return v


def dot(d: date) -> str:
    return f"{d.year}. {d.month}. {d.day}."


def kdate(d: date) -> str:
    return f"{d.year}년 {d.month}월 {d.day}일"


def won(n: int, prefix: str = "금", sep: str = "") -> str:
    return f"{prefix} {kor_amount(n)}원정{sep}(￦{n:,})"


# ---------- page text helpers ----------


def page_chars(page: fitz.Page) -> list[tuple[str, fitz.Rect]]:
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for line in b.get("lines", []):
            for span in line["spans"]:
                out.extend((c["c"], fitz.Rect(c["bbox"])) for c in span["chars"] if not c["c"].isspace())
    return out


def find(page: fitz.Page, text: str, below: float = -1, sub: str | None = None, bottom: bool = False) -> fitz.Rect | None:
    """Top-most (or bottom-most) occurrence of `text` (whitespace-insensitive) on the page; with `sub`, the bbox of that part only."""
    chars = page_chars(page)
    stream = "".join(c for c, _ in chars)
    key = re.sub(r"\s+", "", text)
    hits = [m.start() for m in re.finditer(re.escape(key), stream) if chars[m.start()][1].y0 >= below]
    if not hits:
        return None
    i = (max if bottom else min)(hits, key=lambda h: (round(chars[h][1].y0), chars[h][1].x0))
    j = i + len(key)
    if sub:
        k = stream.find(re.sub(r"\s+", "", sub), i, j)
        assert k >= 0, (text, sub)
        i, j = k, k + len(re.sub(r"\s+", "", sub))
    r = fitz.Rect(chars[i][1])
    for _, cr in chars[i + 1 : j]:
        r |= cr
    return r


def norm_bbox(r: fitz.Rect, page: fitz.Page) -> list[float]:
    w, h = page.rect.width, page.rect.height
    return [round(r.x0 / w, 5), round(r.y0 / h, 5), round(r.x1 / w, 5), round(r.y1 / h, 5)]


def label(value, page: fitz.Page, rect: fitz.Rect, raw: str) -> dict:
    return {"value": value, "page": page.number + 1, "bbox": norm_bbox(rect, page), "raw_text": raw}


# ---------- law PDFs: overlay into the real layout ----------


class Overlay:
    """Collect redactions + writes for one page, apply them, then read gold bboxes back from the text layer."""

    def __init__(self, page: fitz.Page):
        self.page = page
        self.cells = [fitz.Rect(c) for t in page.find_tables().tables for c in t.cells if c]
        self.redact: list[fitz.Rect] = []
        self.writes: list[tuple[fitz.Rect, str, str]] = []  # area, text, align
        self.golds: list[tuple[str, object, str, str | None]] = []  # field, value, written text, sub-part for bbox

    def cell_of(self, r: fitz.Rect) -> fitz.Rect:
        c = r.tl + (r.br - r.tl) * 0.5
        return min((x for x in self.cells if c in x), key=lambda x: x.width * x.height)

    def right_of(self, cell: fitz.Rect) -> fitz.Rect:
        cy = (cell.y0 + cell.y1) / 2
        return min((x for x in self.cells if x.y0 < cy < x.y1 and x.x0 >= cell.x1 - 3), key=lambda x: x.x0)

    def below(self, cell: fitz.Rect) -> fitz.Rect:
        cx = (cell.x0 + cell.x1) / 2
        return min((x for x in self.cells if x.x0 < cx < x.x1 and x.y0 >= cell.y1 - 3), key=lambda x: x.y0)

    def put(self, area: fitz.Rect, text: str, field: str | None = None, value=None, sub: str | None = None, align: str = "left", clear: bool = True):
        if clear:
            self.redact.append(area + (1, 1, -1, -1))
        self.writes.append((area, text, align))
        if field:
            self.golds.append((field, value, text, sub))

    def cell(self, label_text: str, text: str, field: str | None = None, value=None, sub: str | None = None, nth_below: bool = False):
        lab = find(self.page, label_text)
        assert lab is not None, label_text
        target = self.below(self.cell_of(lab)) if nth_below else self.right_of(self.cell_of(lab))
        self.put(target, text, field, value, sub)

    def dateline(self, anchor: str, text: str, where: str = "above", field: str | None = None, value=None):
        """Replace the '.   .   .' date placeholder line nearest to the (bottom-most) anchor text."""
        a = find(self.page, anchor, bottom=True)
        dots = [
            fitz.Rect(line["bbox"])
            for b in self.page.get_text("dict")["blocks"]
            for line in b.get("lines", [])
            if re.fullmatch(r"[.\s]+", "".join(s["text"] for s in line["spans"]))
        ]
        groups: list[list[fitz.Rect]] = []  # dots are often separate text lines: group them by baseline
        for r in sorted(dots, key=lambda r: (round(r.y0), r.x0)):
            if groups and abs(groups[-1][-1].y0 - r.y0) < 2 and r.x0 - groups[-1][-1].x1 < 60:
                groups[-1].append(r)
            else:
                groups.append([r])
        lines = []
        for g in groups:
            u = fitz.Rect(g[0])
            for r in g[1:]:
                u |= r
            if len(g) >= 3 or self.page.get_textbox(u).count(".") >= 3:
                lines.append(u)
        lines = [r for r in lines if (r.y1 <= a.y0 + 1 if where == "above" else r.y0 >= a.y1 - 1)]
        r = min(lines, key=lambda r: abs(r.y0 - a.y0))
        self.redact.append(r + (-1, -1, 1, 1))
        self.writes.append((fitz.Rect(r.x0 - 30, r.y0 - 2, r.x1 + 60, r.y1 + 2), text, "left"))
        if field:
            self.golds.append((field, value, text, None))

    def before(self, anchor: str, text: str, field: str | None = None, value=None):
        a = find(self.page, anchor)
        self.put(fitz.Rect(a.x0 - 170, a.y0 - 2, a.x0 - 4, a.y1 + 2), text, field, value, align="right", clear=False)

    def after(self, anchor: str, text: str, field: str | None = None, value=None):
        a = find(self.page, anchor)
        self.put(fitz.Rect(a.x1 + 4, a.y0 - 2, a.x1 + 170, a.y1 + 2), text, field, value, clear=False)

    def apply(self) -> dict:
        for r in self.redact:
            self.page.add_redact_annot(r)
        self.page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        # TextWriter embeds the CJK font, so ASCII digits get proportional widths (korea-s would make them full-width)
        tw = fitz.TextWriter(self.page.rect)
        for area, text, align in self.writes:
            size = 9.5
            while FONT.text_length(text, fontsize=size) > area.width - 6 and size > 5:
                size -= 0.5
            width = FONT.text_length(text, fontsize=size)
            x = area.x1 - 3 - width if align == "right" else area.x0 + 4
            tw.append((x, (area.y0 + area.y1) / 2 + size * 0.35), text, font=FONT, fontsize=size)
        tw.write_text(self.page)
        out = {}
        for field, value, text, sub in self.golds:
            r = find(self.page, text, sub=sub)
            assert r is not None, (field, text)
            out[field] = label(value, self.page, r, sub or text)
        return out


def iso(d: date) -> str:
    return d.isoformat()


def fill_law(doc_id: str, page: fitz.Page) -> dict:
    form = doc_id.rsplit("_", 1)[1]
    kind = {"07": "works", "08": "goods", "09": "services"}.get(form, "works")
    v = values(doc_id, kind)
    o = Overlay(page)
    local = doc_id.startswith("kr_local")
    if form in ("07", "08", "09"):
        o.cell("발주처", v["agency"], "creditor_name", v["agency"])
        o.cell({"works": "공사명", "goods": "물품명", "services": "용역명"}[kind], v["name"], "contract_name", v["name"])
        o.cell("계약금액", won(v["amount"]), "contract_amount", v["amount"])
        o.cell("계약보증금", won(v["g_amount"]), "guarantee_amount", v["g_amount"])
        if kind == "works":
            o.cell("착공연월일", dot(v["start"]))
            o.cell("준공연월일", dot(v["due"]), "performance_due_date", iso(v["due"]))
            gs, ge = v["g_period"]
            o.cell("담보책임존속기간" if local else "하자담보책임기간", f"{dot(gs)}~{dot(ge)}", "guarantee_period", {"start": iso(gs), "end": iso(ge)}, nth_below=True)
        else:
            rng_label = {"goods": "납품일" if local else "납품일자", "services": "계약기간"}[kind]
            o.cell(rng_label, f"{dot(v['start'])} ~ {dot(v['due'])}", "performance_due_date", iso(v["due"]), sub=dot(v["due"]))
        o.dateline("자치단체의장또는" if local else "중앙관서의장또는", dot(v["c_date"]), "above", "contract_date", iso(v["c_date"]))
        o.after("상호또는법인명" if local else "상호또는법인명칭", v["other"])  # contractor = debtor, not a gold field
    elif form in ("10", "12"):
        o.cell("계약건명", v["name"], "contract_name", v["name"])
        o.cell("계약금액", won(v["amount"]), "contract_amount", v["amount"])
        if form == "10":
            o.cell("계약보증금액", won(v["g_amount"]), "guarantee_amount", v["g_amount"])
            o.cell("계약(예정)연월일", dot(v["c_date"]), "contract_date", iso(v["c_date"]))
            o.cell("계약이행기간", f"{kdate(v['start'])}부터 {kdate(v['due'])}까지", "performance_due_date", iso(v["due"]), sub=kdate(v["due"]))
        else:
            o.cell("준공연월일", dot(v["due"]), "performance_due_date", iso(v["due"]))
            gs, ge = v["g_period"]
            o.cell("담보책임존속기간" if local else "하자담보책임기간", f"{dot(gs)}~{dot(ge)}", "guarantee_period", {"start": iso(gs), "end": iso(ge)}, nth_below=True)
            o.cell("하자보수보증금률" if local else "하자보수보증금율", f"(3)% 금 {v['d_amount']:,}원정", "guarantee_amount", v["d_amount"], sub=f"금 {v['d_amount']:,}원정", nth_below=True)
        o.before("귀하", v["agency"], "creditor_name", v["agency"])
        o.dateline("상호또는법인명", dot(v["c_date"] + timedelta(days=2)), "above")  # payment date: distractor
        o.after("상호또는법인명" if local else "상호또는법인명칭", v["other"])
    elif form == "13" and not local:  # 질권설정동의서
        o.cell("보증금명", "계약보증금", nth_below=True)
        o.cell("보증금액", f"{v['g_amount']:,}원", "guarantee_amount", v["g_amount"], nth_below=True)
        o.dateline("상호또는법인명칭", dot(v["c_date"]), "above")
        o.after("상호또는법인명칭", v["other"])
    else:  # 각서: no contract fields at all (all-null negative), only the pledgor block is filled
        o.dateline("상호또는법인명", dot(v["c_date"]), "above")
        o.after("상호또는법인명", v["other"])
    return o.apply()


# ---------- HWP: fill parsed blocks, render like normalize_to_pdf's fallback ----------


class BlockFiller:
    def __init__(self, blocks: list[dict], v: dict):
        self.blocks, self.v = blocks, v
        self.golds: list[tuple[str, object, str, str]] = []  # field, value, full filled text, value part
        self.done: set[str] = set()
        # FTC files = front sheet (전문, the fill-in part) + 본문 (clauses) + annexes; only the front sheet is filled
        self.front = next(
            (i for i, b in enumerate(blocks) if i > 3 and b["type"] == "p" and b["text"].strip().endswith("(본문)")),
            len(blocks),
        )

    def texts(self):
        for b in self.blocks[: self.front]:
            if b["type"] == "p":
                yield b, None
            else:
                for cell in b["cells"]:
                    yield b, cell

    def sub(self, field: str | None, pattern: str, repl: str, value=None, part: str | None = None, cond=None) -> bool:
        """Replace the first match of `pattern` in the front sheet; record (field, value) with the value part's text."""
        if field and field in self.done:
            return False
        prev = ""
        for b, cell in self.texts():
            text = cell[2] if cell else b["text"]
            if (cond is None or cond(text, prev)) and (m := re.search(pattern, text)):
                new = text[: m.start()] + m.expand(repl) + text[m.end() :]
                if cell:
                    cell[2] = new
                else:
                    b["text"] = new
                if field:
                    self.done.add(field)
                    self.golds.append((field, value, m.expand(repl), part or m.expand(repl)))
                return True
            prev = text
        return False

    def party_cell(self, party: str, value_labels: list[str], text: str, field: str | None, value) -> bool:
        """Signature block of `party` (원사업자/수급사업자): a table column headed by it, or a cell starting with '* party'."""
        for b in self.blocks[: self.front]:
            if b["type"] != "table":
                continue
            cols = {c for r, c, t in b["cells"] if r == 1 and re.sub(r"\s", "", t) == party}
            for cell in b["cells"]:
                if (cell[0] == 2 and cell[1] in cols) or re.sub(r"\s", "", cell[2]).startswith("*" + party):
                    for lab in value_labels:
                        if lab in cell[2]:
                            cell[2] = cell[2].replace(lab, f"{lab} {text}", 1)
                            if field:
                                self.golds.append((field, value, text, text))
                            return True
        return False


def fill_ftc(f: BlockFiller):
    v = f.v
    names = r"(?:하도급\s*(?:공사|계약|사업)명|용역\s*계약명|공사명|계약명(?:\(하도급계약명\))?|[^:]*위탁명\s*\(계약명\))"
    f.sub("contract_name", r"^(\s*(?:\d+\.|◇|ㅇ|◦)?\s*" + names + r")\s*:\s*$", rf"\1 : {v['name']}", v["name"], v["name"])
    amount = f"일금 {kor_amount(v['amount'])}원정 (￦{v['amount']:,})"
    f.sub(
        "contract_amount",
        r"일?금\s*원정\s*\(\s*￦\s*\)",
        amount,
        v["amount"],
        amount,
        cond=lambda t, p: "계약금액" in re.sub(r"\s", "", t) and "변경" not in t and not re.search(r"\[\s*월", t),
    )
    g = f"일금 {kor_amount(v['g_amount'])}원정 (￦{v['g_amount']:,})"
    (
        f.sub("guarantee_amount", r"일금\s*원정\s*\(\s*￦\s*\)", g, v["g_amount"], g, cond=lambda t, p: re.sub(r"\s", "", p).endswith("계약이행보증금"))
        or f.sub("guarantee_amount", r"(계약이행보증금\s*:\s*계약금액의\s*\(\s*\)%,\s*)일금\s*원정\s*\(\s*￦\s*\)", rf"\g<1>{g}", v["g_amount"], g)
        or f.sub("guarantee_amount", r"(계약이행보증금\*?\s*:\s*)원", rf"\g<1>{v['g_amount']:,}원", v["g_amount"], f"{v['g_amount']:,}원")
    )
    due, start = kdate(v["due"]), kdate(v["start"])
    f.sub(None, r"(착공|개시)\s+년\s+월\s+일", rf"\1 {start}")
    period = r"((?:계약|용역)기간\s*:\s*)년\s+월\s+일부터"
    (
        f.sub("performance_due_date", r"(준공|완공|종료)\s+년\s+월\s+일", rf"\1 {due}", v["due"].isoformat(), due)
        or f.sub("performance_due_date", period + r"\s+년\s+월\s+일까지", rf"\g<1>{start}부터 {due}까지", v["due"].isoformat(), due)
        or (  # period split over two paragraphs: '...기간 : 년 월 일부터' / '년 월 일까지'
            f.sub(None, period + r"\s*$", rf"\g<1>{start}부터")
            and f.sub("performance_due_date", r"^(\s*)년\s+월\s+일까지\s*$", rf"\g<1>{due}까지", v["due"].isoformat(), due, cond=lambda t, p: p.rstrip().endswith("부터"))
        )
    )
    f.sub("contract_date", r"^\s*(?:20)?\s*년\s+월\s+일\s*$", kdate(v["c_date"]), v["c_date"].isoformat())
    f.party_cell("원사업자", ["상호 또는 명칭 :", "상호 :"], v["creditor"], "creditor_name", v["creditor"])
    f.party_cell("원사업자", ["사업자(법인)번호 :"], v["biz_no"], "creditor_biz_no", v["biz_no"])
    f.party_cell("수급사업자", ["상호 또는 명칭 :", "상호 :"], v["other"], None, None)
    f.party_cell("수급사업자", ["사업자(법인)번호 :"], v["other_biz_no"], None, None)


def fill_pps_lease(f: BlockFiller):
    v = f.v
    f.sub("contract_date", r"(계약일자\s*:\s*)2005\s*\.\s*\.\s*\.", rf"\g<1>{dot(v['c_date'])}", v["c_date"].isoformat(), dot(v["c_date"]))
    f.sub(None, r"(상\s+호\s*:)\s*$", rf"\1 {v['other']}")
    for b in f.blocks:  # 대여금액 / 대여기간 value cells (row label in col 1, value in col 2)
        if b["type"] != "table":
            continue
        labels = {re.sub(r"\s", "", t): r for r, c, t in b["cells"] if c == 1}
        for cell in b["cells"]:
            if cell[1] == 2 and cell[0] == labels.get("대여금액"):
                cell[2] = won(v["amount"])
                f.golds.append(("contract_amount", v["amount"], cell[2], cell[2]))
            if cell[1] == 2 and cell[0] == labels.get("대여기간"):
                cell[2] = f"{dot(v['start'])} ~ {dot(v['due'])}"
                f.golds.append(("performance_due_date", v["due"].isoformat(), cell[2], dot(v["due"])))
    f.golds.append(("creditor_name", "대한민국 조달청", "대한민국 조달청", "대한민국 조달청"))  # pre-printed party


def fill_hwp(doc_id: str, src: Path, out_pdf: Path) -> dict:
    blocks = parse_hwp(str(src))
    kind = "works" if re.search(r"construction|_work|elevator|overseas", doc_id) else "services" if re.search(r"service|is_|sw_|security|freight|engineering|design", doc_id) else "goods"
    f = BlockFiller(blocks, values(doc_id, kind))
    (fill_pps_lease if doc_id.startswith("pps_stockpile_lease") else fill_ftc)(f)
    render_lines_to_pdf(blocks_to_lines(blocks), str(out_pdf))
    labels = {}
    with fitz.open(out_pdf) as doc:
        for field, value, full, part in f.golds:
            for page in doc:
                if (r := find(page, full, sub=part)) is not None:
                    labels[field] = label(value, page, r, part)
                    break
            else:
                raise AssertionError((doc_id, field, full))
    return labels


# ---------- scan variants ----------


def make_scan(doc_id: str, native_pdf: Path, labels: dict, out_pdf: Path) -> dict:
    rng = random.Random(doc_id + "-scan")
    angle = rng.choice([-1, 1]) * rng.uniform(1.0, 3.0)
    out = fitz.open()
    mats = {}
    with fitz.open(native_pdf) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w).copy()
            m = cv2.getRotationMatrix2D((pix.w / 2, pix.h / 2), angle, 1.0)
            img = cv2.warpAffine(img, m, (pix.w, pix.h), flags=cv2.INTER_LINEAR, borderValue=255)
            noise = np.random.default_rng(rng.randint(0, 2**31)).normal(0, 9, img.shape)
            img = np.clip(cv2.GaussianBlur(img, (3, 3), 0.6) + noise, 0, 255).astype(np.uint8)
            ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            assert ok
            p = out.new_page(width=page.rect.width, height=page.rect.height)
            p.insert_image(p.rect, stream=jpg.tobytes())
            mats[page.number + 1] = (m, pix.w, pix.h)
    out.save(out_pdf, garbage=4, deflate=True)
    out.close()
    scan_labels = {}
    for field, lab in labels.items():
        if lab is None:
            scan_labels[field] = None
            continue
        m, w, h = mats[lab["page"]]
        x0, y0, x1, y1 = lab["bbox"]
        pts = np.array([[x0 * w, y0 * h, 1], [x1 * w, y0 * h, 1], [x0 * w, y1 * h, 1], [x1 * w, y1 * h, 1]]) @ m.T
        bbox = [pts[:, 0].min() / w, pts[:, 1].min() / h, pts[:, 0].max() / w, pts[:, 1].max() / h]
        scan_labels[field] = {**lab, "bbox": [round(min(1.0, max(0.0, b)), 5) for b in bbox]}
    return scan_labels


# ---------- main ----------


def write_gold(doc_id: str, source_type: str, source: Path, labels: dict) -> None:
    gold = {
        "doc_id": doc_id,
        "source_type": source_type,
        "source": str(source.relative_to(ROOT)),
        "labels": {k: labels.get(k) for k in FIELDS},
    }
    (OUT / f"{doc_id}.json").write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    for src in sorted((SAMPLES / "law").glob("*.pdf")):
        doc_id = src.stem
        out_pdf = OUT / f"{doc_id}.pdf"
        with fitz.open(src) as doc:
            labels = fill_law(doc_id, doc[0])  # every law form keeps its fields on page 1
            doc.subset_fonts()
            doc.save(out_pdf, garbage=3, deflate=True)
        write_gold(doc_id, "native", src, labels)
        scan_labels = make_scan(doc_id, out_pdf, {k: labels.get(k) for k in FIELDS}, OUT / f"{doc_id}_scan.pdf")
        write_gold(f"{doc_id}_scan", "scan", src, scan_labels)
        print(doc_id, sorted(labels))
    for src in sorted((SAMPLES / "ftc").glob("*.hwp")) + [SAMPLES / "pps" / "pps_stockpile_lease_2004.hwp"]:
        doc_id = src.stem
        labels = fill_hwp(doc_id, src, OUT / f"{doc_id}.pdf")
        write_gold(doc_id, "native", src, labels)
        print(doc_id, sorted(labels))


if __name__ == "__main__":
    main()
