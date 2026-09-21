"""AI·Document 파트 인터페이스의 결정적(deterministic) 초기 구현.

실제 OCR 엔진/LLM API 키가 아직 없는 상태에서도 end-to-end로 동작하는 시스템을 만들기 위해,
아래 함수들은 규칙 기반(regex/키워드 매칭) 로직으로 구현되어 있다. AI 파트가 나중에 실제
OCR/LLM/임베딩 모델을 붙일 때는 이 파일의 함수 시그니처만 유지한 채 내부 구현을 교체하면 된다
(Backend/API 계층은 이 인터페이스에만 의존하고 DB에 직접 접근하지 않는다 — docs/01_architecture.md 3절).

한계(의도적 범위 축소, docs/04_ai_integration.md 참고):
- normalize_to_pdf: 텍스트 레이어가 있는 PDF만 지원(hwp/hwpx/xlsx 실변환 미구현)
- run_ocr: 텍스트 레이어 기반 추출만 지원(스캔 이미지의 실제 OCR 엔진 미연동)
- hybrid_search: 외부 Vector DB 대신 질의 시점 BM25 + TF-IDF 코사인 유사도로 대체
- generate_answer_stream: 실제 LLM 대신 검색된 조항을 그대로 인용하는 추출형(extractive) 응답
"""

import math
import re
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from typing import Any, TypedDict

import pymupdf as fitz
from rank_bm25 import BM25Okapi

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


class UnsupportedFormatError(Exception):
    """normalize_to_pdf가 아직 지원하지 않는 포맷을 만났을 때 발생. 파이프라인이 documents.status=FAILED로 처리."""


# ---- TypedDict 정의 (docs/04_ai_integration.md 1절과 대응) ----


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
    line_id: str
    text: str
    bbox: list[float]
    confidence: float
    source: str
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
    mapping_method: str
    highlights: list[HighlightDict]


class RiskFindingDict(TypedDict):
    category: str
    severity: str
    score: float
    rule_code: str | None
    title: str
    description: str
    evidence_text: str | None
    highlights: list[HighlightDict]
    llm_reasoning: dict | None


class RegulationNodeDict(TypedDict):
    level: str
    number: str
    title: str | None
    path: str
    page_no: int | None
    bbox: list[float] | None
    content: str
    children: list["RegulationNodeDict"]


class RegulationChunkDict(TypedDict):
    node_path: str
    content: str


class SearchCandidate(TypedDict):
    """Backend가 DB에서 조회해 hybrid_search에 넘기는 검색 후보 (AI 모듈은 DB에 직접 접근하지 않는다)."""

    chunk_id: str
    regulation_id: str
    regulation_title: str
    path: str
    content: str
    node_id: str | None
    page_no: int | None
    bbox: list[float] | None


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


# ==================== 1. 문서 파싱 ====================


def normalize_to_pdf(file_path: str, source_format: str) -> NormalizedDocument:
    if source_format != "pdf":
        raise UnsupportedFormatError(f"'{source_format}' 포맷은 아직 지원하지 않습니다 (PDF만 정규화 가능)")
    doc = fitz.open(file_path)
    try:
        pages: list[PageMetaDict] = []
        for page in doc:
            rect = page.rect
            has_text = bool(page.get_text("text").strip())
            pages.append(
                {
                    "page_no": page.number + 1,
                    "width_pt": rect.width,
                    "height_pt": rect.height,
                    "rotation": page.rotation,
                    "has_text_layer": has_text,
                }
            )
        return {"normalized_pdf_path": file_path, "pages": pages}
    finally:
        doc.close()


# ==================== 2. OCR / Layout ====================


def run_ocr(pdf_path: str) -> list[OcrLineDict]:
    doc = fitz.open(pdf_path)
    try:
        lines: list[OcrLineDict] = []
        for page in doc:
            page_no = page.number + 1
            width, height = page.rect.width, page.rect.height
            if width <= 0 or height <= 0:
                continue
            blocks = [b for b in page.get_text("blocks") if b[4].strip()]
            blocks.sort(key=lambda b: (round(b[1], 1), b[0]))
            for i, (x0, y0, x1, y1, text, *_rest) in enumerate(blocks, start=1):
                lines.append(
                    {
                        "page_no": page_no,
                        "line_id": f"L{page_no}-{i}",
                        "text": text.strip(),
                        "bbox": [x0 / width, y0 / height, x1 / width, y1 / height],
                        "confidence": 1.0,  # 텍스트 레이어 직접 추출이라 OCR 신뢰도 개념 없음(항상 1.0)
                        "source": "pdf_text",
                        "table_cell": None,
                    }
                )
        return lines
    finally:
        doc.close()


# ==================== 3. 정보추출 ====================

_AMOUNT_RE = re.compile(r"[\d][\d,]{2,}")
_BIZ_NO_RE = re.compile(r"\d{3}-\d{2}-\d{5}")
_DATE_ISO_RE = re.compile(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})")
_DATE_KOR_RE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    )
}
_DATE_EN_RE = re.compile(r"(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})")

FIELD_KEYWORDS: dict[str, list[str]] = {
    "contract_name": ["계약건명", "공사명", "사업명", "project name", "contract name"],
    "contract_amount": ["계약금액", "contract amount"],
    "guarantee_amount": ["계약보증금액", "보증금액", "guarantee amount", "contract guarantee amount"],
    "contract_date": ["계약일자", "계약체결일", "contract date"],
    "performance_due_date": ["계약이행기일", "준공기한", "완료기한", "completion due date", "due date"],
    "guarantee_period": ["보증기간", "guarantee period"],
    "creditor_name": ["채권자", "발주자", "client", "creditor"],
    "creditor_biz_no": ["사업자등록번호", "사업자번호", "business registration"],
}


def _find_line(lines: list[OcrLineDict], keywords: list[str]) -> OcrLineDict | None:
    for line in lines:
        lower = line["text"].lower()
        if any(kw.lower() in lower for kw in keywords):
            return line
    return None


def _parse_date(text: str) -> str | None:
    if m := _DATE_ISO_RE.search(text):
        y, mo, d = (int(g) for g in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    if m := _DATE_KOR_RE.search(text):
        y, mo, d = (int(g) for g in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    if m := _DATE_EN_RE.search(text):
        mo, d, y = _MONTHS[m.group(1)], int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def _empty_field(field_code: str) -> ExtractionFieldDict:
    return {
        "field_code": field_code,
        "raw_value": None,
        "normalized_value": None,
        "confidence": 0.0,
        "mapping_method": "none",
        "highlights": [],
    }


def _highlight_for(line: OcrLineDict) -> HighlightDict:
    return {"page_no": line["page_no"], "bbox": line["bbox"], "ocr_line_id": line["line_id"]}


def extract_contract_fields(ocr_lines: list[OcrLineDict]) -> list[ExtractionFieldDict]:
    results: list[ExtractionFieldDict] = []
    for code in FIELD_CODES:
        line = _find_line(ocr_lines, FIELD_KEYWORDS[code])
        if not line:
            results.append(_empty_field(code))
            continue

        text = line["text"]
        field: ExtractionFieldDict = {
            "field_code": code,
            "raw_value": text,
            "normalized_value": None,
            "confidence": 0.9,
            "mapping_method": "exact",
            "highlights": [_highlight_for(line)],
        }

        if code in ("contract_amount", "guarantee_amount"):
            if m := _AMOUNT_RE.search(text):
                field["normalized_value"] = {"amount": int(m.group(0).replace(",", ""))}
            else:
                field["mapping_method"] = "fuzzy"
                field["confidence"] = 0.4
        elif code in ("contract_date", "performance_due_date"):
            if date := _parse_date(text):
                field["normalized_value"] = {"date": date}
            else:
                field["mapping_method"] = "fuzzy"
                field["confidence"] = 0.4
        elif code == "guarantee_period":
            dates = _DATE_ISO_RE.findall(text) or _DATE_KOR_RE.findall(text)
            parsed = [f"{int(y):04d}-{int(mo):02d}-{int(d):02d}" for y, mo, d in dates]
            if len(parsed) >= 2:
                field["normalized_value"] = {"start": parsed[0], "end": parsed[1]}
            else:
                field["mapping_method"] = "fuzzy"
                field["confidence"] = 0.4
        elif code == "creditor_biz_no":
            if m := _BIZ_NO_RE.search(text):
                field["normalized_value"] = {"text": m.group(0)}
            else:
                # 라벨 줄 자체엔 번호가 없는 경우(예: "(see attachment)") 문서 전체에서 재탐색
                found = next((ol for ol in ocr_lines if _BIZ_NO_RE.search(ol["text"])), None)
                if found:
                    m = _BIZ_NO_RE.search(found["text"])
                    field = {
                        "field_code": code,
                        "raw_value": found["text"],
                        "normalized_value": {"text": m.group(0)},
                        "confidence": 0.6,
                        "mapping_method": "fuzzy",
                        "highlights": [_highlight_for(found)],
                    }
                else:
                    field = _empty_field(code)
        else:  # contract_name, creditor_name: 콜론/구분자 뒤 텍스트를 값으로
            value = re.split(r"[:：]", text, maxsplit=1)
            field["normalized_value"] = {"text": value[1].strip() if len(value) > 1 else text}

        results.append(field)
    return results


# ==================== 4. 위험조항 탐지 ====================

FIELD_LABELS: dict[str, str] = {
    "contract_name": "계약건명",
    "contract_amount": "계약금액",
    "guarantee_amount": "보증금액",
    "contract_date": "계약일자",
    "performance_due_date": "계약이행기일",
    "guarantee_period": "보증기간",
    "creditor_name": "채권자명",
    "creditor_biz_no": "채권자 사업자번호",
}
_ESSENTIAL_FIELDS = ["contract_name", "contract_amount", "contract_date", "creditor_name"]

_PENALTY_PERMILLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*1000")
_PENALTY_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_PENALTY_KEYWORDS = ["지체상금", "위약금", "liquidated damages"]
_TOXIC_KEYWORDS = ["일방적", "단독으로 해지", "sole discretion", "without prior notice"]
_EXEMPTION_KEYWORDS = ["면책", "책임지지 않는다", "no liability"]


def detect_risks(ocr_lines: list[OcrLineDict], fields: list[ExtractionFieldDict]) -> list[RiskFindingDict]:
    findings: list[RiskFindingDict] = []
    by_code = {f["field_code"]: f for f in fields}

    for code in _ESSENTIAL_FIELDS:
        if not by_code.get(code, {}).get("raw_value"):
            findings.append(
                {
                    "category": "missing",
                    "severity": "MEDIUM",
                    "score": 0.5,
                    "rule_code": f"MISSING_FIELD_{code.upper()}",
                    "title": f"필수항목 누락: {FIELD_LABELS[code]}",
                    "description": f"{FIELD_LABELS[code]} 항목을 문서에서 찾지 못했습니다.",
                    "evidence_text": None,
                    "highlights": [],
                    "llm_reasoning": None,
                }
            )

    for line in ocr_lines:
        lower = line["text"].lower()

        if any(kw in lower for kw in _PENALTY_KEYWORDS):
            rate = None
            if m := _PENALTY_PERMILLE_RE.search(line["text"]):
                rate = float(m.group(1)) / 1000 * 100
            elif m := _PENALTY_PERCENT_RE.search(line["text"]):
                rate = float(m.group(1))
            if rate is not None:
                severity = "HIGH" if rate >= 0.3 else "MEDIUM" if rate > 0.1 else None
                if severity:
                    findings.append(
                        {
                            "category": "penalty",
                            "severity": severity,
                            "score": min(rate / 0.3, 1.0),
                            "rule_code": "PENALTY_RATE_HIGH",
                            "title": f"지체상금율 과다 (1일 {rate:g}%)",
                            "description": "표준계약서 기준(0.1%/일) 대비 지체상금율이 높습니다.",
                            "evidence_text": line["text"],
                            "highlights": [_highlight_for(line)],
                            "llm_reasoning": None,
                        }
                    )

        if any(kw in lower for kw in _TOXIC_KEYWORDS):
            findings.append(
                {
                    "category": "toxic",
                    "severity": "MEDIUM",
                    "score": 0.55,
                    "rule_code": None,
                    "title": "일방적 계약해지 조항 의심",
                    "description": "발주자 단독 해지권으로 해석될 수 있는 문구가 발견되었습니다.",
                    "evidence_text": line["text"],
                    "highlights": [_highlight_for(line)],
                    "llm_reasoning": {"matched_text": line["text"]},
                }
            )

        if any(kw in lower for kw in _EXEMPTION_KEYWORDS):
            findings.append(
                {
                    "category": "policy",
                    "severity": "LOW",
                    "score": 0.3,
                    "rule_code": None,
                    "title": "면책조항 확인 필요",
                    "description": "일방적 면책으로 해석될 수 있는 문구가 발견되었습니다. 조건의 타당성을 검토하세요.",
                    "evidence_text": line["text"],
                    "highlights": [_highlight_for(line)],
                    "llm_reasoning": None,
                }
            )

    period_field = by_code.get("guarantee_period")
    if period_field and period_field.get("normalized_value"):
        nv = period_field["normalized_value"]
        start, end = nv.get("start"), nv.get("end")
        if start and end and end < start:
            findings.append(
                {
                    "category": "contradiction",
                    "severity": "HIGH",
                    "score": 0.9,
                    "rule_code": "GUARANTEE_PERIOD_INVERTED",
                    "title": "보증기간 시작일이 종료일보다 늦음",
                    "description": f"보증기간 시작({start})이 종료({end})보다 늦게 기재되어 있습니다.",
                    "evidence_text": period_field.get("raw_value"),
                    "highlights": period_field.get("highlights", []),
                    "llm_reasoning": None,
                }
            )

    return findings


# ==================== 5. 규정 구조 파싱 / 청킹 ====================

_CHAPTER_RE = re.compile(r"^제\s*(\d+)\s*장\s*(.*)$")
_ARTICLE_RE = re.compile(r"^제\s*(\d+)\s*조\s*(?:\(([^)]*)\))?")
_PARA_MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
_PARA_RE = re.compile(r"^([" + _PARA_MARKS + r"])")


def _classify(text: str) -> tuple[str, str, str | None] | None:
    if m := _CHAPTER_RE.match(text):
        return "chapter", m.group(1), m.group(2) or None
    if m := _ARTICLE_RE.match(text):
        return "article", m.group(1), m.group(2)
    if m := _PARA_RE.match(text):
        return "paragraph", str(_PARA_MARKS.index(m.group(1)) + 1), None
    return None


def parse_regulation_structure(pdf_path: str) -> list[RegulationNodeDict]:
    lines = run_ocr(pdf_path)  # 정규화 PDF의 텍스트 레이어를 그대로 구조 파싱 입력으로 재사용

    roots: list[RegulationNodeDict] = []
    chapter: RegulationNodeDict | None = None
    article: RegulationNodeDict | None = None
    current: RegulationNodeDict | None = None

    for line in lines:
        cls = _classify(line["text"])
        if cls is None:
            if current is not None:
                current["content"] = (current["content"] + "\n" + line["text"]).strip()
            continue

        level, number, title = cls
        node: RegulationNodeDict = {
            "level": level,
            "number": number,
            "title": title,
            "path": "",
            "page_no": line["page_no"],
            "bbox": line["bbox"],
            "content": line["text"],
            "children": [],
        }

        if level == "chapter":
            node["path"] = f"제{number}장"
            roots.append(node)
            chapter, article, current = node, None, node
        elif level == "article":
            label = f"제{number}조" + (f"({title})" if title else "")
            node["path"] = f"{chapter['path']}>{label}" if chapter else label
            (chapter["children"] if chapter else roots).append(node)
            article, current = node, node
        else:  # paragraph
            circled = _PARA_MARKS[int(number) - 1]
            node["number"] = circled
            node["path"] = f"{article['path']}>제{number}항" if article else f"제{number}항"
            (article["children"] if article else roots).append(node)
            current = node

    return roots


def _flatten_nodes(nodes: list[RegulationNodeDict]) -> list[RegulationNodeDict]:
    flat: list[RegulationNodeDict] = []
    for n in nodes:
        flat.append(n)
        flat.extend(_flatten_nodes(n["children"]))
    return flat


def chunk_regulation(nodes: list[RegulationNodeDict]) -> list[RegulationChunkDict]:
    """노드마다 독립 청크 1개(article/paragraph 모두 자기 content로 청크화). 상세: docs/04_ai_integration.md."""
    return [{"node_path": n["path"], "content": n["content"]} for n in _flatten_nodes(nodes) if n["content"].strip()]


def index_chunks(chunks: list[RegulationChunkDict]) -> list[str]:
    """실제 Vector DB 대신 질의 시점 계산 방식을 쓰므로(hybrid_search 참고), 참조용 placeholder ID만 발급."""
    return [f"chunk-{i}" for i in range(len(chunks))]


# ==================== 6. 하이브리드 검색 ====================

_TOKEN_RE = re.compile(r"[0-9A-Za-z]+|[가-힣]")  # 영숫자 토큰 또는 한글 음절 1개(형태소 분석기 없이 근사)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _tfidf_vectors(corpus_tokens: list[list[str]]) -> tuple[list[dict[str, float]], dict[str, float]]:
    df: Counter[str] = Counter()
    for tokens in corpus_tokens:
        df.update(set(tokens))
    n_docs = len(corpus_tokens)
    idf = {term: math.log((n_docs + 1) / (freq + 1)) + 1 for term, freq in df.items()}

    vectors: list[dict[str, float]] = []
    for tokens in corpus_tokens:
        tf = Counter(tokens)
        vec = {term: count * idf.get(term, 0.0) for term, count in tf.items()}
        vectors.append(vec)
    return vectors, idf


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def hybrid_search(query: str, candidates: list[SearchCandidate], top_k: int = 5) -> list[SearchResultDict]:
    """BM25(키워드) + TF-IDF 코사인(의미 근사) → RRF 결합 → (실 rerank 모델 미도입, RRF 순위를 그대로 사용).
    candidates는 Backend가 DB에서 조회해 전달한다(이 함수는 DB에 접근하지 않는다)."""
    if not candidates:
        return []

    query_tokens = _tokenize(query)
    corpus_tokens = [_tokenize(c["content"]) for c in candidates]

    bm25 = BM25Okapi(corpus_tokens)
    bm25_scores = list(bm25.get_scores(query_tokens))

    doc_vectors, idf = _tfidf_vectors(corpus_tokens)
    query_tf = Counter(query_tokens)
    query_vec = {t: c * idf.get(t, 0.0) for t, c in query_tf.items()}
    vector_scores = [_cosine(query_vec, v) for v in doc_vectors]

    def _ranks(scores: list[float]) -> dict[int, int]:
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return {idx: rank for rank, idx in enumerate(order, start=1)}

    bm25_ranks = _ranks(bm25_scores)
    vector_ranks = _ranks(vector_scores)
    k = 60  # RRF 상수(관례값)
    rrf_scores = [1 / (k + bm25_ranks[i]) + 1 / (k + vector_ranks[i]) for i in range(len(candidates))]

    results: list[SearchResultDict] = []
    for i, c in enumerate(candidates):
        results.append(
            {
                **c,
                "bm25_score": round(bm25_scores[i], 4),
                "vector_score": round(vector_scores[i], 4),
                "rrf_score": round(rrf_scores[i], 6),
                "rerank_score": round(rrf_scores[i], 6),
            }
        )
    results.sort(key=lambda r: r["rrf_score"], reverse=True)
    return results[:top_k]


# ==================== 7. 챗봇 답변 생성 (SSE) ====================


async def generate_answer_stream(
    query: str, chunks: list[SearchResultDict], message_id: uuid.UUID
) -> AsyncIterator[dict[str, Any]]:
    """검색된 상위 청크를 그대로 인용하는 추출형 응답(실 LLM 미연동). chunks는 비어있지 않다고 가정
    (근거 없을 때 NOT_FOUND 처리는 호출측 app/api/chat.py 책임 — docs/04_ai_integration.md 3절)."""
    top = chunks[:2]
    answer = " ".join(f"{c['content'].strip()} [{i + 1}]" for i, c in enumerate(top))

    for token in re.findall(r"\S+\s*", answer):
        yield {"event": "token", "data": {"text": token}}

    for i, c in enumerate(top, start=1):
        yield {
            "event": "citation",
            "data": {
                "ref": i,
                "chunk_id": c["chunk_id"],
                "regulation_id": c["regulation_id"],
                "regulation_title": c["regulation_title"],
                "path": c["path"],
                "quoted_span": c["content"][:80],
                "page_no": c["page_no"],
                "bbox": c["bbox"],
                "node_id": c["node_id"],
            },
        }

    yield {
        "event": "done",
        "data": {"message_id": str(message_id), "answer_status": "ANSWERED", "latency_ms": 0, "content": answer},
    }
