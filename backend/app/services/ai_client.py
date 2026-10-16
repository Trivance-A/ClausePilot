"""AI·Document 파트 인터페이스 (docs/04_ai_integration.md). Backend는 이 모듈의 함수 시그니처에만 의존한다.

계약서 파이프라인(정규화·OCR·LLM 추출·bbox 역매핑·위험탐지)은 `ai/` 패키지(AI·Document 담당)에 구현되어 있고
여기서는 위임만 한다. LLM은 OpenAI 호환 엔드포인트 하나로 추상화되어 LLM_BASE_URL만으로 vLLM/Ollama/API를 전환한다.
- LLM_BASE_URL 미설정(오프라인·CI): 항목 추출은 아래 규칙 기반(_extract_rule_based)으로, 위험탐지의 LLM 룰
  (독소·모순·규정위배)은 DB risk_rules의 keyword 룰로 대체한다. 룰 엔진(지체상금율·필수조항·금액/일자 모순)은 항상 실행.
- 규정 RAG(구조 파싱·청킹·검색·답변)는 Frontend·RAG 파트 범위로 기존 구현을 유지한다.
"""

import math
import re
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Callable, MutableMapping
from typing import Any, NotRequired, TypedDict

from rank_bm25 import BM25Okapi

from ai import extract as ai_extract
from ai import ocr as ai_ocr
from ai import parser as ai_parser
from ai import risk as ai_risk
from ai.llm import LLMClient, LLMUnavailableError
from ai.ocr import OcrUnavailableError
from ai.types import (
    FIELD_CODES,
    FIELD_LABELS,
    ExtractionFieldDict,
    HighlightDict,
    NormalizedDocument,
    OcrLineDict,
    PageMetaDict,
    RiskFindingDict,
)

__all__ = ["FIELD_CODES", "FIELD_LABELS", "LLMUnavailableError", "OcrUnavailableError", "PageMetaDict"]

RISK_CATEGORIES = ["penalty", "missing", "contradiction", "toxic", "policy"]

UnsupportedFormatError = ai_parser.UnsupportedFormatError


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


# ==================== 1. 문서 파싱 / 2. OCR ====================


def normalize_to_pdf(input_path: str, source_format: str, output_path: str) -> NormalizedDocument:
    return ai_parser.normalize_to_pdf(input_path, source_format, output_path)


def run_ocr(pdf_path: str, engine: str | None = None) -> list[OcrLineDict]:
    """native 페이지는 텍스트 레이어, scan 페이지는 OCR 엔진(engine: auto|paddle_vl|paddle|tesseract)."""
    return ai_ocr.run_ocr(pdf_path, engine)


# ==================== 3. 정보추출 ====================

_AMOUNT_RE = re.compile(r"[\d][\d,]{2,}")
_BIZ_NO_RE = re.compile(r"\d{3}-\d{2}-\d{5}")
_DATE_ISO_RE = re.compile(r"(\d{4})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})")  # 2026-10-01 / 2026.10.01 / 2026. 10. 01.
_DATE_KOR_RE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    )
}
_DATE_EN_RE = re.compile(r"(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})")

FIELD_KEYWORDS: dict[str, list[str]] = {
    "contract_name": ["계약건명", "공사명", "사업명", "용역명", "건명", "project name", "contract name"],
    "contract_amount": ["계약금액", "contract amount"],
    "guarantee_amount": ["계약보증금액", "보증금해당액", "보증금액", "계약보증금", "guarantee amount", "contract guarantee amount"],
    "contract_date": ["계약일자", "계약체결일", "contract date"],
    "performance_due_date": ["계약이행기일", "준공기한", "완료기한", "completion due date", "due date"],
    "guarantee_period": ["계약보증기간", "보증기간", "guarantee period"],
    "creditor_name": ["채권자", "발주자", "client", "creditor"],
    "creditor_biz_no": ["사업자등록번호", "사업자번호", "business registration"],
}


_WS_RE = re.compile(r"\s+")


def _squash(text: str) -> str:
    """공백 제거 + 소문자. 한글 서식 문서는 '계 약  금 액'처럼 라벨을 띄어 쓰는 경우가 많아 공백 무시 비교."""
    return _WS_RE.sub("", text).lower()


def _find_lines(lines: list[OcrLineDict], keywords: list[str]) -> list[OcrLineDict]:
    squashed_kws = [_squash(kw) for kw in keywords]
    return [line for line in lines if any(kw in _squash(line["text"]) for kw in squashed_kws)]


def _find_line(lines: list[OcrLineDict], keywords: list[str]) -> OcrLineDict | None:
    found = _find_lines(lines, keywords)
    return found[0] if found else None


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


def _has_value(field: ExtractionFieldDict) -> bool:
    return field["normalized_value"] is not None


def _apply_fallbacks(ocr_lines: list[OcrLineDict], results: list[ExtractionFieldDict]) -> None:
    """라벨 없는 서식(지급각서 등) 대응: 날짜만 있는 줄 → 계약일자, '... 귀하' 줄 → 채권자명 (낮은 confidence)."""
    by_code = {f["field_code"]: f for f in results}
    if not by_code["contract_date"]["raw_value"]:
        for line in ocr_lines:
            t = line["text"].strip()
            if (_DATE_KOR_RE.fullmatch(t) or _DATE_ISO_RE.fullmatch(t.rstrip("."))) and (date := _parse_date(t)):
                by_code["contract_date"].update(
                    {"raw_value": t, "normalized_value": {"date": date}, "confidence": 0.5, "mapping_method": "fuzzy", "highlights": [_highlight_for(line)]}
                )
                break
    if not by_code["creditor_name"]["raw_value"]:
        for line in ocr_lines:
            t = line["text"].strip()
            if t.endswith("귀하") and len(t) > 2:
                by_code["creditor_name"].update(
                    {"raw_value": t, "normalized_value": {"text": t[:-2].strip()}, "confidence": 0.6, "mapping_method": "fuzzy", "highlights": [_highlight_for(line)]}
                )
                break


RULE_BASED_VERSION = "rule-based-v1"
LLMCache = MutableMapping[str, Any]


class ExtractionMetaDict(TypedDict):
    """extractions 행 메타 (03_데이터정의 §5.5)."""

    model_name: str
    prompt_version: str
    raw_llm_output: dict | None


def extraction_model_name() -> str:
    llm = LLMClient.from_env()
    return f"{llm.model}@{ai_extract.PROMPT_VERSION}" if llm else RULE_BASED_VERSION


def extract_contract_fields_with_meta(
    ocr_lines: list[OcrLineDict], llm_cache: LLMCache | None = None
) -> tuple[list[ExtractionFieldDict], ExtractionMetaDict]:
    """LLM 구조화 추출 + bbox 4단 역매핑 + 정규화, 그리고 extractions 행 메타(model_name·prompt_version·raw_llm_output).
    LLM 미설정이면 규칙 기반 대체. llm_cache는 llm_cache 테이블 매핑(app/services/llm_cache.py)."""
    llm = LLMClient.from_env(cache=llm_cache)
    if llm is None:
        return _extract_rule_based(ocr_lines), {"model_name": RULE_BASED_VERSION, "prompt_version": RULE_BASED_VERSION, "raw_llm_output": None}
    fields, meta = ai_extract.extract_fields(ocr_lines, llm)
    return fields, {"model_name": meta["model_name"], "prompt_version": meta["prompt_version"], "raw_llm_output": meta["raw_llm_output"]}


def extract_contract_fields(ocr_lines: list[OcrLineDict]) -> list[ExtractionFieldDict]:
    return extract_contract_fields_with_meta(ocr_lines)[0]


def _extract_rule_based(ocr_lines: list[OcrLineDict]) -> list[ExtractionFieldDict]:
    results: list[ExtractionFieldDict] = []
    for code in FIELD_CODES:
        candidates = _find_lines(ocr_lines, FIELD_KEYWORDS[code])
        if not candidates:
            results.append(_empty_field(code))
            continue
        # 키워드가 여러 줄에 걸리면(예: 제목 '계약보증금 지급각서' vs '보증금해당액 : 금1,600,000원') 값이 파싱되는 줄 우선
        parsed = [_extract_one(ocr_lines, code, line) for line in candidates]
        results.append(next((f for f in parsed if _has_value(f)), parsed[0]))
    _apply_fallbacks(ocr_lines, results)
    return results


def _extract_one(ocr_lines: list[OcrLineDict], code: str, line: OcrLineDict) -> ExtractionFieldDict:
    if True:
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

        return field


# ==================== 4. 위험조항 탐지 ====================

_PENALTY_PERMILLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*1000")
_PENALTY_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_PENALTY_RATE_STANDARD = 0.1  # 표준계약서 기준 지체상금율(%/일), 1.0(=기준의 3배)에서 score=1.0이 되도록 정규화
_PENALTY_RATE_FULL_SCORE = 0.3


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
    rule_type: str  # field_missing | keyword | penalty_rate | period_contradiction | doc
    title: str
    description: str
    keywords: list[str] | None
    field_code: str | None
    base_score: float | None
    engine: NotRequired[str | None]  # rule | llm: 03_데이터정의 §6.1 문서형 룰. None = 기존(오프라인 keyword) 행
    params: NotRequired[dict | None]
    default_severity: NotRequired[str | None]


def doc_risk_rules() -> list[dict]:
    """ai/risk/rules.yaml(03_데이터정의 §6.1)을 risk_rules 행 형태로. app/core/seed.py가 시드한다."""
    return [
        {
            "rule_code": r["code"],
            "category": r["category"],
            "rule_type": "doc",
            "title": r["name"],
            "description": r["name"],
            "engine": r["engine"],
            "params": r.get("params") or {},
            "default_severity": r.get("default_severity"),
            "enabled": r.get("is_active", True),
        }
        for r in ai_risk.load_rules()
    ]


def detect_risks(
    ocr_lines: list[OcrLineDict],
    fields: list[ExtractionFieldDict],
    rules: list[RiskRuleDict],
    policy_search: Callable[[str], list[dict]] | None = None,
    llm_cache: LLMCache | None = None,
) -> list[RiskFindingDict]:
    """룰 엔진(PENALTY_RATE_HIGH·MISSING_ARTICLE·AMOUNT_MISMATCH·DATE_INCONSISTENT) + LLM 엔진(TOXIC_CLAUSE·
    CONTRADICTION_LLM·POLICY_VIOLATION) 병렬. policy_search(query)->규정 청크 목록은 Backend가 RAG 검색으로 주입.
    rules 중 engine이 채워진 행(DB risk_rules의 문서형 룰, 활성 행만 전달됨)을 YAML 형태로 바꿔 ai.risk에 넘긴다."""
    llm = LLMClient.from_env(cache=llm_cache)
    doc_rules = [
        {
            "code": r["rule_code"],
            "name": r["title"],
            "category": r["category"],
            "engine": r["engine"],
            "params": r.get("params") or {},
            "default_severity": r.get("default_severity"),
            "is_active": True,
        }
        for r in rules
        if r.get("engine")
    ]
    findings = ai_risk.detect_risks(ocr_lines, fields, rules=doc_rules, llm=llm, policy_search=policy_search)
    if llm is None:  # 오프라인: keyword 룰이 LLM 룰(독소·규정위배)을 대신한다
        findings += _detect_risks_keyword(ocr_lines, fields, [r for r in rules if r["rule_type"] == "keyword"])
    return findings


def _detect_risks_keyword(ocr_lines: list[OcrLineDict], fields: list[ExtractionFieldDict], rules: list[RiskRuleDict]) -> list[RiskFindingDict]:
    findings: list[RiskFindingDict] = []
    by_code = {f["field_code"]: f for f in fields}

    for rule in rules:
        if rule["rule_type"] == "field_missing":
            if not by_code.get(rule["field_code"], {}).get("raw_value"):
                score = rule["base_score"]
                findings.append(
                    {
                        "category": rule["category"],
                        "severity": ai_risk.severity_of(score),
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
                        "severity": ai_risk.severity_of(score),
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
                        "severity": ai_risk.severity_of(score),
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
