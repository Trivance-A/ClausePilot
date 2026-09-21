from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User


def ensure_demo_users() -> None:
    """빈 users 테이블에 데모 계정 2개를 채운다(admin/user 역할 각 1개). idempotent."""
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        db.add(User(name="관리자", email="admin@example.com", password_hash=hash_password("admin1234"), role="admin"))
        db.add(User(name="사용자", email="user@example.com", password_hash=hash_password("user1234"), role="user"))
        db.commit()
    finally:
        db.close()
