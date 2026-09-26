# 05. 기술 스택 및 서버 환경 (초안)

## 1. 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| Web Framework | FastAPI | 비동기 지원, 자동 OpenAPI 문서화 |
| DB | PostgreSQL(`pgvector/pgvector:pg16`) | jsonb로 bbox/유연 필드 저장, `vector` 확장으로 임베딩 컬럼+HNSW 인덱스 |
| ORM | SQLAlchemy 2.x + Alembic | 마이그레이션 관리 |
| Validation | Pydantic v2 | FastAPI 기본 통합 |
| 파일 저장 | 로컬 파일시스템(`storage/`, api·worker 컨테이너 공유 마운트) | 배포 환경에 따라 S3 호환 스토리지로 전환 가능하도록 경로를 서비스 계층에서 추상화 |
| 비동기 작업 큐 | Redis + RQ (`worker` 컨테이너) | Chroma/FAISS 대신 pgvector 채택에 맞춰 Vector DB 항목은 삭제, 대신 OCR/LLM/인덱싱 job 큐로 Redis+RQ 도입 |
| 임베딩 | fastembed(`paraphrase-multilingual-MiniLM-L12-v2`, 384d) | bge-m3 대신 GPU/API 키 없이 로컬 CPU로 돌아가는 경량 다국어 모델 |
| 형태소 분석 | Kiwi(`kiwipiepy`) | BM25 코퍼스용 한국어 형태소 토크나이저 |
| 인증 | JWT (`pyjwt` + `bcrypt`) | `POST /auth/login`에서 발급, `Authorization: Bearer` 검증 |
| SSE 스트리밍 | FastAPI `StreamingResponse` (`media_type="text/event-stream"`) | 챗봇 답변 스트리밍, 추가 라이브러리 불필요 |
| 로컬 실행 하네스 | Docker Compose (api + db + redis + worker) | 개발 단계부터 팀원 전원이 동일 환경에서 실행/테스트 |
| 테스트 하네스 | pytest + FastAPI TestClient | 실제 동작(추출값·위험분류·검색순위 등) 검증하는 통합 테스트 |
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
