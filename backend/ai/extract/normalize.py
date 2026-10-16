"""⑧ Post-processing / normalization of raw values (03_데이터정의 §3, 05_OCR_Pipeline §3-⑧).

amount -> {"amount": int}            "일금 삼억오천만원정", "₩350,000,000", "3억 5천만원"; digits win when both exist
date   -> {"date": "YYYY-MM-DD"}      "2026.3.5", "2026년 3월 5일", "26.03.05" (2-digit year = 20xx)
period -> {"start", "end", "derived"?} relative words (계약일로부터 / 준공일까지 / N년간) resolved from other fields
biz_no -> {"text": "###-##-#####", "checksum_valid": bool}
names  -> {"text": ...}               quotes/spaces cleaned, "(주)" / "주식회사" / "㈜" unified to "(주)"
"""

import calendar
import re
import unicodedata
from datetime import date, timedelta

_DIGIT = {
    "영": 0,
    "공": 0,
    "일": 1,
    "이": 2,
    "삼": 3,
    "사": 4,
    "오": 5,
    "육": 6,
    "칠": 7,
    "팔": 8,
    "구": 9,
}
_SMALL = {"십": 10, "백": 100, "천": 1000}
_BIG = {"만": 10**4, "억": 10**8, "조": 10**12}
KOR_AMOUNT_RE = re.compile(r"([영공일이삼사오육칠팔구십백천만억조\d,\s]*[십백천만억조][영공일이삼사오육칠팔구십백천만억조\d,\s]*?)\s*원")
DIGIT_AMOUNT_RE = re.compile(r"(?:(?:₩|\\|W|KRW|금)\s*(\d{1,3}(?:,\d{3})+|\d+)(?![\d,]*\s*[십백천만억조])|(\d{1,3}(?:,\d{3})+|\d{4,})\s*원)")


def korean_to_int(text: str) -> int | None:
    """'삼억오천만' -> 350000000, '1,500만' -> 15000000, '일십만' -> 100000. Digits and numerals may mix."""
    total = section = 0
    num: int | None = None
    seen = False
    for token in re.findall(r"\d[\d,]*|\S", text):
        if token[0].isdigit():
            num, seen = int(token.replace(",", "")), True
        elif token in _DIGIT:
            num, seen = _DIGIT[token], True
        elif token in _SMALL:
            section += (num if num is not None else 1) * _SMALL[token]
            num, seen = None, True
        elif token in _BIG:
            total += ((section + (num or 0)) or 1) * _BIG[token]
            section, num, seen = 0, None, True
    return total + section + (num or 0) if seen else None


def parse_amounts(text: str) -> tuple[int | None, int | None]:
    """(digit amount, Korean-numeral amount) found in `text`."""
    t = unicodedata.normalize("NFKC", text)
    digit = None
    if m := DIGIT_AMOUNT_RE.search(t):
        digit = int((m.group(1) or m.group(2)).replace(",", ""))
    korean = None
    if m := KOR_AMOUNT_RE.search(t.replace("일금", "금")):
        korean = korean_to_int(m.group(1))
    return digit, korean


def normalize_amount(text: str) -> dict | None:
    digit, korean = parse_amounts(text)
    value = digit if digit is not None else korean  # 숫자 병기 시 숫자 우선
    return {"amount": value} if value is not None else None


_DATE_RES = [
    re.compile(r"(?<!\d)(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})(?!\d)"),
    re.compile(r"(?<![\d.])(\d{2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})(?![\d])"),
]
_MONTHS = {m: i for i, m in enumerate(calendar.month_name) if m}
_EN_DATE_RE = re.compile(r"(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})")


def parse_dates(text: str) -> list[str]:
    """All valid dates in text order, ISO formatted."""
    t = unicodedata.normalize("NFKC", text)
    found: list[tuple[int, str]] = []
    taken: list[range] = []
    for rx in _DATE_RES:
        for m in rx.finditer(t):
            if any(m.start() in r for r in taken):
                continue
            y, mo, d = (int(g) for g in m.groups())
            y = y + 2000 if y < 100 else y
            if iso := _iso(y, mo, d):
                found.append((m.start(), iso))
                taken.append(range(m.start(), m.end()))
    for m in _EN_DATE_RE.finditer(t):
        if iso := _iso(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2))):
            found.append((m.start(), iso))
    return [iso for _, iso in sorted(found)]


def _iso(y: int, mo: int, d: int) -> str | None:
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def normalize_date(text: str) -> dict | None:
    dates = parse_dates(text)
    return {"date": dates[0]} if dates else None


def normalize_due_date(text: str) -> dict | None:
    """계약이행기일: a period written here means its end date."""
    dates = parse_dates(text)
    return {"date": dates[-1]} if dates else None


def _add(start: str, n: int, unit: str) -> str:
    """Inclusive period end: 2026-03-05 + 1년 -> 2027-03-04."""
    d = date.fromisoformat(start)
    if unit == "일":
        return (d + timedelta(days=n - 1)).isoformat()
    y, m = divmod(d.month - 1 + (n * 12 if unit == "년" else n), 12)
    y, m = d.year + y, m + 1
    return (date(y, m, min(d.day, calendar.monthrange(y, m)[1])) - timedelta(days=1)).isoformat()


_START_WORDS = ("계약일", "계약체결일", "체결일")
_END_WORDS = ("준공일", "준공", "이행기일", "완료일", "만료일", "납품일", "기한")
_DURATION_RE = re.compile(r"(?<!\d)(\d{1,3})\s*(개월|년|일)")


def normalize_period(text: str, contract_date: str | None, due_date: str | None) -> dict | None:
    """Two dates -> start/end. Relative words are replaced by the extracted contract/due dates (derived=true)."""
    dates = parse_dates(text)
    if len(dates) >= 2:
        return {"start": dates[0], "end": dates[1]}
    compact = re.sub(r"\s", "", text)  # OCR splits words: "계약 일 로부터 준 공 일 까 지"
    from_contract = contract_date if contract_date and any(w in compact for w in _START_WORDS) else None
    if dates and from_contract:  # "계약일로부터 2027. 3. 4.까지"
        return {"start": from_contract, "end": dates[0], "derived": True}
    start = dates[0] if dates else from_contract
    if start is None:
        return None
    rest = text
    for rx in _DATE_RES:  # drop the date itself so "2026년 3월 5일" is not read as a duration
        rest = rx.sub(" ", unicodedata.normalize("NFKC", rest))
    if m := _DURATION_RE.search(rest):
        return {
            "start": start,
            "end": _add(start, int(m.group(1)), m.group(2)),
            "derived": True,
        }
    if due_date and any(w in re.sub(r"\s", "", rest) for w in _END_WORDS):
        return {"start": start, "end": due_date, "derived": True}
    return None


_BIZ_RE = re.compile(r"(?<!\d)(\d{3})\s*-?\s*(\d{2})\s*-?\s*(\d{5})(?!\d)")


def biz_no_checksum_ok(digits: str) -> bool:
    """Korean business registration number check digit."""
    d = [int(c) for c in digits]
    s = sum(x * w for x, w in zip(d[:9], [1, 3, 7, 1, 3, 7, 1, 3, 5], strict=True)) + d[8] * 5 // 10
    return (10 - s % 10) % 10 == d[9]


def normalize_biz_no(text: str) -> dict | None:
    if not (m := _BIZ_RE.search(unicodedata.normalize("NFKC", text))):
        return None
    return {
        "text": "-".join(m.groups()),
        "checksum_valid": biz_no_checksum_ok("".join(m.groups())),
    }


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\"'“”‘’「」『』]", "", text)
    return " ".join(text.split())


def normalize_company(text: str) -> dict | None:
    t = _clean(text)
    t = re.sub(r"\s*귀하$", "", t)
    t = re.sub(r"\(\s*주\s*\)|^주\s*\)", "(주)", t)  # "주)미래기계": LLM/OCR dropped the "("
    t = re.sub(r"^주식회사\s*(.+)$", r"(주)\1", t)
    t = re.sub(r"^(.+?)\s*주식회사$", r"\1(주)", t)
    t = re.sub(r"\s*\(주\)\s*", "(주)", t).strip()
    t = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", t)  # OCR splits Hangul names: "한빛 시청" == "한빛시청"
    return {"text": t} if t else None


def normalize_text(text: str) -> dict | None:
    t = _clean(text)
    return {"text": t} if t else None


NORMALIZERS = {
    "contract_name": normalize_text,
    "contract_amount": normalize_amount,
    "guarantee_amount": normalize_amount,
    "contract_date": normalize_date,
    "performance_due_date": normalize_due_date,
    "creditor_name": normalize_company,
    "creditor_biz_no": normalize_biz_no,
}


def normalize_fields(raw: dict[str, str | None]) -> dict[str, dict | None]:
    out = {code: (fn(v) if (v := raw.get(code)) else None) for code, fn in NORMALIZERS.items()}
    period = raw.get("guarantee_period")
    contract_date = (out["contract_date"] or {}).get("date")
    due = (out["performance_due_date"] or {}).get("date")
    out["guarantee_period"] = normalize_period(period, contract_date, due) if period else None
    return out
