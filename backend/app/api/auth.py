from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User as UserModel
from app.schemas.auth import LoginRequest, LoginResponse, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == payload.email).one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise ApiError(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다")
    token = create_access_token(user.id)
    return LoginResponse(access_token=token, user=User(id=user.id, name=user.name, email=user.email, role=user.role))


@router.get("/me", response_model=User)
async def me(user: UserModel = Depends(get_current_user)):
    return User(id=user.id, name=user.name, email=user.email, role=user.role)
