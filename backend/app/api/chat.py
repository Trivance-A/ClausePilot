import uuid

from fastapi import APIRouter, HTTPException, Response

from app.schemas.chat import ChatMessage, ChatSession, CreateChatSessionRequest, CreateChatSessionResponse, FeedbackRequest, SendMessageRequest

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/sessions")
async def list_chat_sessions() -> dict[str, list[ChatSession]]:
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.post("/sessions", response_model=CreateChatSessionResponse, status_code=201)
async def create_chat_session(payload: CreateChatSessionRequest):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.get("/sessions/{session_id}/messages")
async def list_chat_messages(session_id: uuid.UUID) -> dict[str, list[ChatMessage]]:
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")


@router.post("/sessions/{session_id}/messages")
async def post_chat_message(session_id: uuid.UUID, payload: SendMessageRequest) -> Response:
    """stream=false: ChatMessage JSON 단건 응답.
    stream=true(기본값): text/event-stream, event 순서는 status(rewrite) → status(retrieve) →
    token* → citation* → done. 이벤트 형식은 app/schemas/chat.py의 Sse*Data 참고.
    """
    raise HTTPException(
        status_code=501,
        detail="구현 대기 (6주차): RAG 검색 + LLM 답변생성. 근거 청크 없으면 answer_status=NOT_FOUND",
    )


@router.post("/messages/{message_id}/feedback", status_code=201)
async def post_message_feedback(message_id: uuid.UUID, payload: FeedbackRequest) -> dict[str, bool]:
    raise HTTPException(status_code=501, detail="구현 대기 (6주차)")
