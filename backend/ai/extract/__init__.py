"""⑤ LLM structured extraction of the 8 guarantee fields (FR-04) + ⑥ bbox mapping + ⑧ normalization.

Prompt rules (05_OCR_Pipeline §3-⑥): JSON only, schema-enforced; every field has raw_value (verbatim),
evidence_line_ids, confidence; absent -> raw_value null (no guessing); normalization happens afterwards.

Schema notes from Ollama qwen2.5:7b runs (SPEC): `anyOf[null, object]` makes every field null, so each field is
always an object with `raw_value: string|null`; line IDs come back as "[L1-2]" -> pattern + post-cleaning;
the model's confidence is ~always 1, so the stored confidence is derived from mapping/validation instead.
"""

import logging
from typing import Any

from ai.extract.normalize import normalize_fields
from ai.llm import LLMClient
from ai.mapping import map_value
from ai.types import FIELD_CODES, FIELD_LABELS, ExtractionFieldDict, OcrLineDict

logger = logging.getLogger(__name__)

PROMPT_VERSION = "extract-v1"
REQUERY_PROMPT_VERSION = "requery-v1"
MAX_FULL_PAGES = 5
WINDOW = 10
KEYWORDS = ("계약", "금액", "보증", "기일", "기한", "기간", "채권자", "발주", "도급", "사업자", "공사명", "용역명", "건명", "준공", "일자")

FIELD_GUIDE = {
    "contract_name": "계약건명 — 공사명·용역명·물품명·사업명·계약건명",
    "contract_amount": "계약금액 — 총 계약금액 (원문 표기 그대로, 한글·숫자 병기 포함)",
    "guarantee_amount": "보증금액 — 계약보증금·보증금액·보증금 해당액",
    "contract_date": "계약일자 — 계약 체결일",
    "performance_due_date": "계약이행기일 — 준공기한·완료기한·납품기한·이행기간의 종료일",
    "guarantee_period": '보증기간 — 보증 시작~종료 ("계약일로부터 준공일까지" 같은 상대표현도 원문 그대로)',
    "creditor_name": '채권자명 — 보증의 채권자 = 발주자·도급인·발주기관·"갑"',
    "creditor_biz_no": "채권자 사업자등록번호 — 채권자(발주자)의 번호만",
}

SYSTEM = (
    "너는 한국어 계약서에서 보증신청 항목을 추출하는 도구다. 반드시 JSON만 출력한다.\n"
    "규칙:\n"
    "1. 각 항목의 raw_value에는 문서에 적힌 값을 원문 표기 그대로 넣는다(라벨 제외, 정규화·계산 금지).\n"
    "2. evidence_line_ids에는 값이 적힌 라인의 ID(예: L1-17)만 넣는다. 라인 본문은 넣지 않는다.\n"
    "3. 문서에 없거나 빈칸(OO, ○○, 공란)인 항목은 raw_value를 null, evidence_line_ids를 []로 둔다. 추측 금지.\n"
    "4. confidence는 0~1 사이 숫자.\n"
    "항목 설명:\n" + "\n".join(f"- {code}: {desc}" for code, desc in FIELD_GUIDE.items())
)

_FIELD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "raw_value": {"type": ["string", "null"]},
        "evidence_line_ids": {"type": "array", "items": {"type": "string", "pattern": "^L[0-9]+-[0-9]+$"}},
        "confidence": {"type": "number"},
    },
    "required": ["raw_value", "evidence_line_ids", "confidence"],
}
SCHEMA = {
    "type": "object",
    "properties": {code: {"$ref": "#/$defs/field"} for code in FIELD_CODES},
    "required": FIELD_CODES,
    "$defs": {"field": _FIELD_SCHEMA},
}
REQUERY_SCHEMA = {
    "type": "object",
    "properties": {"evidence_line_ids": _FIELD_SCHEMA["properties"]["evidence_line_ids"]},
    "required": ["evidence_line_ids"],
}

_BLANKS = {"", "null", "none", "n/a", "없음", "해당없음", "미기재", "-"}
_METHOD_CONFIDENCE = {"llm_ref": 0.95, "exact": 0.9, "fuzzy": 0.75, "none": 0.3}


def format_lines(lines: list[OcrLineDict]) -> str:
    return "\n".join(f"{ln['line_id']}: " + (f"[표 {ln['table_cell']}] " if ln["table_cell"] else "") + ln["text"] for ln in lines)


def select_lines(lines: list[OcrLineDict]) -> list[OcrLineDict]:
    """All lines for <= 5 pages; otherwise keyword lines +-10 (token budget, 05_OCR_Pipeline §3-⑥)."""
    if len({ln["page_no"] for ln in lines}) <= MAX_FULL_PAGES:
        return lines
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if any(k in line["text"].replace(" ", "") for k in KEYWORDS):
            keep.update(range(max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)))
    return [lines[i] for i in sorted(keep)]


def _raw(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in _BLANKS else text


def _confidence(method: str, score: float, normalized: dict | None) -> float:
    conf = _METHOD_CONFIDENCE[method] * (score / 100 if method == "fuzzy" else 1)
    if normalized is None or normalized.get("checksum_valid") is False:
        conf *= 0.7
    return round(conf, 3)


def extract_fields(lines: list[OcrLineDict], llm: LLMClient) -> tuple[list[ExtractionFieldDict], dict]:
    """Returns (8 fields in FIELD_CODES order, meta{model_name, prompt_version, raw_llm_output})."""
    doc_text = format_lines(select_lines(lines))
    output = llm.chat_json(SYSTEM, "[문서 라인 목록]\n" + doc_text, SCHEMA, prompt_version=PROMPT_VERSION, name="contract_fields")

    raw = {code: _raw((output.get(code) or {}).get("raw_value")) for code in FIELD_CODES}
    normalized = normalize_fields(raw)

    fields: list[ExtractionFieldDict] = []
    for code in FIELD_CODES:
        value = raw[code]

        def requery(code=code, value=value) -> list[str]:
            prompt = f"[문서 라인 목록]\n{doc_text}\n\n항목: {FIELD_LABELS[code]}\n값: {value}\n위 값이 적힌 라인 ID만 반환하라."
            out = llm.chat_json(SYSTEM, prompt, REQUERY_SCHEMA, prompt_version=REQUERY_PROMPT_VERSION, name="evidence")
            return out.get("evidence_line_ids") or []

        method, highlights, score = map_value(value, lines, (output.get(code) or {}).get("evidence_line_ids"), requery if value else None, code)
        fields.append(
            {
                "field_code": code,
                "raw_value": value,
                "normalized_value": normalized[code],
                "confidence": _confidence(method, score, normalized[code]) if value else 0.0,
                "mapping_method": method,
                "highlights": highlights,
            }
        )
    meta = {"model_name": llm.model, "prompt_version": PROMPT_VERSION, "raw_llm_output": output}
    return fields, meta
