import uuid
from pathlib import Path

from app.core.config import settings


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def uploads_dir() -> Path:
    return _ensure_dir(Path(settings.storage_dir) / "uploads")


def normalized_dir() -> Path:
    return _ensure_dir(Path(settings.storage_dir) / "normalized")


def regulations_dir() -> Path:
    return _ensure_dir(Path(settings.storage_dir) / "regulations")


def save_upload(directory: Path, entity_id: uuid.UUID, filename: str, content: bytes) -> str:
    """원본 파일명 확장자를 보존해 {entity_id}{ext}로 저장하고 저장 경로(str)를 반환한다."""
    ext = Path(filename).suffix
    path = directory / f"{entity_id}{ext}"
    path.write_bytes(content)
    return str(path)
