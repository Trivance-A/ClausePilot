"""모든 모델 서브모듈을 여기서 임포트해 Base.metadata에 항상 전부 등록되게 한다.
api 프로세스는 main.py가 모든 라우터를 통해 전 모델을 간접 임포트하지만, RQ worker
프로세스는 app.services.pipeline만 임포트하므로 그 안에서 참조하지 않는 모델(User,
ChatSession 등)은 등록되지 않아 FK 해석이 실패한다 — 그래서 `import app.models`
하나로 항상 전체가 등록되도록 여기서 모아둔다."""

from app.models import (  # noqa: F401
    chat,
    document,
    eval,
    extraction,
    guarantee,
    highlight,
    job,
    regulation,
    risk,
    risk_rule,
    user,
)
