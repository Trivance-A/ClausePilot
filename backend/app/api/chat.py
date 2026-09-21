import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.chat import ChatMessageIn, ChatMessageOut

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatSessionOut(BaseModel):
    session_id: uuid.UUID


@router.post("/sessions", response_model=ChatSessionOut)
async def create_chat_session():
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageOut)
async def post_chat_message(session_id: uuid.UUID, payload: ChatMessageIn):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): AI 파트 answer_question 호출")
