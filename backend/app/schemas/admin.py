import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.chat import AnswerStatus

JobType = Literal["process_document", "index_regulation", "eval"]
JobStatus = Literal["QUEUED", "RUNNING", "DONE", "FAILED"]


class AdminJob(BaseModel):
    id: uuid.UUID
    job_type: JobType
    target_id: uuid.UUID
    target_name: str | None = None
    status: JobStatus
    current_step: str | None
    progress: int
    error: str | None
    attempts: int
    started_at: datetime | None
    finished_at: datetime | None


class DocumentCounts(BaseModel):
    total: int
    done: int
    failed: int


class RegulationCounts(BaseModel):
    indexed: int
    chunks: int


class ChatCounts(BaseModel):
    messages_7d: int
    not_found_rate: float
    thumbs_up_rate: float


class AvgLatency(BaseModel):
    extract: int
    chat_first_token: int


class AdminStats(BaseModel):
    documents: DocumentCounts
    regulations: RegulationCounts
    chat: ChatCounts
    avg_latency_ms: AvgLatency


class ChatLogCitation(BaseModel):
    path: str


class ChatLogItem(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    question: str
    answer: str
    answer_status: AnswerStatus
    citations: list[ChatLogCitation]
    feedback: Literal[1, -1] | None
    latency_ms: int
    created_at: datetime
