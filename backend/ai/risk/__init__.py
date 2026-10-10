"""⑨ Risk clause detection (FR-09): rule engine and LLM engine run in parallel, then score -> severity,
duplicate merge and evidence line IDs -> bbox (05_OCR_Pipeline §3-⑨).

Rules (engine=rule) use default_severity; LLM findings use severity = f(score): >=0.75 HIGH, >=0.45 MEDIUM, else LOW.
LLM findings without a valid evidence line are dropped (근거 우선 — no evidence, no finding).
POLICY_VIOLATION gets top-3 regulation chunks from the RAG search through `policy_search` (the pipelines' contact point).
"""

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from ai.extract import format_lines
from ai.extract.normalize import (
    DIGIT_AMOUNT_RE,
    KOR_AMOUNT_RE,
    korean_to_int,
    parse_amounts,
)
from ai.llm import LLMClient
from ai.mapping import clean_line_ids, line_highlights
from ai.types import FIELD_LABELS, HighlightDict, OcrLineDict, RiskFindingDict

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).with_name("rules.yaml")
PROMPT_VERSION = "risk-v1"
SEVERITY_SCORE = {"HIGH": 0.9, "MEDIUM": 0.6, "LOW": 0.3}
MAX_LLM_LINES = 400  # shortcut: very long contracts are cut at 400 lines; chunk per article if that ever bites

PolicySearch = Callable[[str], list[dict]]


def load_rules(path: Path = RULES_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def severity_of(score: float) -> str:
    return "HIGH" if score >= 0.75 else "MEDIUM" if score >= 0.45 else "LOW"


def _finding(
    rule: dict,
    title: str,
    description: str,
    highlights: list[HighlightDict],
    evidence: str | None,
    *,
    score: float | None = None,
    reasoning: dict | None = None,
) -> RiskFindingDict:
    if score is None:
        severity = rule.get("default_severity") or "MEDIUM"
        score = SEVERITY_SCORE[severity]
    else:
        score = min(1.0, max(0.0, float(score)))
        severity = severity_of(score)
    return {
        "category": rule["category"],
        "severity": severity,
        "score": round(score, 3),
        "rule_code": rule["code"],
        "title": title,
        "description": description,
        "evidence_text": evidence,
        "highlights": highlights,
        "llm_reasoning": reasoning,
    }


def _hl(line: OcrLineDict) -> HighlightDict:
    return {"page_no": line["page_no"], "bbox": line["bbox"], "ocr_line_id": line["line_id"]}


# ---------------- rule engine ----------------

_FRACTION_RE = re.compile(r"((?:\d[\d,]*\s*)?[십백천만]+|\d[\d,]*)\s*분\s*의\s*(\d+(?:\.\d+)?)")
_SLASH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(1,?000|100)(?!\d)")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_CAP_WORDS = ("초과", "한도", "상한", "최대")  # "...의 100분의 30을 초과할 수 없다" is a cap, not a daily rate
_ARTICLE_TITLE_RE = re.compile(r"제\s*\d+\s*조\s*[(【\[]([^)】\]]+)")


def penalty_rates(text: str) -> list[float]:
    """Daily penalty rates as fractions: '1000분의 3', '1천분의 3', '3/1000', '0.3%'."""
    rates = []
    for denom, num in _FRACTION_RE.findall(text):
        d = korean_to_int(denom)
        if d:
            rates.append(float(num) / d)
    rates += [float(n) / int(d.replace(",", "")) for n, d in _SLASH_RE.findall(text)]
    rates += [float(p) / 100 for p in _PERCENT_RE.findall(text)]
    return rates


def penalty_rate_high(rule: dict, lines: list[OcrLineDict], fields: dict) -> list[RiskFindingDict]:
    limit = rule["params"]["max_rate_per_day"]
    keywords = [k.replace(" ", "") for k in rule["params"]["keywords"]]
    out = []
    for i, line in enumerate(lines):
        # keyword on this line, or on the article title right above it ("제8조(지체상금)" / "① ...1000분의 3")
        context = [line["text"]] + ([lines[i - 1]["text"]] if i and _ARTICLE_TITLE_RE.search(lines[i - 1]["text"]) else [])
        squashed = "".join(context).replace(" ", "").lower()
        if not any(k.lower() in squashed for k in keywords) or any(w in line["text"] for w in _CAP_WORDS):
            continue
        over = [r for r in penalty_rates(line["text"]) if r > limit * (1 + 1e-9)]
        if over:
            rate = max(over)
            desc = f"지체상금율 1일 {rate * 1000:g}/1000 — 기준 {limit * 1000:g}/1000 초과"
            out.append(_finding(rule, f"{rule['name']} ({rate * 1000:g}/1000)", desc, [_hl(line)], line["text"]))
    return out


def missing_article(rule: dict, lines: list[OcrLineDict], fields: dict) -> list[RiskFindingDict]:
    text = "".join(ln["text"] for ln in lines).replace(" ", "")
    return [
        _finding(rule, f"{rule['name']}: {article}", f"필수조항 '{article}' 관련 문구({', '.join(kws)})가 계약서에 없습니다.", [], None)
        for article, kws in rule["params"]["required"].items()
        if not any(k.replace(" ", "") in text for k in kws)
    ]


def amount_mismatch(rule: dict, lines: list[OcrLineDict], fields: dict) -> list[RiskFindingDict]:
    out, seen = [], set()
    for line in lines:
        t = line["text"]
        if len(KOR_AMOUNT_RE.findall(t.replace("일금", "금"))) != 1 or len(DIGIT_AMOUNT_RE.findall(t)) != 1:
            continue  # only "금 삼억원정(₩300,000,000)"-style single pairs; several amounts on a line are not a pair
        digit, korean = parse_amounts(t)
        if digit is not None and korean is not None and digit != korean:
            seen.add(line["line_id"])
            out.append(_finding(rule, rule["name"], f"한글 금액 {korean:,}원과 숫자 금액 {digit:,}원이 다릅니다.", [_hl(line)], t))
    for code in ("contract_amount", "guarantee_amount"):  # values broken over two lines
        f = fields.get(code) or {}
        hls = f.get("highlights") or []
        if not f.get("raw_value") or any(h["ocr_line_id"] in seen for h in hls):
            continue
        digit, korean = parse_amounts(f["raw_value"])
        if digit is not None and korean is not None and digit != korean:
            out.append(
                _finding(rule, f"{rule['name']}: {FIELD_LABELS[code]}", f"한글 금액 {korean:,}원과 숫자 금액 {digit:,}원이 다릅니다.", hls, f["raw_value"])
            )
    return out


def date_inconsistent(rule: dict, lines: list[OcrLineDict], fields: dict) -> list[RiskFindingDict]:
    def nv(code):
        return (fields.get(code) or {}).get("normalized_value") or {}

    def hls(*codes):
        return [h for c in codes for h in (fields.get(c) or {}).get("highlights") or []]

    def raw(*codes):
        return " / ".join(r for c in codes if (r := (fields.get(c) or {}).get("raw_value"))) or None

    out = []
    signed, due = nv("contract_date").get("date"), nv("performance_due_date").get("date")
    if signed and due and signed > due:
        out.append(
            _finding(
                rule,
                f"{rule['name']}: 계약일자 > 계약이행기일",
                f"계약일자({signed})가 계약이행기일({due})보다 늦습니다.",
                hls("contract_date", "performance_due_date"),
                raw("contract_date", "performance_due_date"),
            )
        )
    start, end = nv("guarantee_period").get("start"), nv("guarantee_period").get("end")
    if start and end and start > end:
        out.append(
            _finding(
                rule,
                f"{rule['name']}: 보증기간 역전",
                f"보증기간 시작일({start})이 종료일({end})보다 늦습니다.",
                hls("guarantee_period"),
                raw("guarantee_period"),
            )
        )
    return out


RULE_ENGINE = {
    "PENALTY_RATE_HIGH": penalty_rate_high,
    "MISSING_ARTICLE": missing_article,
    "AMOUNT_MISMATCH": amount_mismatch,
    "DATE_INCONSISTENT": date_inconsistent,
}


# ---------------- LLM engine ----------------

_IDS = {"type": "array", "items": {"type": "string", "pattern": "^L[0-9]+-[0-9]+$"}}


def _schema(with_refs: bool) -> dict:
    props = {"title": {"type": "string"}, "description": {"type": "string"}, "evidence_line_ids": _IDS, "score": {"type": "number"}}
    if with_refs:
        props["regulation_refs"] = {"type": "array", "items": {"type": "integer"}}
    item = {"type": "object", "properties": props, "required": list(props)}
    return {"type": "object", "properties": {"findings": {"type": "array", "items": item}}, "required": ["findings"]}


_COMMON = (
    "너는 한국어 계약서 위험조항 검토 도구다. 반드시 JSON만 출력한다.\n"
    "findings 각 항목: title(짧은 제목), description(왜 위험한지 1~2문장), evidence_line_ids(근거 라인 ID, 예: L1-17), "
    "score(0~1 위험도: 0.75 이상 심각, 0.45 이상 주의).\n"
    "문서에 실제로 적힌 조항만 근거로 삼는다. 근거 라인이 없으면 보고하지 않는다. 해당 사항이 없으면 findings는 []."
)

TASKS = {
    "TOXIC_CLAUSE": "다음 유형의 독소조항(한쪽 당사자에게 일방적으로 불리한 조항)을 찾는다: {aspects}.",
    "CONTRADICTION_LLM": (
        "같은 사항(금액·기간·일자·비율·당사자)에 대해 계약서의 두 곳이 서로 다른 값이나 양립할 수 없는 의무를 정한 경우만 찾는다. "
        "한쪽에 불리할 뿐인 조항은 모순이 아니다(독소조항 검토 대상이므로 제외). "
        "evidence_line_ids에는 서로 충돌하는 두 라인 이상을 모두 넣고, description에 두 값을 함께 적는다."
    ),
    "POLICY_VIOLATION": "[내부 규정]의 기준과 계약서 조항을 대조해 규정에 어긋나는 계약 조항만 찾는다. regulation_refs에 근거가 된 [규정 n]의 n을 넣는다.",
}


def policy_query(lines: list[OcrLineDict]) -> str:
    titles = list(dict.fromkeys(m.group(1).strip() for ln in lines if (m := _ARTICLE_TITLE_RE.search(ln["text"]))))
    return " ".join(titles[:12]) or "계약보증금 지체상금 하자담보 계약해지 대가지급"


def llm_rule(rule: dict, lines: list[OcrLineDict], llm: LLMClient, policy_search: PolicySearch | None) -> list[RiskFindingDict]:
    regs: list[dict] = []
    task = TASKS[rule["code"]].format(aspects=", ".join(rule.get("params", {}).get("aspects", [])))
    prompt = "[계약서 라인 목록]\n" + format_lines(lines[:MAX_LLM_LINES])
    if rule["code"] == "POLICY_VIOLATION":
        if policy_search is None:
            return []
        regs = policy_search(policy_query(lines))[: rule.get("params", {}).get("top_k", 3)]
        if not regs:
            return []
        prompt = (
            "\n\n".join(f"[규정 {n}] {r.get('regulation_title', '')} > {r.get('path', '')}\n{r['content']}" for n, r in enumerate(regs, 1)) + "\n\n" + prompt
        )
        prompt = "[내부 규정]\n" + prompt

    output = llm.chat_json(f"{_COMMON}\n과제: {task}", prompt, _schema(bool(regs)), prompt_version=PROMPT_VERSION, name="risk_findings")
    by_id = {ln["line_id"]: ln for ln in lines}
    out = []
    for item in output.get("findings") or []:
        ids = clean_line_ids(item.get("evidence_line_ids"), by_id)
        if not ids:
            continue
        reasoning: dict[str, Any] = {"engine": "llm", "model": llm.model, "prompt_version": PROMPT_VERSION, "evidence_line_ids": ids}
        if regs:
            reasoning["regulation_refs"] = [
                {k: regs[n - 1].get(k) for k in ("chunk_id", "regulation_id", "regulation_title", "path", "node_id")}
                for n in item.get("regulation_refs") or []
                if isinstance(n, int) and 1 <= n <= len(regs)
            ]
        evidence = "\n".join(by_id[i]["text"] for i in ids)
        title = str(item.get("title") or rule["name"]).strip()
        out.append(
            _finding(
                rule,
                title,
                str(item.get("description") or "").strip(),
                line_highlights(ids, by_id),
                evidence,
                score=item.get("score", 0.5),
                reasoning=reasoning,
            )
        )
    return out


# ---------------- orchestration ----------------


def merge_findings(findings: list[RiskFindingDict]) -> list[RiskFindingDict]:
    """Same category + overlapping evidence lines = one finding; the higher score wins."""
    kept: list[RiskFindingDict] = []
    for f in sorted(findings, key=lambda f: f["score"], reverse=True):
        ids = {h["ocr_line_id"] for h in f["highlights"]}
        dup = any(k["category"] == f["category"] and (ids & {h["ocr_line_id"] for h in k["highlights"]} if ids else k["title"] == f["title"]) for k in kept)
        if not dup:
            kept.append(f)
    return kept


def detect_risks(
    lines: list[OcrLineDict],
    fields: list[dict],
    rules: list[dict] | None = None,
    llm: LLMClient | None = None,
    policy_search: PolicySearch | None = None,
) -> list[RiskFindingDict]:
    active = [r for r in (rules if rules is not None else load_rules()) if r.get("is_active", True)]
    by_code = {f["field_code"]: f for f in fields}

    def run_rules() -> list[RiskFindingDict]:
        return [f for r in active if r["engine"] == "rule" and r["code"] in RULE_ENGINE for f in RULE_ENGINE[r["code"]](r, lines, by_code)]

    def run_llm(rule: dict) -> list[RiskFindingDict]:
        assert llm is not None
        try:
            return llm_rule(rule, lines, llm, policy_search)
        except Exception:  # noqa: BLE001 - one failed LLM rule must not drop the rule-engine findings
            logger.exception("LLM risk rule %s failed", rule["code"])
            return []

    llm_rules = [r for r in active if r["engine"] == "llm" and r["code"] in TASKS] if llm is not None else []
    with ThreadPoolExecutor(max_workers=1 + len(llm_rules)) as pool:
        futures = [pool.submit(run_rules)] + [pool.submit(run_llm, r) for r in llm_rules]
        findings = [f for fut in futures for f in fut.result()]
    return merge_findings(findings)
