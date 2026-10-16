"""Shared data contracts of the contract pipeline (03_데이터정의 §3, §5.3~5.9).

bbox is always [x0, y0, x1, y1], top-left origin, rotation applied, normalized 0~1 by page size.
Keys mirror the backend models 1:1 (the backend does `Model(**dict)`), so do not add keys casually.
"""

from typing import TypedDict

FIELD_CODES = [
    "contract_name",
    "contract_amount",
    "guarantee_amount",
    "contract_date",
    "performance_due_date",
    "guarantee_period",
    "creditor_name",
    "creditor_biz_no",
]

FIELD_LABELS = {
    "contract_name": "계약건명",
    "contract_amount": "계약금액",
    "guarantee_amount": "보증금액",
    "contract_date": "계약일자",
    "performance_due_date": "계약이행기일",
    "guarantee_period": "보증기간",
    "creditor_name": "채권자명",
    "creditor_biz_no": "채권자 사업자번호",
}

FIELD_COLORS = {
    "contract_name": "#2F80ED",
    "contract_amount": "#27AE60",
    "guarantee_amount": "#16A085",
    "contract_date": "#F2994A",
    "performance_due_date": "#EB5757",
    "guarantee_period": "#9B51E0",
    "creditor_name": "#56CCF2",
    "creditor_biz_no": "#BDBDBD",
}


class PageMetaDict(TypedDict):
    page_no: int
    width_pt: float
    height_pt: float
    rotation: int
    has_text_layer: bool


class NormalizedDocument(TypedDict):
    normalized_pdf_path: str
    pages: list[PageMetaDict]
    source_type: str  # native | scan | mixed (router verdict, FR-02)
    parsed_text_path: str | None  # parsed_text.json from the native format parser, if any


class OcrLineDict(TypedDict):
    page_no: int
    line_id: str  # L{page}-{line}
    text: str
    bbox: list[float]
    confidence: float
    source: str  # pdf_text | paddle | tesseract
    table_cell: str | None  # "r{row},c{col}"


class HighlightDict(TypedDict):
    page_no: int
    bbox: list[float]
    ocr_line_id: str | None


class ExtractionFieldDict(TypedDict):
    field_code: str
    raw_value: str | None
    normalized_value: dict | None
    confidence: float
    mapping_method: str  # llm_ref | exact | fuzzy | manual | none
    highlights: list[HighlightDict]


class RiskFindingDict(TypedDict):
    category: str  # penalty | missing | contradiction | toxic | policy
    severity: str  # HIGH | MEDIUM | LOW
    score: float
    rule_code: str | None
    title: str
    description: str
    evidence_text: str | None
    highlights: list[HighlightDict]
    llm_reasoning: dict | None
