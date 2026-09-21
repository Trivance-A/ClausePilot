# Backend · Data 모듈

AI 기반 계약서 검증 및 규정 챗봇 시스템의 Backend·Data 파트 작업 공간입니다.
담당 범위: 백엔드 API 구축, DB 설계·구축, 문서/OCR 결과/추출 데이터 저장, AI 기능과 프론트엔드 간 연동, 서버 환경.

## 현재 단계: 4주차 산출물 + 실제 구현

15주 개발계획 중 4~5주차는 설계 단계이며, `docs/`의 설계 문서 자체는 4주차 산출물 형식을
유지합니다. 다만 `front 폴더`가 이미 구현되어 있어 설계와 구현을 분리할 이유가 없었고,
**API 34개 엔드포인트 전부가 스텁이 아니라 실제로 동작하는 로직으로 구현되어 있습니다**
(DB 연동, JWT 인증, 파일 저장, 규칙 기반 정보추출/위험탐지, BM25+TF-IDF 하이브리드 검색,
SSE 챗봇 응답까지 — 아래 "구현 현황과 한계" 참고).

> **2차 개정**: `../front 폴더`에 이미 구현된 프론트엔드(React + TanStack Query + MSW 목 서버)가
> 있어, 이 프론트가 기대하는 실제 API 계약(`front 폴더/src/types/api.ts`, `src/mocks/handlers.ts`)에
> 맞춰 DB/API 설계를 다시 정렬했습니다. 각 설계 문서에 "1차 설계 대비 변경 사항"을 남겨뒀습니다.

## 구현 현황과 한계

외부 OCR/LLM API 키 없이도 전체 파이프라인이 end-to-end로 동작하도록, AI 모듈
(`app/services/ai_client.py`)은 **결정적(deterministic) 규칙 기반 로직**으로 구현했습니다.
실제 서비스로 확장할 때는 아래 표의 "현재 구현"을 실제 AI 모델로 교체하면 됩니다
(인터페이스는 그대로 유지).

| 기능 | 현재 구현 | 한계 |
|---|---|---|
| 문서 정규화/OCR | PyMuPDF로 PDF 텍스트 레이어 직접 추출 | 텍스트 레이어 없는 스캔본은 실제 OCR 엔진 미연동(빈 결과) |
| 계약서 정보추출 | 키워드 매칭 + 정규식 (금액/날짜/사업자번호 등) | LLM 기반 추출보다 표현 변형에 취약 |
| 위험조항 탐지 | 키워드/정규식 룰 (지체상금율, 해지조항, 면책조항 등) | 룰에 없는 패턴은 탐지 못함 |
| 규정 구조 파싱 | 정규식 기반 장/조/항 파서 | "제N장/제N조/①~⑮" 형식 외 구조는 인식 못함 |
| 규정 검색 | BM25 + TF-IDF 코사인 → RRF 결합 (질의 시점 계산, 별도 Vector DB 없음) | 임베딩 기반 의미검색보다 정확도 낮음 |
| 챗봇 답변 생성 | 검색된 조항을 그대로 인용하는 추출형 응답 | 자연스러운 문장 생성은 안 됨(LLM 미연동) |
| 성능평가(`/eval`) | 라이브 DB 데이터 기반 프록시 지표 | 정답 라벨셋이 없어 `failures[]`는 항상 빈 배열 |
| PDF 내보내기 | PyMuPDF로 하이라이트 사각형 실제 합성 | — |

데모 계정: `admin@example.com` / `admin1234` (admin), `user@example.com` / `user1234` (user) —
`SEED_DEMO_USERS=true`(기본값)일 때 앱 시작 시 자동 생성됩니다.

## 기술 스택 (4주차 결정)

- **Framework**: FastAPI (Python)
- **DB**: PostgreSQL
- **ORM**: SQLAlchemy + Alembic (마이그레이션)
- 근거: AI 파트(OCR/LLM 연동)와 언어를 통일해 연동 비용을 낮추고, FastAPI의 자동 API 문서화(Swagger)로
  Frontend·AI 파트와의 인터페이스 합의를 빠르게 진행하기 위함.

## 폴더 구조

```
backend/
├── README.md
├── REVIEW_PROMPT.md            # 다른 AI가 이번 주 산출물을 검토할 때 쓰는 프롬프트
├── docs/                        # 설계 문서 (4주차 산출물 형식 유지)
│   ├── 01_architecture.md
│   ├── 02_db_erd.md
│   ├── 03_api_spec.md
│   ├── 04_ai_integration.md
│   └── 05_tech_stack.md
├── app/                          # 실제 구현 (34개 엔드포인트 전부 동작)
│   ├── main.py
│   ├── core/                     # 설정, JWT, 에러 포맷, 파일 저장, 색상맵, 시드 계정
│   ├── api/                      # 라우터 11개
│   ├── models/                   # SQLAlchemy 모델 16개 테이블
│   ├── schemas/                  # Pydantic 요청/응답 스키마 (front 폴더 타입과 1:1)
│   └── services/                 # ai_client(규칙기반 AI 로직), pipeline(백그라운드 처리), search, eval_metrics
├── alembic/                       # DB 마이그레이션
├── tests/                         # pytest 통합 테스트 (실제 Postgres 필요)
├── Dockerfile
├── docker-compose.yml             # api + db(PostgreSQL) 실행 환경 하네스
├── .env.example
├── requirements.txt
└── requirements-dev.txt           # 테스트용 추가 의존성
```

## 실행 환경 하네스 (Docker Compose)

FastAPI(api)와 PostgreSQL(db)을 한 번에 띄우는 로컬 실행 환경입니다.

```bash
cd backend
make up        # 또는: docker compose up --build
```

- API: http://localhost:8080 (Swagger UI: http://localhost:8080/docs) — 호스트 8000/5432는 다른
  프로젝트와 충돌할 수 있어 각각 8080/5433으로 매핑했습니다(컨테이너 내부는 그대로 8000/5432).
- DB: localhost:5433 (postgres/postgres/contract_ai)
- 앱 시작 시 `Base.metadata.create_all()`로 테이블을 자동 생성하고 데모 계정을 시드합니다(개발 편의용).
  배포 환경에서는 `alembic upgrade head`로 마이그레이션을 관리하세요 (`alembic/versions/`에 초기
  마이그레이션이 이미 포함되어 있습니다. 새 마이그레이션: `alembic revision --autogenerate -m "..."`).
- 코드는 `app/` 볼륨 마운트로 즉시 반영(`--reload`)되므로, 컨테이너 재빌드 없이 개발 가능(의존성
  추가 시에는 재빌드 필요: `make build`)
- 종료: `make down`

Docker 없이 로컬에서 직접 실행하려면 `.env.example`을 `.env`로 복사해 `DATABASE_URL`을
로컬 PostgreSQL에 맞게 수정한 뒤 `uvicorn app.main:app --reload`로 실행합니다.

## 테스트 하네스 (pytest)

**실제 Postgres가 필요합니다** (DB 연동까지 검증하는 통합 테스트이기 때문):

```bash
cd backend
docker compose up -d db          # 테스트용 DB 기동 (localhost:5433)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest          # 또는: make test
```

`tests/conftest.py`가 세션 시작 시 테이블을 drop_all→create_all로 초기화하므로, 매 실행이
깨끗한 상태에서 시작합니다(해당 DB의 기존 데이터는 사라집니다 — 개발용 DB를 그대로 재사용).
총 46개 테스트가 실제 동작을 검증합니다:
- `tests/test_*.py` (auth/documents/extractions/highlights/risks/guarantee/regulations/search/chat/admin/eval):
  실제 PDF 업로드 → 백그라운드 파이프라인 완료 대기 → 추출/위험조항/검색/챗봇 응답까지 실제 값 검증
  (예: 계약금액 정규식 추출값이 실제로 350,000,000인지, 위험조항 카테고리가 penalty/toxic으로
  올바르게 분류되는지 등). `tests/pdf_fixtures.py`가 PyMuPDF로 테스트용 계약서/규정 PDF를 생성합니다.
- `tests/test_models.py`: SQLAlchemy 모델/관계 설정 정적 검증 (DB 연결 불필요)

`tests/helpers.py`에 업로드+완료대기 헬퍼가 있어 새 테스트에서 재사용할 수 있습니다.

## 참고 자료

- `../front 폴더/` — 실제 구현된 프론트엔드. `src/types/api.ts`, `src/mocks/handlers.ts`가 사실상
  가장 정확한 API 명세(구현 시 최우선 참고 대상)
- `../대본.docx` — 발표 대본 (프로젝트 목표, 15주 계획, 성능 목표 근거)
- `../발표자료.pdf` — 발표 슬라이드 (시스템 구성도 등)
- `../제안요청서_AI보증신청 및 챗봇 시스템 개발.hwp` — 원본 RFP
