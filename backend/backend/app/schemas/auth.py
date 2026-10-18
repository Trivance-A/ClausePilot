import uuid

from pydantic import BaseModel

from app.schemas.common import Role


class User(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None = None
    role: Role


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
