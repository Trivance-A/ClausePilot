from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.risk_rule import RiskRule
from app.models.user import User
from app.services.ai_client import DEFAULT_RISK_RULES, doc_risk_rules


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


def ensure_default_risk_rules() -> None:
    """빈 risk_rules 테이블을 ai_client.DEFAULT_RISK_RULES로 채우고, 03_데이터정의 §6.1 문서형 룰(ai/risk/rules.yaml)
    중 없는 code를 추가한다. 같은 code의 기존 행(PENALTY_RATE_HIGH)은 engine이 비어 있을 때만 engine·params·
    default_severity를 채운다(관리자가 바꾼 title·enabled는 유지). idempotent."""
    db = SessionLocal()
    try:
        if db.query(RiskRule).count() == 0:
            for rule in DEFAULT_RISK_RULES:
                db.add(RiskRule(**rule))
            db.flush()
        existing = {r.rule_code: r for r in db.query(RiskRule).all()}
        for rule in doc_risk_rules():
            row = existing.get(rule["rule_code"])
            if row is None:
                db.add(RiskRule(**rule))
            elif row.engine is None:
                row.engine, row.params, row.default_severity = rule["engine"], rule["params"], rule["default_severity"]
        db.commit()
    finally:
        db.close()
