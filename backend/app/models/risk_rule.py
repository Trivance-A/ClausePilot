import uuid

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RiskRule(Base):
    """관리자가 코드 수정 없이 위험조항 탐지 규칙을 조정할 수 있도록 DB로 뺀 규칙 테이블
    (03_API_명세서 설계의 risk_rules 대응). rule_type:
    - field_missing: field_code 값이 비어있으면 base_score로 탐지
    - keyword: ocr_lines 중 keywords 중 하나라도 포함된 줄마다 base_score로 탐지
    - penalty_rate: keywords가 등장한 줄에서 퍼센트/천분율을 정규식으로 파싱해 rate/0.3 비율로 score 계산
    - period_contradiction: 보증기간 시작>종료 같은 구조적 모순 검사(값 비교라 키워드 매칭이 아님,
      base_score를 그대로 점수로 사용). 실제 판정 로직은 ai_client.detect_risks에 남아있고,
      이 행은 그 규칙의 존재와 점수를 문서화·조정하기 위한 용도다.
    severity는 score로부터 통일된 공식으로 계산한다: score>=0.75 HIGH, >=0.45 MEDIUM, 그 외 LOW."""

    __tablename__ = "risk_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_code: Mapped[str] = mapped_column(String, unique=True)
    category: Mapped[str] = mapped_column(String)  # penalty | missing | contradiction | toxic | policy
    rule_type: Mapped[str] = mapped_column(String)  # field_missing | keyword | penalty_rate | period_contradiction
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    field_code: Mapped[str | None] = mapped_column(String, nullable=True)
    base_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
