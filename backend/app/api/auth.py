from fastapi import APIRouter, HTTPException

from app.schemas.auth import LoginRequest, LoginResponse, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): 사용자 조회 + 비밀번호 검증 + JWT 발급")


@router.get("/me", response_model=User)
async def me():
    raise HTTPException(status_code=501, detail="구현 대기 (6주차): Authorization 헤더의 JWT 디코드")
