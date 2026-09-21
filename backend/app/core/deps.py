import jwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User


def get_current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "인증 토큰이 없습니다")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_id = decode_access_token(token)
    except jwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", "토큰이 유효하지 않거나 만료되었습니다")
    user = db.get(User, user_id)
    if not user:
        raise ApiError(401, "UNAUTHORIZED", "사용자를 찾을 수 없습니다")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise ApiError(403, "FORBIDDEN", "관리자만 접근할 수 있습니다")
    return user
