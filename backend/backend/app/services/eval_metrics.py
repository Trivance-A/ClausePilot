"""EvalRun 지표 계산. 라벨링된 정답셋(gold set)이 아직 없으므로(11~13주차 테스트 단계 예정),
실측 가능한 프록시 지표를 라이브 DB 데이터로부터 계산한다 — 가짜 수치를 만들지 않는다.
failures[]는 정답셋 없이는 "expected 값"을 정의할 수 없어 항상 빈 리스트로 둔다."""

from app.models.chat import ChatMessage
from app.models.extraction import ExtractionField
from sqlalchemy.orm import Session


def compute_metrics(db: Session, suite: str) -> dict:
    metrics: dict = {}

    if suite in ("extraction", "all"):
        fields = db.query(ExtractionField).all()
        found = [f for f in fields if f.raw_value]
        if fields:
            overall = round(sum(f.confidence for f in fields) / len(fields), 4)
            by_field: dict[str, list[float]] = {}
            for f in fields:
                by_field.setdefault(f.field_code, []).append(f.confidence)
            metrics["field_accuracy"] = {
                "overall": overall,
                "by_field": {code: round(sum(vals) / len(vals), 4) for code, vals in by_field.items()},
            }
        with_highlight = [f for f in found if f.highlights]
        metrics["bbox_mapping_rate"] = round(len(with_highlight) / len(found), 4) if found else None

    if suite in ("retrieval", "all"):
        assistant_msgs = db.query(ChatMessage).filter(ChatMessage.role == "assistant").all()
        if assistant_msgs:
            answered = [m for m in assistant_msgs if m.answer_status == "ANSWERED"]
            metrics["recall_at_5"] = round(len(answered) / len(assistant_msgs), 4)

    if suite in ("faithfulness", "all"):
        answered = db.query(ChatMessage).filter(ChatMessage.role == "assistant", ChatMessage.answer_status == "ANSWERED").all()
        if answered:
            hallucinated = [m for m in answered if not m.citations]
            metrics["hallucination_rate"] = round(len(hallucinated) / len(answered), 4)

    return metrics
