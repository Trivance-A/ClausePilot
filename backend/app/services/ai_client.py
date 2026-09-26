"""AI·Document 파트 인터페이스의 결정적(deterministic) 초기 구현.

실제 OCR 엔진/LLM API 키가 아직 없는 상태에서도 end-to-end로 동작하는 시스템을 만들기 위해,
아래 함수들은 규칙 기반(regex/키워드 매칭) 로직으로 구현되어 있다. AI 파트가 나중에 실제
OCR/LLM/임베딩 모델을 붙일 때는 이 파일의 함수 시그니처만 유지한 채 내부 구현을 교체하면 된다
(Backend/API 계층은 이 인터페이스에만 의존하고 DB에 직접 접근하지 않는다 — docs/01_architecture.md 3절).

한계(의도적 범위 축소, docs/04_ai_integration.md 참고):
- normalize_to_pdf: pdf/docx/xlsx/hwpx/hwp 지원. 단 hwp/hwpx/docx/xlsx는 원본 레이아웃을 보존하지
  않고 텍스트만 A4 페이지에 순서대로 재배치한다(표는 " | "로 이어붙인 한 줄로 단순화)
- run_ocr: 텍스트 레이어 기반 추출만 지원(스캔 이미지의 실제 OCR 엔진 미연동)
- hybrid_search: 외부 Vector DB 대신 질의 시점 BM25 + TF-IDF 코사인 유사도로 대체
- generate_answer_stream: 실제 LLM 대신 검색된 조항을 그대로 인용하는 추출형(extractive) 응답
"""

import math
import re
import shutil
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
    embedding: list[float] | None


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


_SUPPORTED_FORMATS = {"pdf", "docx", "xlsx", "hwpx", "hwp"}


def _extract_docx_lines(path: str) -> list[str]:
    from docx import Document as DocxDocument

    doc = DocxDocument(path)
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return lines


def _extract_xlsx_lines(path: str) -> list[str]:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)
    lines: list[str] = []
    for ws in wb.worksheets:
        lines.append(f"[{ws.title}]")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None and str(c).strip()]
            if cells:
                lines.append(" | ".join(cells))
    return lines


def _extract_hwpx_lines(path: str) -> list[str]:
    """HWPX(OWPML)는 zip+XML 구조. 네임스페이스에 무관하게 <p> 문단 안의 <t> 텍스트런을 모은다."""
    import zipfile
    from xml.etree import ElementTree as ET

    lines: list[str] = []
    with zipfile.ZipFile(path) as zf:
        section_names = sorted(n for n in zf.namelist() if n.startswith("Contents/section") and n.endswith(".xml"))
        for name in section_names:
            root = ET.fromstring(zf.read(name))
            for elem in root.iter():
                if elem.tag.rsplit("}", 1)[-1] != "p":
                    continue
                text = "".join(t.text or "" for t in elem.iter() if t.tag.rsplit("}", 1)[-1] == "t")
                if text.strip():
                    lines.append(text)
    return lines


def _extract_hwp_lines(path: str) -> list[str]:
    """구형 바이너리 .hwp는 pyhwp(hwp5txt)로 추출한다(OLE+zlib 압축 레코드를 직접 파싱하는 대신
    검증된 오픈소스 파서를 사용). 표/그림은 <표>/<그림> 플레이스홀더로만 나오고 내용은 유실된다."""
    import subprocess

    result = subprocess.run(["hwp5txt", path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise ValueError(f"hwp5txt 실행 실패: {result.stderr.strip() or result.returncode}")
    return [line for line in result.stdout.splitlines() if line.strip() and line.strip() not in ("<표>", "<그림>")]


_EXTRACTORS = {
    "docx": _extract_docx_lines,
    "xlsx": _extract_xlsx_lines,
    "hwpx": _extract_hwpx_lines,
    "hwp": _extract_hwp_lines,
}


def _render_lines_to_pdf(lines: list[str], output_path: str) -> None:
    """추출된 텍스트를 A4 페이지에 순서대로 흘려 넣어 PDF를 만든다. 원본 시각적 레이아웃은
    보존하지 않지만(표는 " | "로 이어붙인 한 줄이 됨), 텍스트 자체는 실제 원문 그대로이므로
    이후 run_ocr/extract_contract_fields가 그대로 동작한다."""
    import textwrap

    # line_height를 font_size의 3배로 넉넉히 둬서 run_ocr의 블록 분리가 원래 줄 단위와 일치하게 한다
    # (간격이 좁으면 PyMuPDF가 인접 줄을 하나의 블록으로 합쳐 필드 추출 시 값이 섞일 수 있음)
    width, height, margin, font_size, line_height = 595, 842, 50, 10, 30
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    y = margin
    for line in lines:
        for wrapped in textwrap.wrap(line, width=72) or [""]:
            if y > height - margin:
                page = doc.new_page(width=width, height=height)
                y = margin
            page.insert_text((margin, y), wrapped, fontsize=font_size, fontname="korea-s")
            y += line_height
    doc.save(output_path)
    doc.close()


def normalize_to_pdf(input_path: str, source_format: str, output_path: str) -> NormalizedDocument:
    if source_format not in _SUPPORTED_FORMATS:
        raise UnsupportedFormatError(f"'{source_format}' 포맷은 아직 지원하지 않습니다")

    if source_format == "pdf":
        shutil.copyfile(input_path, output_path)
    else:
        lines = _EXTRACTORS[source_format](input_path)
        _render_lines_to_pdf(lines, output_path)

    doc = fitz.open(output_path)
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
        return {"normalized_pdf_path": output_path, "pages": pages}
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
_PENALTY_PERMILLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*1000")
_PENALTY_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_PENALTY_RATE_STANDARD = 0.1  # 표준계약서 기준 지체상금율(%/일), 1.0(=기준의 3배)에서 score=1.0이 되도록 정규화
_PENALTY_RATE_FULL_SCORE = 0.3


def _severity_from_score(score: float) -> str:
    """03_API_명세서 설계의 통일 기준: score>=0.75 HIGH, >=0.45 MEDIUM, 그 외 LOW."""
    if score >= 0.75:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM"
    return "LOW"


# 관리자가 DB(risk_rules)에서 조정 가능한 규칙의 기본값. app/core/seed.py가 최초 1회 이 값으로 채운다.
DEFAULT_RISK_RULES: list[dict] = [
    {
        "rule_code": f"MISSING_FIELD_{code.upper()}",
        "category": "missing",
        "rule_type": "field_missing",
        "title": f"필수항목 누락: {FIELD_LABELS[code]}",
        "description": f"{FIELD_LABELS[code]} 항목을 문서에서 찾지 못했습니다.",
        "keywords": None,
        "field_code": code,
        "base_score": 0.5,
    }
    for code in ["contract_name", "contract_amount", "contract_date", "creditor_name"]
] + [
    {
        "rule_code": "PENALTY_RATE_HIGH",
        "category": "penalty",
        "rule_type": "penalty_rate",
        "title": "지체상금율 과다",
        "description": "표준계약서 기준(0.1%/일) 대비 지체상금율이 높습니다.",
        "keywords": ["지체상금", "위약금", "liquidated damages"],
        "field_code": None,
        "base_score": None,
    },
    {
        "rule_code": "TOXIC_TERMINATION",
        "category": "toxic",
        "rule_type": "keyword",
        "title": "일방적 계약해지 조항 의심",
        "description": "발주자 단독 해지권으로 해석될 수 있는 문구가 발견되었습니다.",
        "keywords": ["일방적", "단독으로 해지", "sole discretion", "without prior notice"],
        "field_code": None,
        "base_score": 0.55,
    },
    {
        "rule_code": "POLICY_EXEMPTION",
        "category": "policy",
        "rule_type": "keyword",
        "title": "면책조항 확인 필요",
        "description": "일방적 면책으로 해석될 수 있는 문구가 발견되었습니다. 조건의 타당성을 검토하세요.",
        "keywords": ["면책", "책임지지 않는다", "no liability"],
        "field_code": None,
        "base_score": 0.3,
    },
    {
        "rule_code": "GUARANTEE_PERIOD_INVERTED",
        "category": "contradiction",
        "rule_type": "period_contradiction",
        "title": "보증기간 시작일이 종료일보다 늦음",
        "description": "보증기간 시작일이 종료일보다 늦게 기재되어 있습니다.",
        "keywords": None,
        "field_code": None,
        "base_score": 0.9,
    },
]


class RiskRuleDict(TypedDict):
    rule_code: str
    category: str
    rule_type: str  # field_missing | keyword | penalty_rate | period_contradiction
    title: str
    description: str
    keywords: list[str] | None
    field_code: str | None
    base_score: float | None


def detect_risks(ocr_lines: list[OcrLineDict], fields: list[ExtractionFieldDict], rules: list[RiskRuleDict]) -> list[RiskFindingDict]:
    findings: list[RiskFindingDict] = []
    by_code = {f["field_code"]: f for f in fields}

    for rule in rules:
        if rule["rule_type"] == "field_missing":
            if not by_code.get(rule["field_code"], {}).get("raw_value"):
                score = rule["base_score"]
                findings.append(
                    {
                        "category": rule["category"],
                        "severity": _severity_from_score(score),
                        "score": score,
                        "rule_code": rule["rule_code"],
                        "title": rule["title"],
                        "description": rule["description"],
                        "evidence_text": None,
                        "highlights": [],
                        "llm_reasoning": None,
                    }
                )

        elif rule["rule_type"] == "period_contradiction":
            period_field = by_code.get("guarantee_period")
            nv = (period_field or {}).get("normalized_value") or {}
            start, end = nv.get("start"), nv.get("end")
            if start and end and end < start:
                score = rule["base_score"]
                findings.append(
                    {
                        "category": rule["category"],
                        "severity": _severity_from_score(score),
                        "score": score,
                        "rule_code": rule["rule_code"],
                        "title": rule["title"],
                        "description": f"보증기간 시작({start})이 종료({end})보다 늦게 기재되어 있습니다.",
                        "evidence_text": period_field.get("raw_value"),
                        "highlights": period_field.get("highlights", []),
                        "llm_reasoning": None,
                    }
                )

        elif rule["rule_type"] in ("keyword", "penalty_rate"):
            keywords = rule["keywords"] or []
            for line in ocr_lines:
                lower = line["text"].lower()
                if not any(kw.lower() in lower for kw in keywords):
                    continue

                if rule["rule_type"] == "penalty_rate":
                    rate = None
                    if m := _PENALTY_PERMILLE_RE.search(line["text"]):
                        rate = float(m.group(1)) / 1000 * 100
                    elif m := _PENALTY_PERCENT_RE.search(line["text"]):
                        rate = float(m.group(1))
                    if rate is None:
                        continue
                    score = min(rate / _PENALTY_RATE_FULL_SCORE, 1.0)
                    title = f"{rule['title']} (1일 {rate:g}%, 기준 {_PENALTY_RATE_STANDARD:g}%/일)"
                    reasoning = None
                else:
                    score = rule["base_score"]
                    title = rule["title"]
                    reasoning = {"matched_text": line["text"]}

                findings.append(
                    {
                        "category": rule["category"],
                        "severity": _severity_from_score(score),
                        "score": score,
                        "rule_code": rule["rule_code"],
                        "title": title,
                        "description": rule["description"],
                        "evidence_text": line["text"],
                        "highlights": [_highlight_for(line)],
                        "llm_reasoning": reasoning,
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
    """조(article) 단위로 청킹한다 — 해당 조의 제목 + 하위 항(paragraph 등) 내용을 전부 합쳐 1청크로
    만든다(03_API_명세서: "조 1개 = 1청크가 기본", 800토큰 초과 시 항 단위 분할이지만 학기 프로젝트
    규모 문서는 대부분 그 이내라 단순화). chapter/section 같은 순수 제목 노드는 청크로 만들지 않는다
    — 실측 결과 "제1장 총칙"처럼 내용 없는 짧은 제목이 완전히 무관한 질의와도 우연히 높은 임베딩
    유사도를 보여(예: "오늘 점심 메뉴는?" 0.78) 검색 정확도를 해쳤다."""
    chunks: list[RegulationChunkDict] = []
    for n in _flatten_nodes(nodes):
        if n["level"] != "article":
            continue
        body = "\n".join(part["content"] for part in [n, *_flatten_nodes(n["children"])] if part["content"].strip())
        if body.strip():
            chunks.append({"node_path": n["path"], "content": body})
    return chunks


def index_chunks(chunks: list[RegulationChunkDict]) -> list[list[float]]:
    """각 청크의 임베딩 벡터를 계산해 반환한다(순서는 chunks와 동일). Backend가 이 벡터를
    regulation_chunks.embedding(pgvector) 컬럼에 저장하고, 검색 시점에 hybrid_search로 되돌려준다."""
    return embed_texts([c["content"] for c in chunks])


# ==================== 6. 하이브리드 검색 ====================

EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384  # bge-m3(1024d) 대신 로컬(CPU, API 키 불필요)로 돌아가는 경량 다국어 모델로 대체

# 03_API_명세서의 "리랭커 점수 임계값 τ=0.35(정답셋으로 튜닝)"에 대응. 정답셋이 아직 없어(failures[]
# 참고) 실제 관련/무관 질의 코사인 유사도를 수동으로 측정해 정했다(관련 0.6~0.7 vs 무관 0.02~0.3) —
# 정답셋이 생기면 그걸로 다시 튜닝해야 한다.
RELEVANCE_THRESHOLD = 0.4


def is_relevant(results: list["SearchResultDict"]) -> bool:
    """검색 결과가 챗봇이 답변을 생성할 만큼 관련 있는지 판단(근거 없는 응답 방지의 게이트).
    BM25는 형태소가 하나도 안 겹치면 정확히 0점이라 그대로 신호로 쓰지만, 임베딩 코사인 유사도는
    완전히 무관해도 0에 가깝지 딱 0이 되진 않으므로 RELEVANCE_THRESHOLD 임계값을 둔다."""
    if not results:
        return False
    top = results[0]
    return top["bm25_score"] > 0 or top["vector_score"] >= RELEVANCE_THRESHOLD

_kiwi = None
_embedding_model = None

_CONTENT_TAG_PREFIXES = ("N", "V", "XR", "SL", "SN")  # 체언/용언 어근 + 외국어/숫자(조사·어미·기호 제외)


def _get_kiwi():
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi

        _kiwi = Kiwi()
    return _kiwi


def _tokenize(text: str) -> list[str]:
    """Kiwi 형태소 분석기로 체언/용언 어근만 추출한다(BM25 코퍼스용, 03_API_명세서의 'Kiwi 형태소 기반
    tsvector' 대응). 조사·어미 같은 기능어를 제거해 "계약보증금"과 "계약금액"이 "계약" 형태소를 공유하는 등
    문자 단위 근사(이전 구현)보다 훨씬 정확하게 매칭된다."""
    return [t.form.lower() for t in _get_kiwi().tokenize(text) if t.tag.startswith(_CONTENT_TAG_PREFIXES)]


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from fastembed import TextEmbedding

        _embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL_NAME)
    return _embedding_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """bge-m3 대신 로컬 CPU에서 돌아가는 경량 다국어 임베딩 모델(fastembed, ONNX 런타임 — torch/GPU 불필요).
    최초 호출 시 HuggingFace Hub에서 모델을 1회 내려받는다(이후 캐시 재사용)."""
    if not texts:
        return []
    return [vec.tolist() for vec in _get_embedding_model().embed(texts)]


def _cosine_dense(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def hybrid_search(query: str, candidates: list[SearchCandidate], top_k: int = 5) -> list[SearchResultDict]:
    """BM25(Kiwi 형태소, 키워드) + 임베딩 코사인 유사도(의미) → RRF 결합 → (실 cross-encoder rerank 모델
    미도입, RRF 순위를 그대로 최종 순위로 사용). candidates[i]["embedding"]은 Backend가 pgvector
    컬럼(regulation_chunks.embedding)에서 미리 읽어 전달한다(이 함수는 DB에 접근하지 않는다) —
    없는 후보는 vector_score=0으로 처리한다."""
    if not candidates:
        return []

    query_tokens = _tokenize(query)
    corpus_tokens = [_tokenize(c["content"]) for c in candidates]
    bm25 = BM25Okapi(corpus_tokens)
    bm25_scores = list(bm25.get_scores(query_tokens))

    query_embedding = embed_texts([query])[0]
    vector_scores = [_cosine_dense(query_embedding, c["embedding"]) if c.get("embedding") else 0.0 for c in candidates]

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
                **{key: val for key, val in c.items() if key != "embedding"},
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
