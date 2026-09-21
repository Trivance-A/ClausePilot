"""AI·Document 파트와의 호출 계약. 4주차에는 인터페이스만 고정하고,
실제 구현은 AI 파트가 6주차 이후 채운다. front 폴더의 타입(src/types/api.ts)과
mocks/handlers.ts를 기준으로 필드명을 맞췄다. 상세: docs/04_ai_integration.md 참고.

bbox는 어디서나 [x0, y0, x1, y1] 페이지 폭/높이 기준 0~1 정규화 좌표를 사용한다
(절대 px 좌표를 쓰지 않는다 — 프론트 PdfViewer가 정규화 좌표만 다룸).
"""

from collections.abc import AsyncIterator
from typing import Any, TypedDict

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

RISK_CATEGORIES = ["penalty", "missing", "contradiction", "toxic", "policy"]


class PageMetaDict(TypedDict):
    page_no: int
    width_pt: float
    height_pt: float
    rotation: int
    has_text_layer: bool


class NormalizedDocument(TypedDict):
    normalized_pdf_path: str
    pages: list[PageMetaDict]


class OcrLineDict(TypedDict):
    page_no: int
    line_id: str  # 페이지 내 식별자, 예: "L1-2"
    text: str
    bbox: list[float]
    confidence: float
    source: str  # pdf_text | paddle | tesseract 등
    table_cell: str | None


class HighlightDict(TypedDict):
    page_no: int
    bbox: list[float]
    ocr_line_id: str | None


class ExtractionFieldDict(TypedDict):
    field_code: str
    raw_value: str | None
    normalized_value: dict | None
    confidence: float
    mapping_method: str  # exact | fuzzy | llm_ref | none (manual은 사용자가 직접 부여)
    highlights: list[HighlightDict]


class RiskFindingDict(TypedDict):
    category: str  # RISK_CATEGORIES 중 하나
    severity: str  # HIGH | MEDIUM | LOW
    score: float
    rule_code: str | None
    title: str
    description: str
    evidence_text: str | None
    highlights: list[HighlightDict]
    llm_reasoning: dict | None


class RegulationNodeDict(TypedDict):
    level: str  # chapter|section|article|paragraph|item|subitem|appendix
    number: str
    title: str | None
    path: str
    page_no: int | None
    bbox: list[float] | None
    content: str
    children: list["RegulationNodeDict"]


class RegulationChunkDict(TypedDict):
    node_path: str  # 어느 노드에서 나온 청크인지 (인덱싱 시 node_id로 재매핑)
    content: str


class SearchResultDict(TypedDict):
    chunk_id: str
    regulation_id: str
    regulation_title: str
    path: str
    content: str
    node_id: str | None
    page_no: int | None
    bbox: list[float] | None
    bm25_score: float
    vector_score: float
    rrf_score: float
    rerank_score: float


def normalize_to_pdf(file_path: str, source_format: str) -> NormalizedDocument:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def run_ocr(pdf_path: str) -> list[OcrLineDict]:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def extract_contract_fields(ocr_lines: list[OcrLineDict]) -> list[ExtractionFieldDict]:
    """반환 리스트는 FIELD_CODES 8개를 모두 포함해야 한다 (값을 못 찾은 필드도
    raw_value=None, confidence=0, mapping_method='none', highlights=[] 로 채워 반환)."""
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def detect_risks(ocr_lines: list[OcrLineDict], fields: list[ExtractionFieldDict]) -> list[RiskFindingDict]:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def parse_regulation_structure(pdf_path: str) -> list[RegulationNodeDict]:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def chunk_regulation(nodes: list[RegulationNodeDict]) -> list[RegulationChunkDict]:
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def index_chunks(regulation_id: str, chunks: list[RegulationChunkDict]) -> list[str]:
    """반환값은 각 청크의 embedding_ref(Vector DB 인덱스 참조 ID) 리스트, chunks와 순서 동일."""
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


def hybrid_search(query: str, regulation_ids: list[str] | None, top_k: int = 5) -> list[SearchResultDict]:
    """BM25 키워드 검색 + Vector 유사도 검색 → RRF(Reciprocal Rank Fusion) 결합 → rerank 순으로 처리.
    /search 디버그 엔드포인트가 이 네 단계 점수를 그대로 노출한다."""
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")


async def generate_answer_stream(query: str, chunks: list[SearchResultDict]) -> AsyncIterator[dict[str, Any]]:
    """POST /chat/sessions/{id}/messages (stream=true)의 SSE 본문을 만드는 제너레이터.
    yield하는 각 dict는 {"event": ..., "data": ...} 형태로 app/schemas/chat.py의 Sse*Data와 대응된다.

    이벤트 순서: status(stage=rewrite) → status(stage=retrieve, hits=len(chunks)) →
    (chunks가 있으면) token* → citation*  |  (없으면 토큰 없이) → done.
    근거 청크가 없으면 답변을 생성하지 않고 status=NOT_FOUND로 done만 보낸다
    (근거 없는 응답 5% 이하 목표와 직결되는 분기점)."""
    raise NotImplementedError("AI 파트 구현 대기 (6주차)")
    yield  # pragma: no cover - AsyncIterator 타입을 만족시키기 위한 자리표시자
