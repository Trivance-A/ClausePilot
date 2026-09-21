# 05. 기술 스택 및 서버 환경 (초안)

## 1. 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| Web Framework | FastAPI | 비동기 지원, 자동 OpenAPI 문서화 |
| DB | PostgreSQL | jsonb로 bbox/유연 필드 저장 용이 |
| ORM | SQLAlchemy 2.x + Alembic | 마이그레이션 관리 |
| Validation | Pydantic v2 | FastAPI 기본 통합 |
| 파일 저장 | 로컬 파일시스템 (학기 프로젝트 범위) | 배포 환경에 따라 S3 호환 스토리지로 전환 가능하도록 경로를 서비스 계층에서 추상화 |
| Vector DB | Chroma 또는 FAISS (AI 파트와 5주차 확정) | 로컬 실행 가능, 별도 서버 불필요 |
| 로컬 실행 하네스 | Docker Compose (api + db) | 개발 단계부터 팀원 전원이 동일 환경에서 실행/테스트하기 위해 4주차에 조기 구성 |
| 테스트 하네스 | pytest + FastAPI TestClient | 6주차 구현 시작 전 라우트/모델 골격을 미리 검증 |
| 배포(안) | Docker Compose 이미지를 기반으로 확장 | 14~15주차 최종 배포 단계에서 세부 확정 |

## 2. 로컬 개발/테스트 환경

```
backend/
├── app/
│   ├── main.py           # FastAPI(app) 엔트리포인트
│   └── core/config.py    # .env 기반 설정 (pydantic-settings)
├── tests/                  # pytest 테스트 하네스
├── Dockerfile
├── docker-compose.yml      # api(FastAPI) + db(PostgreSQL) 실행 환경
├── requirements.txt
├── requirements-dev.txt    # pytest, httpx 등 테스트 의존성
└── .env.example             # DB 접속정보 등 (실제 .env는 커밋하지 않음)
```

실행: `make up` (Docker Compose) / 테스트: `make test` 또는 `pytest` (`README.md` 참고).

## 3. 4주차 결정 / 5주차 이월

- **결정**: FastAPI + PostgreSQL, 로컬 파일시스템 기반 파일 저장
- **결정**: Docker Compose(api+db) 실행 하네스, pytest 테스트 하네스 (본 세션에서 조기 구성)
- **이월**: CI(GitHub Actions 등) 연동 여부, Alembic 마이그레이션 초안, 실제 Postgres 대상 통합 테스트 추가
