"""⑤ LLM structured extraction of the 8 guarantee fields (FR-04) + ⑥ bbox mapping + ⑧ normalization.

Prompt rules (05_OCR_Pipeline §3-⑥): JSON only, schema-enforced; every field has raw_value (verbatim),
evidence_line_ids, confidence; absent -> raw_value null (no guessing); normalization happens afterwards.

Schema notes from Ollama qwen2.5:7b runs (SPEC): `anyOf[null, object]` makes every field null, so each field is
always an object with `raw_value: string|null`; line IDs come back as "[L1-2]" -> pattern + post-cleaning;
the model's confidence is ~always 1, so the stored confidence is derived from mapping/validation instead.
A value that cannot be found anywhere in the document (best fuzzy < 50, re-query failed) is nulled: 추측 금지.
A value of the wrong shape (form blank "년 월 일", a label, a role word like "원사업자", a form title / notice sentence) is
asked again once for just those fields (one extra call); still wrong -> null. Forms run: these were ~60% of the failures.
Values that merely look OCR-garbled (50~85) stay with mapping_method=none for manual fixing (05_OCR_Pipeline ⑦).
"""

import logging
import re
import unicodedata
from typing import Any

from ai.extract.normalize import _DATE_RES, _END_WORDS, _START_WORDS, normalize_fields, parse_dates
from ai.llm import LLMClient, LLMUnavailableError
from ai.mapping import map_value
from ai.types import FIELD_CODES, FIELD_LABELS, ExtractionFieldDict, OcrLineDict

logger = logging.getLogger(__name__)

PROMPT_VERSION = "extract-v4"
RETRY_PROMPT_VERSION = "extract-retry-v1"
REQUERY_PROMPT_VERSION = "requery-v1"
MAX_FULL_PAGES = 5
MAX_PROMPT_CHARS = 10_000  # ~2.6k tokens (~3.9 chars/token, qwen2.5), inside 05 설계서 "2~6k 토큰"; 20k: 7B lost the front (FTC 0~1/8 -> 5~6/8 at 10k)
WINDOW = 10
KEYWORDS = ("계약", "금액", "보증", "기일", "기한", "기간", "채권자", "발주", "도급", "사업자", "공사명", "용역명", "건명", "준공", "일자")

FIELD_GUIDE = {
    "contract_name": "계약건명 — 공사명·용역명·물품명·사업명·계약건명",
    "contract_amount": "계약금액 — 총 계약금액 (원문 표기 그대로, 한글·숫자 병기 포함)",
    "guarantee_amount": "보증금액 — 계약보증금·보증금액·보증금 해당액",
    "contract_date": "계약일자 — '계약일자'·'계약(예정)연월일' 칸, 없으면 계약서 서명·기명날인 줄 옆 날짜. 계약기간·착공일의 시작일이나 납부서·각서의 작성일은 계약일자가 아님(칸이 없으면 null)",
    "performance_due_date": "계약이행기일 — 준공기한·완료기한·납품기한·이행기간의 종료일",
    "guarantee_period": '보증기간 — 보증기간·하자담보책임기간 칸에 적힌 기간만 ("계약일로부터 준공일까지" 같은 상대표현도 원문 그대로). 계약기간·공사기간·착공~준공은 보증기간이 아님(칸이 없으면 null)',
    "creditor_name": '채권자명 — 보증의 채권자 = 발주자·도급인·발주기관·발주처·"갑"·납부서의 수신인. 적힌 그대로(직함 "○○장"·"이사장" 포함, "귀하"만 제외)',
    "creditor_biz_no": "채권자 사업자등록번호 — 채권자(발주자)의 번호만",
}

SYSTEM = (
    "너는 한국어 계약서에서 보증신청 항목을 추출하는 도구다. 반드시 JSON만 출력한다.\n"
    "규칙:\n"
    "1. 각 항목의 raw_value에는 문서에 적힌 값을 원문 표기 그대로 넣는다(라벨 제외, 정규화·계산 금지).\n"
    "2. evidence_line_ids에는 값이 적힌 라인의 ID(예: L1-17)만 넣는다. 라인 본문은 넣지 않는다.\n"
    "3. 문서에 없거나 빈칸(OO, ○○, 공란)인 항목은 raw_value를 null, evidence_line_ids를 []로 둔다. 추측 금지.\n"
    "4. confidence는 0~1 사이 숫자.\n"
    "5. 빈칸 서식(예: '년 월 일', '일금 원정 (￦ )', '(인)', '사업자(법인)번호 :')과 라벨은 값이 아니다. "
    "같은 항목이 여러 곳에 있으면 실제 값이 채워진 곳을 고른다.\n"
    "6. 채권자명에는 '원사업자', '발주자', '갑' 같은 역할 이름이 아니라 그 칸에 적힌 회사·기관 이름을 넣는다.\n"
    "7. 계약건명은 공사명·용역명·물품명 칸에 적힌 짧은 이름이다. 서식 제목(○○계약서)·법률 문장·안내문은 넣지 않는다.\n"
    "항목 설명:\n" + "\n".join(f"- {code}: {desc}" for code, desc in FIELD_GUIDE.items())
)

_FIELD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "raw_value": {"type": ["string", "null"]},
        "evidence_line_ids": {
            "type": "array",
            "items": {"type": "string", "pattern": "^L[0-9]+-[0-9]+$"},
            "maxItems": 5,
        },  # unbounded -> 7B loops to the token limit
        "confidence": {"type": "number"},
    },
    "required": ["raw_value", "evidence_line_ids", "confidence"],
}
SCHEMA = {"type": "object", "properties": {code: {"$ref": "#/$defs/field"} for code in FIELD_CODES}, "required": FIELD_CODES, "$defs": {"field": _FIELD_SCHEMA}}
REQUERY_SCHEMA = {"type": "object", "properties": {"evidence_line_ids": _FIELD_SCHEMA["properties"]["evidence_line_ids"]}, "required": ["evidence_line_ids"]}

TYPED_FIELDS = {"contract_amount", "guarantee_amount", "contract_date", "performance_due_date", "creditor_biz_no"}
ROLE_WORDS = {"갑", "을", "발주자", "발주기관", "발주처", "도급인", "수급인", "원사업자", "원사업자등", "수급사업자", "수급사업자등"}
ROLE_WORDS |= {"계약담당공무원", "유가증권취급공무원", "세입세출외현금출납공무원", "중앙관서의장"}
ROLE_WORDS |= {"위탁기업", "수탁기업", "계약상대자", "계약자", "채권자", "상호또는명칭", "상호", "대표자", "귀하"}
_BLANKS = {"", "null", "none", "n/a", "없음", "해당없음", "미기재", "-", "미정", "미상", "알수없음", "추정되지않음", "확인불가"}
NOT_IN_DOCUMENT = 50  # below this best fuzzy score the value is a fabrication, not an OCR misread
_METHOD_CONFIDENCE = {"llm_ref": 0.95, "exact": 0.9, "fuzzy": 0.75, "none": 0.3}


def format_lines(lines: list[OcrLineDict]) -> str:
    return "\n".join(f"{ln['line_id']}: " + (f"[표 {ln['table_cell']}] " if ln["table_cell"] else "") + ln["text"] for ln in lines)


def select_lines(lines: list[OcrLineDict]) -> list[OcrLineDict]:
    """All lines for <= 5 pages; otherwise keyword lines +-10 (token budget, 05_OCR_Pipeline §3-⑥); then at most
    MAX_PROMPT_CHARS. Without the cap a 39-page FTC form (80k chars) overflowed the model context and the server
    silently kept only the tail (attached blank forms) -> 0/8 fields on 21 forms."""
    picked = lines
    if len({ln["page_no"] for ln in lines}) > MAX_FULL_PAGES:
        keep: set[int] = set()
        for i, line in enumerate(lines):
            if any(k in line["text"].replace(" ", "") for k in KEYWORDS):
                keep.update(range(max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)))
        picked = [lines[i] for i in sorted(keep)]
    # shortcut: front-first cut (contract terms + signature block come first); rank windows if a late field gets cut
    out, used = [], 0
    for ln in picked:
        used += len(ln["line_id"]) + len(ln["text"]) + 3
        if used > MAX_PROMPT_CHARS:
            break
        out.append(ln)
    return out


def _raw(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if re.sub(r"\s", "", text).lower() in _BLANKS else text


def wrong_shape(code: str, raw: str | None, normalized: dict | None) -> str | None:
    """Why `raw` cannot be a value of `code` (None = plausible). Only shape checks; the document decides the rest."""
    if raw is None:
        return None
    compact = re.sub(r"\s", "", raw)
    if code in TYPED_FIELDS:
        return None if normalized else "형식에 맞는 숫자·날짜가 없음(빈칸 또는 라벨)"
    if code == "guarantee_period":
        relative = any(w in compact for w in _START_WORDS + _END_WORDS) or re.search(r"\d", compact)
        return None if normalized or relative else "날짜·기간 표현이 없음"
    if code == "creditor_name":
        if re.sub(r"\(.*?\)", "", compact) in ROLE_WORDS:
            return "회사·기관 이름이 아니라 역할 이름"
        return "이름이 아니라 문장" if len(compact) > 40 else None
    if code == "contract_name" and (len(compact) > 50 or "【" in compact or "이하" in compact or compact.endswith("계약서")):
        return "건명이 아니라 서식 제목·안내 문장"
    return None


_SIGN_WORDS = ("기명날인", "서명", "(인)", "날인")
_YEAR4_RE = re.compile(r"(?<!\d)\d{4}\s*[.\-/년]")


def signature_date(lines: list[OcrLineDict]) -> tuple[str, str] | None:
    """Forms rarely label the contract date: it is the lone date next to the 서명/기명날인 block.
    Last such line wins (cover notes come first); 4-digit years only ("95.6.30 승인" form footers).
    Public forms: 37/48 right when used alone; used only when the LLM returns null."""
    found = None
    for i, line in enumerate(lines):
        dates = parse_dates(line["text"])
        if len(dates) != 1 or not _YEAR4_RE.search(line["text"]):
            continue
        if any(w in near["text"].replace(" ", "") for near in lines[max(0, i - 3) : i + 4] for w in _SIGN_WORDS):
            found = (line["text"], line["line_id"])
    return found


def _is_contract(lines: list[OcrLineDict]) -> bool:
    """Title says 계약서: payment slips, pledges and consent forms have no contract date (their date is a filing date)."""
    return any("계약서" in ln["text"].replace(" ", "") for ln in lines[:5])


_PERIOD_WORDS = ("계약기간", "공사기간", "용역기간", "이행기간", "착공")


def period_start(lines: list[OcrLineDict]) -> tuple[str, str] | None:
    """First date of a 계약기간/공사기간 entry (same line, or the next line when the label is its own table cell)."""
    for i, line in enumerate(lines):
        if any(w in line["text"].replace(" ", "") for w in _PERIOD_WORDS):
            for cand in lines[i : i + 2]:
                if dates := parse_dates(cand["text"]):
                    return dates[0], cand["line_id"]
    return None


def _has_contract_date_field(lines: list[OcrLineDict]) -> bool:
    return any("계약" in (t := ln["text"].replace(" ", "")) and ("연월일" in t or "일자" in t) for ln in lines)


_TITLE_RE = re.compile(r"([가-힣]{0,3}장)(?:귀하)?")


def with_title(name: str, lines: list[OcrLineDict]) -> str:
    """Creditor names are written with the office title ("가람시 시설관리공단 이사장 귀하"); the 7B model drops it.
    Re-attach a title that directly follows the name in the document (gold rule: 직함 포함)."""
    compact = re.sub(r"\s", "", name)
    if compact.endswith("장"):
        return name
    for ln in lines:
        text = re.sub(r"\s", "", ln["text"])
        if (pos := text.find(compact)) >= 0 and (m := _TITLE_RE.match(text, pos + len(compact))) and m.group(1):
            return name + " " + m.group(1)
    return name


def _retry(doc_text: str, bad: dict[str, tuple[str, str]], llm: LLMClient) -> dict:
    """One extra call for just the wrong-shaped fields; the doc prefix is unchanged so server prompt caches reuse it."""
    schema = {"type": "object", "properties": {c: {"$ref": "#/$defs/field"} for c in bad}, "required": list(bad), "$defs": {"field": _FIELD_SCHEMA}}
    notes = "\n".join(f"- {c} ({FIELD_LABELS[c]}): 앞의 답 {v!r}은 {why}" for c, (v, why) in bad.items())
    prompt = f"[문서 라인 목록]\n{doc_text}\n\n[다시 찾을 항목]\n{notes}\n앞의 답은 값이 아니다. 실제 값이 채워진 라인에서 다시 찾고, 채워진 값이 없으면 null."
    try:
        return llm.chat_json(SYSTEM, prompt, schema, prompt_version=RETRY_PROMPT_VERSION, name="contract_fields_retry")
    except LLMUnavailableError as exc:  # the first answer is already usable; a failed retry just nulls the wrong fields
        logger.warning("retry for %s failed: %s", list(bad), exc)
        return {}


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
    evidence = {code: (output.get(code) or {}).get("evidence_line_ids") for code in FIELD_CODES}
    normalized = normalize_fields(raw)
    bad = {c: (raw[c], why) for c in FIELD_CODES if (why := wrong_shape(c, raw[c], normalized[c]))}
    retry_out = _retry(doc_text, bad, llm) if bad else None
    if bad:
        first = {c: (raw[c], evidence[c]) for c in bad}
        for c in bad:
            raw[c], evidence[c] = (_raw((retry_out.get(c) or {}).get("raw_value")), (retry_out.get(c) or {}).get("evidence_line_ids"))
        normalized = normalize_fields(raw)
        for c in bad:
            if why := wrong_shape(c, raw[c], normalized[c]) if raw[c] else "다시 물어도 값 없음":
                # digits = an OCR-garbled real value ("1 2026 년 018 03 일"): keep it for manual fixing (05 ⑦), else null
                keep = next(((v, ids) for v, ids in ((raw[c], evidence[c]), first[c]) if v and c in TYPED_FIELDS and re.search(r"\d", v)), None)
                logger.warning("%s %s=%r after retry: %s", "kept" if keep else "dropped", c, raw[c], why)
                raw[c], evidence[c] = keep or (None, None)
        normalized = normalize_fields(raw)  # guarantee_period depends on the date fields
    is_contract = _is_contract(lines)
    if not is_contract and raw["contract_date"] and not _has_contract_date_field(lines):
        logger.warning("dropped contract_date=%r: not a contract and no 계약일자 field", raw["contract_date"])
        raw["contract_date"] = None  # a slip's / pledge's filing date is not a contract date
    if raw["creditor_name"]:
        raw["creditor_name"] = with_title(raw["creditor_name"], lines)
    normalized = normalize_fields(raw)
    if raw["contract_date"] is None and is_contract and (sig := signature_date(lines)):
        m = _DATE_RES[0].search(unicodedata.normalize("NFKC", sig[0]))
        raw["contract_date"], evidence["contract_date"] = (m.group(0), [sig[1]])  # the date as written, not the 서명 line text
        normalized = normalize_fields(raw)
    if raw["contract_date"] is None and is_contract and (start := period_start(lines)):
        # 계약기간 start != signing date (gold: 09-16 vs 09-13): offered for confirmation only, never the value
        normalized["contract_date"] = {"suggestion": {"date": start[0], "source": "contract_period_start", "ocr_line_id": start[1]}}

    fields: list[ExtractionFieldDict] = []
    for code in FIELD_CODES:
        value = raw[code]

        def requery(code=code, value=value) -> list[str]:
            prompt = f"[문서 라인 목록]\n{doc_text}\n\n항목: {FIELD_LABELS[code]}\n값: {value}\n위 값이 적힌 라인 ID만 반환하라."
            out = llm.chat_json(SYSTEM, prompt, REQUERY_SCHEMA, prompt_version=REQUERY_PROMPT_VERSION, name="evidence")
            return out.get("evidence_line_ids") or []

        method, highlights, score = map_value(value, lines, evidence[code], requery if value else None, code)
        if value and method == "none" and score < NOT_IN_DOCUMENT:
            # nothing in the document even resembles it -> the model invented it (raw kept in raw_llm_output)
            logger.warning("dropped %s=%r: not found in document (best fuzzy %.0f)", code, value, score)
            value, normalized[code] = None, None
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
    meta = {"model_name": llm.model, "prompt_version": PROMPT_VERSION, "raw_llm_output": output if retry_out is None else {**output, "_retry": retry_out}}
    return fields, meta
