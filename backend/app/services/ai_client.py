"""AI·Document 파트와의 호출 계약. 4주차에는 인터페이스만 고정하고,
실제 구현은 AI 파트가 6주차 이후 채운다. 자세한 내용은 docs/04_ai_integration.md 참고.
"""

from typing import Any, TypedDict


class NormalizedDocument(TypedDict):
    normalized_pdf_path: str
    page_count: int


class OcrBlockDict(TypedDict):
    page_no: int
    block_id: str
    text: str
    bbox: list[float]
    block_type: str
    confidence: float


class OcrResult(TypedDict):
    doc_id: str
    blocks: list[OcrBlockDict]


class ContractExtractionResult(TypedDict):
    fields: dict[str, Any]


class RiskFlagDict(TypedDict):
    category: str
    level: str
    description: str
    evidence: dict | None


class ChatAnswer(TypedDict):
    content: str
    evidence: list[dict]


def normalize_to_pdf(file_path: str, source_format: str) -> NormalizedDocument:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def run_ocr(pdf_path: str) -> OcrResult:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def extract_contract_fields(ocr_result: OcrResult) -> ContractExtractionResult:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def detect_risks(ocr_result: OcrResult, extraction: ContractExtractionResult) -> list[RiskFlagDict]:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def build_regulation_index(pdf_path: str) -> None:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def answer_question(query: str, session_id: str) -> ChatAnswer:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")
