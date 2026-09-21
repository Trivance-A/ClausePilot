import csv
import io
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.models.chat import ChatMessage
from app.models.document import Document
from app.models.job import Job
from app.models.regulation import Regulation, RegulationChunk
from app.models.user import User
from app.schemas.admin import AdminJob, AdminStats, AvgLatency, ChatCounts, ChatLogCitation, ChatLogItem, DocumentCounts, JobStatus, RegulationCounts
from app.schemas.common import Paginated

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(db: Session = Depends(get_db), _user: User = Depends(require_admin)):
    total = db.query(Document).count()
    done = db.query(Document).filter(Document.status == "DONE").count()
    failed = db.query(Document).filter(Document.status == "FAILED").count()

    indexed = db.query(Regulation).filter(Regulation.status == "INDEXED").count()
    chunks = db.query(RegulationChunk).count()

    since = datetime.now(timezone.utc) - timedelta(days=7)
    recent_assistant = db.query(ChatMessage).filter(ChatMessage.role == "assistant", ChatMessage.created_at >= since).all()
    not_found = sum(1 for m in recent_assistant if m.answer_status == "NOT_FOUND")
    rated = [m for m in recent_assistant if m.feedback is not None]
    thumbs_up = sum(1 for m in rated if m.feedback == 1)

    finished_jobs = (
        db.query(Job)
        .filter(Job.job_type == "process_document", Job.status == "DONE", Job.started_at.isnot(None), Job.finished_at.isnot(None))
        .all()
    )
    extract_latencies = [(j.finished_at - j.started_at).total_seconds() * 1000 for j in finished_jobs]
    all_latencies = [m.latency_ms for m in db.query(ChatMessage).filter(ChatMessage.role == "assistant", ChatMessage.latency_ms.isnot(None)).all()]

    return AdminStats(
        documents=DocumentCounts(total=total, done=done, failed=failed),
        regulations=RegulationCounts(indexed=indexed, chunks=chunks),
        chat=ChatCounts(
            messages_7d=len(recent_assistant),
            not_found_rate=round(not_found / len(recent_assistant), 4) if recent_assistant else 0.0,
            thumbs_up_rate=round(thumbs_up / len(rated), 4) if rated else 0.0,
        ),
        avg_latency_ms=AvgLatency(
            extract=int(sum(extract_latencies) / len(extract_latencies)) if extract_latencies else 0,
            chat_first_token=int(sum(all_latencies) / len(all_latencies)) if all_latencies else 0,
        ),
    )


@router.get("/jobs")
async def list_admin_jobs(status: JobStatus | None = None, db: Session = Depends(get_db), _user: User = Depends(require_admin)) -> dict[str, list[AdminJob]]:
    q = db.query(Job)
    if status:
        q = q.filter(Job.status == status)
    jobs = q.order_by(Job.started_at.desc().nullslast()).all()
    return {
        "items": [
            AdminJob(
                id=j.id, job_type=j.job_type, target_id=j.target_id, target_name=j.target_name, status=j.status,
                current_step=j.current_step, progress=j.progress, error=j.error, attempts=j.attempts,
                started_at=j.started_at, finished_at=j.finished_at,
            )
            for j in jobs
        ]
    }


def _parse_bound(value: str | None, *, end_of_day: bool) -> datetime | None:
    if not value:
        return None
    try:
        d = date.fromisoformat(value[:10])
    except ValueError:
        return None
    return datetime.combine(d, time.max if end_of_day else time.min)


@router.get("/logs/chat", response_model=None)
async def list_chat_logs(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    answer_status: str | None = None,
    page: int = 1,
    size: int = 20,
    format: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
) -> Paginated[ChatLogItem] | Response:
    q = db.query(ChatMessage).filter(ChatMessage.role == "assistant")
    if answer_status:
        q = q.filter(ChatMessage.answer_status == answer_status)
    if start := _parse_bound(from_, end_of_day=False):
        q = q.filter(ChatMessage.created_at >= start)
    if end := _parse_bound(to, end_of_day=True):
        q = q.filter(ChatMessage.created_at <= end)
    q = q.order_by(ChatMessage.created_at.desc())

    if format == "csv":
        rows = q.all()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "question", "answer_status", "citations", "feedback", "latency_ms", "created_at"])
        for m in rows:
            question = _question_for(db, m)
            writer.writerow([str(m.id), question, m.answer_status, "|".join(c.get("path", "") for c in (m.citations or [])), m.feedback, m.latency_ms, m.created_at])
        return Response(content="﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8")

    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    items = [
        ChatLogItem(
            id=m.id, session_id=m.session_id, question=_question_for(db, m), answer=m.content, answer_status=m.answer_status,
            citations=[ChatLogCitation(path=c.get("path", "")) for c in (m.citations or [])], feedback=m.feedback,
            latency_ms=m.latency_ms or 0, created_at=m.created_at,
        )
        for m in rows
    ]
    return Paginated(items=items, total=total, page=page, size=size)


def _question_for(db: Session, assistant_message: ChatMessage) -> str:
    prev = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == assistant_message.session_id, ChatMessage.role == "user", ChatMessage.created_at <= assistant_message.created_at)
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    return prev.content if prev else ""
