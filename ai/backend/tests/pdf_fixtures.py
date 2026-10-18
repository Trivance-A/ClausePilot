"""테스트용 PDF 생성 헬퍼. PyMuPDF 기본 폰트(Helvetica)는 한글을 렌더링하지 못하므로
내장 CJK 폰트("korea-s")를 명시해야 한다 — 안 그러면 텍스트 레이어가 전부 tofu(·)로 깨진다."""

import io

import pymupdf as fitz

CONTRACT_LINES = [
    "CONSTRUCTION CONTRACT AGREEMENT",
    "1. Project Name : Smoke Test Road Works",
    "2. Contract Amount : KRW 350,000,000",
    "3. Contract Date : March 5, 2026",
    "4. Completion Due Date : December 31, 2026",
    "5. Contract Guarantee Amount : KRW 35,000,000",
    "6. Guarantee Period : 2026-03-05 ~ 2027-03-04",
    "7. Client (Creditor) : Test Public Corporation",
    "Business Registration No. : 123-45-67890",
    "Article 8 (Liquidated Damages) The Contractor shall pay liquidated damages of 3/1000",
    "of the contract amount for each day of delay.",
    "Article 15 (Termination) The Client may terminate this Contract at its sole discretion",
    "without prior notice.",
]

REGULATION_LINES = [
    "제1장 총칙",
    "제1조(목적) 이 규정은 조합의 계약 사무 처리에 관한 기본 사항을 정함을 목적으로 한다.",
    "제3장 계약의 체결",
    "제12조(계약보증금)",
    "① 계약담당자는 계약을 체결하고자 할 때에는 계약보증금을 납부하게 하여야 한다.",
    "② 계약보증금은 계약금액의 100분의 10 이상으로 한다.",
    "제13조(보증금 면제)",
    "① 국가기관과 계약하는 경우에는 계약보증금의 전부 또는 일부를 면제할 수 있다.",
]


def _build_pdf(lines: list[str], *, fontname: str = "helv") -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 60
    for line in lines:
        page.insert_text((50, y), line, fontsize=11, fontname=fontname)
        y += 25
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def contract_pdf_bytes() -> bytes:
    return _build_pdf(CONTRACT_LINES)


def regulation_pdf_bytes() -> bytes:
    return _build_pdf(REGULATION_LINES, fontname="korea-s")
