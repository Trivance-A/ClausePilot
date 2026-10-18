import json
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.db.session import SessionLocal, get_db
from app.models.chat import ChatMessage, ChatSession, Citation, MessageFeedback
from app.models.regulation import Regulation, RegulationNode
from app.models.user import User
from app.schemas.chat import (
    ChatMessage as ChatMessageOut,
)
from app.schemas.chat import (
    ChatSession as ChatSessionOut,
)
from app.schemas.chat import (
    CreateChatSessionRequest,
    CreateChatSessionResponse,
    FeedbackRequest,
    SendMessageRequest,
)
from app.services import ai_client as ai
from app.services.search import search as run_search

router = APIRouter(prefix="/chat", tags=["chat"])

NOT_FOUND_TEXT = "관련 규정을 찾지 못했습니다."


def _session_out(s: ChatSession) -> ChatSessionOut:
    return ChatSessionOut(session_id=s.id, title=s.title, regulation_ids=[uuid.UUID(r) for r in s.regulation_ids], created_at=s.created_at, last_active_at=s.last_active_at)


def _message_out(m: ChatMessage) -> ChatMessageOut:
    citations = [
        {
            "ref": c.ref, "chunk_id": c.chunk_id, "regulation_id": c.regulation_id, "regulation_title": c.regulation_title,
            "path": c.path, "quoted_span": c.quoted_span, "page_no": c.page_no, "bbox": c.bbox, "node_id": c.node_id,
        }
        for c in m.citations
    ]
    return ChatMessageOut(
        id=m.id, role=m.role, content=m.content, created_at=m.created_at, answer_status=m.answer_status,
        citations=citations if m.role == "assistant" else None, suggestions=m.suggestions, latency_ms=m.latency_ms,
        feedback=m.feedback.rating if m.feedback else None,
    )


def _save_citations(db: Session, message_id: uuid.UUID, citation_dicts: list[dict]) -> None:
    for c in citation_dicts:
        db.add(
            Citation(
                message_id=message_id,
                ref=c["ref"],
                chunk_id=uuid.UUID(c["chunk_id"]) if c.get("chunk_id") else None,
                regulation_id=uuid.UUID(c["regulation_id"]) if c.get("regulation_id") else None,
                regulation_title=c["regulation_title"],
                path=c["path"],
                quoted_span=c.get("quoted_span"),
                page_no=c.get("page_no"),
                bbox=list(c["bbox"]) if c.get("bbox") else None,
                node_id=uuid.UUID(c["node_id"]) if c.get("node_id") else None,
            )
        )


@router.get("/sessions")
async def list_chat_sessions(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, list[ChatSessionOut]]:
    sessions = db.query(ChatSession).filter(ChatSession.owner_id == user.id).order_by(ChatSession.last_active_at.desc()).all()
    return {"items": [_session_out(s) for s in sessions]}


@router.post("/sessions", response_model=CreateChatSessionResponse, status_code=201)
async def create_chat_session(payload: CreateChatSessionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = ChatSession(owner_id=user.id, title=payload.title, regulation_ids=[str(r) for r in payload.regulation_ids])
    db.add(session)
    db.commit()
    return CreateChatSessionResponse(session_id=session.id)


def _get_session_or_404(db: Session, session_id: uuid.UUID, user: User) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if not session:
        raise ApiError(404, "NOT_FOUND", "채팅 세션을 찾을 수 없습니다")
    if session.owner_id != user.id:
        raise ApiError(403, "FORBIDDEN", "본인의 세션만 조회할 수 있습니다")
    return session


@router.get("/sessions/{session_id}/messages")
async def list_chat_messages(session_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, list[ChatMessageOut]]:
    _get_session_or_404(db, session_id, user)
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    return {"items": [_message_out(m) for m in messages]}


def _suggestions(db: Session, regulation_ids: list[str]) -> list[dict]:
    q = db.query(RegulationNode).join(Regulation, RegulationNode.regulation_id == Regulation.id).filter(Regulation.status == "INDEXED", RegulationNode.level == "article")
    if regulation_ids:
        q = q.filter(RegulationNode.regulation_id.in_(regulation_ids))
    nodes = q.limit(3).all()
    return [{"path": n.path, "title": n.title or n.path, "regulation_id": str(n.regulation_id), "node_id": str(n.id)} for n in nodes]


@router.post("/sessions/{session_id}/messages")
async def post_chat_message(session_id: uuid.UUID, payload: SendMessageRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = _get_session_or_404(db, session_id, user)
    now = datetime.now(timezone.utc)
    db.add(ChatMessage(session_id=session_id, role="user", content=payload.content, created_at=now))
    session.last_active_at = now
    if not session.title:
        session.title = payload.content[:20]
    db.commit()

    regulation_ids = session.regulation_ids or None
    started = time.monotonic()
    results = run_search(db, payload.content, regulation_ids, top_k=5)
    has_results = ai.is_relevant(results)

    if not payload.stream:
        message_id = uuid.uuid4()
        if not has_results:
            content, citations, suggestions, status = NOT_FOUND_TEXT, [], _suggestions(db, session.regulation_ids), "NOT_FOUND"
        else:
            citations = []
            content = ""
            async for event in ai.generate_answer_stream(payload.content, results, message_id):
                if event["event"] == "citation":
                    citations.append(event["data"])
                elif event["event"] == "done":
                    content = event["data"]["content"]
            suggestions, status = None, "ANSWERED"
        latency_ms = int((time.monotonic() - started) * 1000)
        db.add(ChatMessage(id=message_id, session_id=session_id, role="assistant", content=content, answer_status=status, suggestions=suggestions, latency_ms=latency_ms, created_at=datetime.now(timezone.utc)))
        _save_citations(db, message_id, citations)
        db.commit()
        return _message_out(db.get(ChatMessage, message_id))

    return StreamingResponse(_stream(session_id, payload.content, results, has_results, session.regulation_ids, started), media_type="text/event-stream")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


async def _stream(session_id: uuid.UUID, query: str, results: list[ai.SearchResultDict], has_results: bool, regulation_ids: list[str], started: float):
    message_id = uuid.uuid4()
    yield _sse("status", {"stage": "rewrite", "rewritten_query": query})
    yield _sse("status", {"stage": "retrieve", "hits": len(results) if has_results else 0})

    content = NOT_FOUND_TEXT
    citations: list[dict] = []
    suggestions: list[dict] | None = None
    status = "NOT_FOUND"

    db = SessionLocal()
    try:
        if has_results:
            status = "ANSWERED"
            tokens: list[str] = []
            async for event in ai.generate_answer_stream(query, results, message_id):
                if event["event"] == "token":
                    tokens.append(event["data"]["text"])
                    yield _sse("token", event["data"])
                elif event["event"] == "citation":
                    citations.append(event["data"])
                    yield _sse("citation", event["data"])
            content = "".join(tokens)
        else:
            suggestions = _suggestions(db, regulation_ids)

        latency_ms = int((time.monotonic() - started) * 1000)
        done_data = {"message_id": str(message_id), "answer_status": status, "latency_ms": latency_ms, "suggestions": suggestions, "content": content if status == "NOT_FOUND" else None}
        yield _sse("done", done_data)

        db.add(ChatMessage(id=message_id, session_id=session_id, role="assistant", content=content, answer_status=status, suggestions=suggestions, latency_ms=latency_ms, created_at=datetime.now(timezone.utc)))
        _save_citations(db, message_id, citations)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 스트림 중 오류를 SSE error 이벤트로 알리기 위해 폭넓게 포착
        yield _sse("error", {"code": "INTERNAL_ERROR", "message": str(exc)})
    finally:
        db.close()


@router.post("/messages/{message_id}/feedback", status_code=201)
async def post_message_feedback(message_id: uuid.UUID, payload: FeedbackRequest, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> dict[str, bool]:
    message = db.get(ChatMessage, message_id)
    if not message:
        raise ApiError(404, "NOT_FOUND", "메시지를 찾을 수 없습니다")
    existing = db.query(MessageFeedback).filter(MessageFeedback.message_id == message_id).one_or_none()
    if existing:
        existing.rating, existing.comment = payload.rating, payload.comment
    else:
        db.add(MessageFeedback(message_id=message_id, rating=payload.rating, comment=payload.comment))
    db.commit()
    return {"ok": True}
