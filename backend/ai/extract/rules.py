"""Label–value pairing and the rule-based extractor of the 8 guarantee fields (no LLM).

Forms write values next to a label in four layouts; each becomes a Pair(label, value, line):

  inline  "5. 계 약 금 액 : 일금 ... (￦687,000,000)"   several pairs per line, cut at the next known label
  prefix  "계약금액 금 팔억구천만원정(￦890,000,000)"     label words then the value, no colon
  next    "9. 계약이행보증금" / "ㅇ 계약금액의 ( )%, 일금 ..." label alone, value on the next line
  cell    table label cell -> value cell to its right (same row band) or below it (column header);
          geometry, not r/c ranks, so merged cells (a label spanning two rows, "계/약/자" stacked letters,
          a header over several value rows) still pair with the right value.

Signature tables ("원사업자 | 수급사업자" then "상호 또는 명칭 : ... | 상호 또는 명칭 : ...") and lines like
"* 원사업자 주소 : 상호 : 가온산업(주)" carry a role; pairs under a role are labelled "원사업자.상호".

Used three ways: the GPU-less extractor (LLM_BASE_URL unset), filling fields the LLM left empty
(extract_fields), and the "[표 r6,c3 · 공사명]" label hint on table value lines in the LLM prompt.
"""

import re
import unicodedata
from dataclasses import dataclass

from ai.extract.normalize import normalize_amount, normalize_biz_no, normalize_company, parse_dates
from ai.types import FIELD_CODES, OcrLineDict

ROLES = ("원사업자", "발주자", "발주처", "발주기관", "도급인", "위탁기업", "갑")
_OTHER_ROLES = ("수급사업자", "수급인", "수탁기업", "계약상대자", "을", "임차인", "계약자")

_LEAD_RE = re.compile(r"^(?:\s*(?:\d{1,2}[.)]|\(\d{1,2}\)|[가-하][.)]|[ㅇ○◦◇◆■□▶▷*※•·ㆍ\-]))+\s*")
_BULLET_SPLIT = re.compile(r"\s*[ㆍ•]\s*")  # not "·": names use it ("제조·구매")
_SEG_SPLIT = re.compile(r"\s+\|\s+")
_COLON = re.compile(r"[:：]")
_KNOWN_TAIL = re.compile(
    r"(?:상\s*호(?:\s*또는\s*(?:법인)?\s*명\s*칭?)?|전\s*화\s*(?:번\s*호)?|팩\s*스|주\s*소|대\s*표\s*자(?:\s*성\s*명)?"
    r"|(?:사업자|주민)?\s*\(?\s*법인\s*\)?\s*(?:등록)?\s*번\s*호|사업자\s*(?:등록)?\s*번\s*호|등록\s*번\s*호[^:：]*|성\s*명)\s*$"
)
_GENERIC_TAIL = re.compile(r"(?:^|[\s/,])([가-힣()]{2,14})\s*$")
_BLANK_CHARS = re.compile(r"[\s금원정￦₩제호년월일%().,\-~:：/·ㆍ*]|부터|까지|\(인\)|인")


def compact(text: str) -> str:
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", text))


def clean_label(text: str) -> str:
    return compact(_LEAD_RE.sub("", text)).strip("*※")


def has_content(value: str) -> bool:
    """False for form blanks: "일금 원정 (￦ )", "제 호", ". . .", "( )%", "년 월 일", "(인)"."""
    return bool(_BLANK_CHARS.sub("", value))


@dataclass
class Pair:
    label: str  # compact, numbering stripped; "원사업자.상호" under a role
    value: str  # substring of line text
    line: OcrLineDict
    kind: str  # inline | prefix | next | cell | header
    order: int  # document order of the value line


# ---------- field labels ----------

_NAME_EXCLUDE = ("발주", "상호", "대표", "성명", "명칭", "업체", "기관", "공종", "주소")
FIELD_LABELS: dict[str, list[tuple[re.Pattern, int]]] = {
    "contract_name": [
        (re.compile(r"^하도급(?:공사|용역|계약)?명(?:\([가-힣]+\))?$"), 1),
        (re.compile(r"^(?:[가-힣]{0,12}(?:공사|용역|물품|사업|과업|구매|계약|위탁|용역계약)|계약건|건)명(?:\([가-힣]+\))?$"), 2),
        (re.compile(r"^도급공사명$"), 3),
    ],
    "contract_amount": [
        (re.compile(r"^(?:총)?(?:계약|공사|용역|하도급|도급|대여|물품)?(?:금액|대금)(?:\([^)]*\))?$"), 1),
    ],
    "guarantee_amount": [
        (re.compile(r"^(?:계약|이행|계약이행)?보증금(?:액|해당액)?$"), 1),
        (re.compile(r"^하자보수보증금(?:율\(%\))?(?:및금액)?$"), 3),
    ],
    "contract_date": [
        (re.compile(r"^계약(?:\(예정\))?(?:연월일|일자|체결일|일)$|^체결일자?$"), 1),
    ],
    "performance_due_date": [
        (re.compile(r"^(?:준공|완공|완료|납품|이행)(?:예정)?(?:연월일|기한|일자?|기일)?$|^계약이행기일$|^납기$"), 1),
        (re.compile(r"^(?:계약|공사|용역|이행|계약이행|대여|납품|위탁)기간$"), 2),
    ],
    "guarantee_period": [
        (re.compile(r"(?:하자담보책임|담보책임존속|하자보수보증)기간$|^보증기간$"), 1),
    ],
    "creditor_name": [
        (re.compile(r"^(?:발주자|발주처|발주기관|도급인|갑|위탁기업|발주자명|발주기관명)(?:\([가-힣]+\))?$"), 1),
        (re.compile(r"^(?:" + "|".join(ROLES) + r")\.상호(?:또는)?(?:법인)?(?:명칭?)?$"), 2),
    ],
    "creditor_biz_no": [
        (re.compile(r"^(?:" + "|".join(ROLES) + r")\..*번호$"), 1),
        (re.compile(r"^(?:발주자|발주처|발주기관)(?:사업자)?(?:등록)?번호$"), 1),
    ],
}
ALL_LABELS = [rx for pats in FIELD_LABELS.values() for rx, _ in pats]


def field_label(code: str, label: str) -> int | None:
    """Priority (lower is better) of `label` for field `code`, or None."""
    if code == "contract_name" and any(w in label for w in _NAME_EXCLUDE):
        return None
    base = label.split(".", 1)[-1] if "." in label and code not in ("creditor_name", "creditor_biz_no") else label
    return next((prio for rx, prio in FIELD_LABELS[code] if rx.search(base)), None)


def is_label(text: str) -> bool:
    """A table cell / line that is a field label (any field) rather than a value."""
    lab = clean_label(text)
    if not lab or len(lab) > 22 or re.search(r"\d", lab):
        return False
    return any(rx.search(lab) for rx in ALL_LABELS) or lab in ("발주처계약상대자", "계약상대자", "대표자", "주소", "전화번호", "상호")


# ---------- pair finding ----------


def _split_value(chunk: str) -> tuple[str, str]:
    """chunk between two colons -> (value of the previous label, next label)."""
    m = _KNOWN_TAIL.search(chunk) or _GENERIC_TAIL.search(chunk)
    if not m:
        return chunk.strip(), ""
    start = m.start(1) if m.re is _GENERIC_TAIL else m.start()
    return chunk[:start].strip(" /,"), chunk[start:]


def _clean_value(value: str) -> str:
    value = re.sub(r"\(\s*(?:서명\s*또는\s*)?인\s*\)", "", value).strip()
    first = next((p for p in _BULLET_SPLIT.split(value) if p.strip()), "")
    return first.strip(" ,/")


def inline_pairs(text: str) -> list[tuple[str, str]]:
    """'라벨 : 값 라벨2 : 값2' -> [(label, value)]; a role word in a label prefixes the following labels."""
    colons = [m.start() for m in _COLON.finditer(text)]
    if not colons:
        return []
    out, role = [], None
    label_text, start = text[: colons[0]], 0
    for i, pos in enumerate(colons):
        end = colons[i + 1] if i + 1 < len(colons) else len(text)
        chunk = text[pos + 1 : end]
        value, next_label = _split_value(chunk) if i + 1 < len(colons) else (chunk.strip(), "")
        label = clean_label(label_text)
        if r := next((w for w in ROLES + _OTHER_ROLES if w in label and not label.startswith(w + "는")), None):
            role = r if r in ROLES else "_other"
        if label:
            out.append((f"{role}.{label}" if role and not any(w in label for w in ROLES + _OTHER_ROLES) else label, _clean_value(value)))
        label_text, start = next_label, end
    return out


def _prefix_pair(text: str) -> tuple[str, str] | None:
    """'계약금액 금 ...', '약 계약보증금 금 ...', '준공 2026년 8월 15일': label words + value, no colon."""
    tokens = _LEAD_RE.sub("", text).split()
    for skip in (0, 1):
        if skip and (len(tokens) < 2 or len(tokens[0]) != 1):  # stacked vertical label letter "약"
            continue
        acc = ""
        for k in range(skip, min(len(tokens) - 1, skip + 5)):
            acc += tokens[k]
            if any(rx.search(acc) for rx in ALL_LABELS):
                rest = " ".join(tokens[k + 1 :])
                return (acc, rest) if has_content(rest) else None
    return None


def _center_y(b: list[float]) -> float:
    return (b[1] + b[3]) / 2


def cell_pairs(lines: list[OcrLineDict]) -> list[tuple[OcrLineDict, OcrLineDict, str]]:
    """(label line, value line, kind) for table cells on each page, by geometry.
    right: value cell starts right of the label and its centre lies within the label's row band (+-1 line height,
    so a label merged over two rows pairs with both). header: label above, columns overlap (column-header tables)."""
    out = []
    by_page: dict[int, list[OcrLineDict]] = {}
    for ln in lines:
        if ln["table_cell"]:
            by_page.setdefault(ln["page_no"], []).append(ln)
    for cells in by_page.values():
        labels = [c for c in cells if is_label(c["text"])]
        values = [c for c in cells if not is_label(c["text"]) and len(compact(c["text"])) > 1]
        for lab in labels:
            lb = lab["bbox"]
            h = max(lb[3] - lb[1], 0.008)
            right = [
                v
                for v in values
                if v["bbox"][0] >= lb[2] - 0.01 and v["bbox"][0] - lb[2] < 0.45 and lb[1] - h <= _center_y(v["bbox"]) <= lb[3] + h
            ]
            right.sort(key=lambda v: (round(v["bbox"][0] - lb[2], 2), abs(_center_y(v["bbox"]) - _center_y(lb))))
            out.extend((lab, v, "cell") for v in right[:2])
            below = [
                v
                for v in values
                if v["bbox"][1] >= lb[3] - 0.004
                and v["bbox"][1] - lb[3] < 0.1
                and min(v["bbox"][2], lb[2]) - max(v["bbox"][0], lb[0]) > 0.3 * min(v["bbox"][2] - v["bbox"][0], lb[2] - lb[0])
            ]
            below.sort(key=lambda v: v["bbox"][1])
            out.extend((lab, v, "header") for v in below[:3])
    return out


def find_pairs(lines: list[OcrLineDict]) -> list[Pair]:
    order = {ln["line_id"]: i for i, ln in enumerate(lines)}
    pairs: list[Pair] = []
    roles: list[str | None] = []  # column roles of a "원사업자 | 수급사업자" header, for the next few lines
    roles_left = 0
    for i, ln in enumerate(lines):
        segs = _SEG_SPLIT.split(ln["text"])
        seg_labels = [clean_label(s) for s in segs]
        if len(segs) > 1 and all(s in ROLES + _OTHER_ROLES for s in seg_labels):
            roles, roles_left = seg_labels, 4
            continue
        for j in range(len(segs) - 1):  # "대여금액 | 금 오억..." pipe-table row: label cell then value cell
            if is_label(segs[j]) and not is_label(segs[j + 1]) and not _COLON.search(segs[j] + segs[j + 1]):
                pairs.append(Pair(clean_label(segs[j]), _clean_value(segs[j + 1]), ln, "cell", order[ln["line_id"]]))
        for j, seg in enumerate(segs):
            role = roles[j] if roles_left and j < len(roles) and roles[j] in ROLES else None
            for label, value in inline_pairs(seg):
                lab = f"{role}.{label.split('.')[-1]}" if role and "." not in label else label
                pairs.append(Pair(lab, value, ln, "inline", order[ln["line_id"]]))
            if not _COLON.search(seg) and (pp := _prefix_pair(seg)):
                pairs.append(Pair(pp[0], pp[1], ln, "prefix", order[ln["line_id"]]))
        roles_left = max(0, roles_left - 1)
        label_only = re.sub(r"[:：]\s*$", "", ln["text"])
        if not ln["table_cell"] and is_label(label_only) and (not _COLON.search(ln["text"]) or ln["text"].rstrip().endswith((":", "："))):
            for nxt in lines[i + 1 : i + 3]:
                if nxt["page_no"] != ln["page_no"] or is_label(nxt["text"]) or _COLON.search(nxt["text"]) or re.match(r"^\s*\d{1,2}\.\s", nxt["text"]):
                    break
                pairs.append(Pair(clean_label(label_only), _clean_value(_LEAD_RE.sub("", nxt["text"])), nxt, "next", order[nxt["line_id"]]))
    for lab, val, kind in cell_pairs(lines):
        pairs.append(Pair(clean_label(lab["text"]), _clean_value(val["text"]), val, kind, order[val["line_id"]]))
    return pairs


def table_label_hints(lines: list[OcrLineDict]) -> dict[str, str]:
    """value line_id -> its label text, for table cells (LLM prompt hint '[표 r6,c3 · 공사명]')."""
    hints: dict[str, str] = {}
    for lab, val, kind in cell_pairs(lines):
        if kind == "cell" or val["line_id"] not in hints:
            hints.setdefault(val["line_id"], clean_label(lab["text"]))
    return hints


# ---------- field values ----------


def _valid(code: str, value: str) -> str | None:
    """The value as stored (substring of the line) when it has the field's shape, else None."""
    value = value.strip()
    if not value or not has_content(value):
        return None
    if code in ("contract_amount", "guarantee_amount"):
        return value if (normalize_amount(value) or {}).get("amount") else None
    if code == "contract_date":
        return value if parse_dates(value) else None
    if code == "performance_due_date":
        return value if parse_dates(value) else None
    if code == "guarantee_period":
        return value if len(parse_dates(value)) >= 2 or re.search(r"계약일|준공|\d+\s*(?:년|개월|일)간?", value) else None
    if code == "creditor_biz_no":
        return value if normalize_biz_no(value) else None
    value = re.sub(r"\s*귀하$", "", value).strip()
    c = compact(value)
    if _PROSE_RE.search(c):
        return None
    if not re.search(r"[가-힣]", c) or len(c) < 2:
        return None
    if code == "creditor_name":
        bare = re.sub(r"\(.*?\)", "", c)
        if bare in ROLES + _OTHER_ROLES or bare.endswith(("공무원", "출납원")) or "번호" in c or len(c) > 40:
            return None
        return value
    if len(c) > 60 or c.endswith("계약서") or "【" in c:
        return None
    return value


_PROSE_RE = re.compile(r"^제\d+조|한다|합니다|하여야|이라|으로서|에따라|또는|경우|^[^가-힣(]*$")
FRONT_LINES = 150  # cover block of a form; attachments and articles come later and repeat the labels blank


def _period_end(pair: Pair, lines: list[OcrLineDict]) -> str | None:
    """'용역기간 : 2026년 8월 20일부터' + next line '2027년 5월 28일까지' -> the line with the end date."""
    if len(parse_dates(pair.value)) >= 2 or "부터" not in pair.value:
        return pair.value
    nxt = next((ln for ln in lines[pair.order + 1 : pair.order + 2] if ln["page_no"] == pair.line["page_no"]), None)
    return nxt["text"].strip() if nxt and parse_dates(nxt["text"]) else pair.value


_DATE_TEXT = re.compile(r"\d{4}\s*[.년\-/]\s*\d{1,2}\s*[.월\-/]\s*\d{1,2}\s*[.일]?")


def date_text(value: str, last: bool = False) -> str:
    """The date as written inside a longer value ('2026년 1월 14일부터 2026년 7월 20일까지' -> end date), so the
    highlight covers the date only."""
    found = _DATE_TEXT.findall(value)
    return (found[-1] if last else found[0]).strip() if found else value


@dataclass
class RuleValue:
    raw: str
    line_id: str
    kind: str  # pair kind, or addressee | signature
    priority: int


def _addressee(lines: list[OcrLineDict]) -> RuleValue | None:
    """Payment slips / pledges are addressed to the creditor: '새솔군 상하수도사업소장 귀하'."""
    for ln in lines:
        text = ln["text"].strip()
        if re.search(r"귀\s*하$", text):
            value = re.sub(r"\s*귀\s*하$", "", _COLON.split(text)[-1]).strip()
            if (v := _valid("creditor_name", value)) and len(compact(v)) >= 3:
                return RuleValue(v, ln["line_id"], "addressee", 3)
    return None


def rule_values(lines: list[OcrLineDict]) -> dict[str, RuleValue | None]:
    """Best labelled value per field (None = not found). contract_date also falls back to the signature date."""
    from ai.extract import _has_contract_date_field, _is_contract, signature_date  # noqa: PLC0415 - circular

    pairs = find_pairs(lines)
    best: dict[str, RuleValue | None] = {}
    for code in FIELD_CODES:
        cands = []
        for p in pairs:
            prio = field_label(code, p.label)
            if prio is None:
                continue
            value = _period_end(p, lines) if code == "performance_due_date" and prio == 2 else p.value
            line_id = p.line["line_id"]
            if value != p.value:
                line_id = next((ln["line_id"] for ln in lines[p.order + 1 : p.order + 2]), line_id)
            if (v := _valid(code, value)) and code in ("contract_date", "performance_due_date"):
                v = date_text(v, last=code == "performance_due_date")
            if v:
                kind_rank = {"cell": 0, "inline": 0, "prefix": 1, "header": 1, "next": 2}[p.kind]
                cands.append((p.order > FRONT_LINES, prio, kind_rank, p.order, RuleValue(v, line_id, p.kind, prio)))
        best[code] = min(cands, key=lambda c: c[:4])[4] if cands else None
    if best["creditor_name"] is None or best["creditor_name"].priority > 1:
        addressee = _addressee(lines)
        if addressee and (best["creditor_name"] is None or not _is_contract(lines)):
            best["creditor_name"] = addressee
    is_contract = _is_contract(lines)
    if best["contract_date"] and not is_contract and not _has_contract_date_field(lines):
        best["contract_date"] = None
    if best["contract_date"] is None and is_contract and (sig := signature_date(lines)):
        m = parse_dates(sig[0])
        if m:
            best["contract_date"] = RuleValue(date_text(sig[0]), sig[1], "signature", 4)
    if best["creditor_name"]:
        best["creditor_name"].raw = (normalize_company(best["creditor_name"].raw) or {}).get("text") and best["creditor_name"].raw
    return best


RULE_VERSION = "rule-based-v2"
_KIND_CONFIDENCE = {"cell": 0.85, "inline": 0.85, "prefix": 0.75, "header": 0.75, "next": 0.7, "addressee": 0.7, "signature": 0.6}


def extract_rule_based(lines: list[OcrLineDict]) -> list[dict]:
    """8 ExtractionFieldDicts from labelled values only (GPU-less path; same contract as extract_fields)."""
    from ai.extract import with_title  # noqa: PLC0415 - circular
    from ai.extract.normalize import normalize_fields
    from ai.mapping import map_value

    found = rule_values(lines)
    raw = {code: (rv.raw if rv else None) for code, rv in found.items()}
    if raw["creditor_name"]:
        raw["creditor_name"] = with_title(raw["creditor_name"], lines)
    normalized = normalize_fields(raw)
    fields = []
    for code in FIELD_CODES:
        rv, value = found[code], raw[code]
        if not value:
            fields.append({"field_code": code, "raw_value": None, "normalized_value": None, "confidence": 0.0, "mapping_method": "none", "highlights": []})
            continue
        method, highlights, _ = map_value(value, lines, [rv.line_id], None, code)
        conf = _KIND_CONFIDENCE[rv.kind] * (1.0 if normalized[code] else 0.6)
        fields.append(
            {"field_code": code, "raw_value": value, "normalized_value": normalized[code], "confidence": round(conf, 3), "mapping_method": method, "highlights": highlights}
        )
    return fields
