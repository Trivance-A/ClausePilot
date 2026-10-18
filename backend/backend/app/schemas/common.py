"""프론트(front 폴더/src/types/api.ts) 타입과 1:1 대응되는 공용 스키마.
BBox = [x0, y0, x1, y1], 페이지 폭/높이 기준 0~1 정규화 좌표, 좌상단 원점."""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

BBox = tuple[float, float, float, float]

Role = Literal["admin", "user"]
Severity = Literal["HIGH", "MEDIUM", "LOW"]

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    detail: dict | None = None


class ApiErrorBody(BaseModel):
    error: ApiErrorDetail
