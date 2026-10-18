"""Synthetic contract fixtures (공개 표준계약서 형식, 가공 데이터 — NFR-09)."""

import pymupdf as fitz

CONTRACT_LINES = [
    "공 사 도 급 계 약 서",
    "1. 공사명 : 한빛시 도로 확장공사",
    "2. 계약금액 : 일금 삼억오천만원정 (₩350,000,000)",
    "3. 계약일자 : 2026년 3월 5일",
    "4. 준공기한 : 2026. 12. 31.",
    "5. 계약보증금 : 금 삼천오백만원정 (₩35,000,000)",
    "6. 보증기간 : 계약일로부터 준공일까지",
    "7. 발주자(갑) : 주식회사 한빛도시공사 (사업자등록번호 214-86-11115)",
    "8. 수급인(을) : 미래건설 주식회사",
    "제3조(계약기간) 계약기간은 착공일로부터 2026년 11월 30일까지로 한다.",
    "제8조(지체상금) 을이 준공기한 내에 공사를 완성하지 못한 때에는 지체일수 1일마다",
    "계약금액의 1000분의 3에 해당하는 지체상금을 갑에게 납부하여야 한다.",
    "제9조(하자담보) 을은 준공 후 2년간 하자보수 책임을 진다.",
    "제10조(계약해지) 갑은 필요하다고 인정할 경우 사전 통보 없이 언제든지 계약을 해지할 수 있으며,",
    "을은 이에 대하여 어떠한 이의나 손해배상도 청구할 수 없다.",
    "제11조(손해배상) 을은 공사와 관련하여 발생한 모든 손해에 대하여 금액의 제한 없이 배상한다.",
]


def contract_pdf(path: str, lines: list[str] = CONTRACT_LINES, rotate: int = 0) -> str:
    """rotate != 0: /Rotate page whose content is drawn so that it *displays* upright (landscape-style pages)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.set_rotation(rotate)
    for i, line in enumerate(lines):
        page.insert_text(fitz.Point(40, 60 + i * 24) * page.derotation_matrix, line, fontsize=10, fontname="korea-s", rotate=rotate)
    doc.save(path)
    doc.close()
    return path
