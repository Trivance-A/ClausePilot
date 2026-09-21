# Backend · Data 모듈

AI 기반 계약서 검증 및 규정 챗봇 시스템의 Backend·Data 파트 작업 공간입니다.
담당 범위: 백엔드 API 구축, DB 설계·구축, 문서/OCR 결과/추출 데이터 저장, AI 기능과 프론트엔드 간 연동, 서버 환경.

## 현재 단계: 4주차 (설계 단계 1주차)

15주 개발계획 중 4~5주차는 설계 단계입니다. 4주차에는 전체 시스템 구조, DB, API 설계를
구체화합니다. 실제 구현(코딩)은 6주차부터 시작하므로, 이번 주 산출물은
**설계 문서 + DB/API 스펙 + 프로젝트 골격(스텁)** 입니다.

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
├── docs/                        # 설계 문서
│   ├── 01_architecture.md
│   ├── 02_db_erd.md
│   ├── 03_api_spec.md
│   ├── 04_ai_integration.md
│   └── 05_tech_stack.md
├── app/                          # 구현 골격 (6주차 이후 실제 로직 채움)
│   ├── main.py
│   ├── core/                     # 설정 (.env 로드)
│   ├── api/                      # 라우터
│   ├── models/                   # SQLAlchemy 모델
│   ├── schemas/                  # Pydantic 요청/응답 스키마
│   ├── db/                       # DB 연결/세션
│   └── services/                 # 비즈니스 로직 (AI 모듈 호출 등)
├── tests/                         # pytest 테스트 하네스
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

- API: http://localhost:8000 (Swagger UI: http://localhost:8000/docs)
- DB: localhost:5432 (postgres/postgres/contract_ai)
- 코드는 `app/` 볼륨 마운트로 즉시 반영(`--reload`)되므로, 컨테이너 재빌드 없이 개발 가능
- 종료: `make down`

Docker 없이 로컬에서 직접 실행하려면 `.env.example`을 `.env`로 복사해 `DATABASE_URL`을
로컬 PostgreSQL에 맞게 수정한 뒤 `uvicorn app.main:app --reload`로 실행합니다.

## 테스트 하네스 (pytest)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest          # 또는: make test
```

4주차 시점 테스트는 실제 DB 없이도 동작하도록 설계했습니다:
- `tests/test_*.py` (documents/regulations/chat/guarantee_applications): 스텁 라우트가 올바르게
  등록되어 있는지, 요청 스키마 검증(422)이 동작하는지 확인 (현재는 501을 기대값으로 검증 — 6주차에
  실제 로직이 채워지면 실제 동작/응답 스키마 검증으로 교체해야 함)
- `tests/test_models.py`: SQLAlchemy 모델/관계 설정에 오류(FK 오타 등)가 없는지 DB 연결 없이 정적 검증

## 참고 자료

- `../대본.docx` — 발표 대본 (프로젝트 목표, 15주 계획, 성능 목표 근거)
- `../발표자료.pdf` — 발표 슬라이드 (시스템 구성도 등)
- `../제안요청서_AI보증신청 및 챗봇 시스템 개발.hwp` — 원본 RFP
