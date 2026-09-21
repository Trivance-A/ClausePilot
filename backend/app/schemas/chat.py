import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import BBox


class ChatSession(BaseModel):
    session_id: uuid.UUID
    title: str | None
    regulation_ids: list[uuid.UUID]
    created_at: datetime | None = None
    last_active_at: datetime | None = None


AnswerStatus = Literal["ANSWERED", "NOT_FOUND", "ERROR"]


class Citation(BaseModel):
    ref: int
    chunk_id: uuid.UUID
    regulation_id: uuid.UUID
    regulation_title: str
    path: str
    quoted_span: str | None = None
    page_no: int | None
    bbox: BBox | None
    node_id: uuid.UUID | None = None


class Suggestion(BaseModel):
    path: str
    title: str
    regulation_id: uuid.UUID | None = None
    node_id: uuid.UUID | None = None


class ChatMessage(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime | None = None
    answer_status: AnswerStatus | None = None
    citations: list[Citation] | None = None
    suggestions: list[Suggestion] | None = None
    latency_ms: int | None = None
    feedback: Literal[1, -1] | None = None


class CreateChatSessionRequest(BaseModel):
    title: str | None = None
    regulation_ids: list[uuid.UUID] = []


class CreateChatSessionResponse(BaseModel):
    session_id: uuid.UUID


class SendMessageRequest(BaseModel):
    content: str
    stream: bool = True


class FeedbackRequest(BaseModel):
    rating: Literal[1, -1]
    comment: str | None = None


# ---- SSE 이벤트 (POST /chat/sessions/{sid}/messages, stream=true 일 때 text/event-stream 본문) ----
# event: status  data: {"stage": "rewrite"|"retrieve"|"generate", "rewritten_query"?, "hits"?}
# event: token   data: {"text": str}
# event: citation data: Citation
# event: done    data: {"message_id", "answer_status", "latency_ms", "suggestions"?, "content"?}
# event: error   data: {"code", "message"}
class SseStatusData(BaseModel):
    stage: Literal["rewrite", "retrieve", "generate"] | str
    rewritten_query: str | None = None
    hits: int | None = None


class SseTokenData(BaseModel):
    text: str


class SseDoneData(BaseModel):
    message_id: uuid.UUID
    answer_status: AnswerStatus
    latency_ms: int
    suggestions: list[Suggestion] | None = None
    content: str | None = None  # NOT_FOUND 등 토큰 스트리밍 없이 바로 전체 내용을 줄 때만 채움


class SseErrorData(BaseModel):
    code: str
    message: str
