import uuid

from pydantic import BaseModel


class ChatMessageIn(BaseModel):
    content: str


class ChatEvidence(BaseModel):
    regulation_title: str
    chapter: str | None = None
    article: str | None = None
    chunk_id: uuid.UUID


class ChatMessageOut(BaseModel):
    message_id: uuid.UUID
    content: str
    evidence: list[ChatEvidence]
