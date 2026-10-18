from datetime import datetime, timezone


def utcnow() -> datetime:
    """SQLAlchemy Column(default=...)로 쓰는 timezone-aware UTC now.
    naive datetime.utcnow()는 timestamptz 컬럼에 저장될 때 세션 타임존으로 해석될 수 있어 피한다."""
    return datetime.now(timezone.utc)
