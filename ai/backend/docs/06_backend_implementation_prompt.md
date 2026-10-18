# 06. 백엔드 구현 AI 프롬프트

이 문서는 `front 폴더`(Front-End 레포)에 맞춰 `backend/`를 실제로 구현시킬 때, 새 AI 세션(Claude Code 등)에
그대로 붙여넣어 쓰는 **실행용 프롬프트**입니다. 아래 구분선(`---`) 아래 내용을 복사해서 사용하세요.

## 왜 이 문서가 필요한가

`backend/docs/03_api_spec.md`와 `02_db_erd.md`는 4주차 설계 초안 수준이라 매우 단순합니다
(인증 없음, 페이지네이션 없음, 필드 수정/하이라이트 CRUD 없음 등). 반면 `front 폴더`는 이미
5~6주차 수준으로 구현되어 있고, 실제로 호출하는 API 계약이 `front 폴더/src/types/api.ts`,
`src/api/*.ts`, `src/mocks/handlers.ts`에 훨씬 상세하게 코드로 박혀 있습니다.

**따라서 백엔드를 새로 설계하지 말고, 프론트엔드가 이미 요구하는 계약에 맞춰 구현해야 합니다.**
이 프롬프트는 그 괴리를 명시하고, 프론트 소스를 1차 사실 기준(source of truth)으로 삼도록 AI에게 지시합니다.

---

## 프롬프트 시작 (아래 복사)

너는 ClausePilot(AI 기반 계약서 검증 및 규정 챗봇 시스템) 프로젝트의 백엔드를 구현하는 작업을 맡았다.
모노레포 루트는 `web framwork/`이고, 프론트엔드는 `front 폴더/`, 백엔드는 `backend/`에 있다.

### 0. 먼저 읽어야 할 파일 (작업 전 필수)

1. `front 폴더/src/types/api.ts` — **모든 요청/응답 타입의 1차 사실 기준**. 여기 정의된 필드명·타입을 그대로 Pydantic 스키마로 옮길 것.
2. `front 폴더/src/api/*.ts` (auth, documents, extractions, risks, guarantee, regulations, chat, admin) — 각 도메인이 실제로 호출하는 엔드포인트, 메서드, 쿼리 파라미터, invalidate 패턴.
3. `front 폴더/src/mocks/handlers.ts` + `front 폴더/src/mocks/fixtures.ts` — 각 엔드포인트의 **정확한 동작**(상태 전이, 에러 코드, 페이지네이션, 필터링 로직)이 이미 목업으로 구현되어 있다. 실제 백엔드 동작을 설계할 때 이 파일의 로직을 참고 사양서로 취급할 것.
4. `front 폴더/src/lib/sse.ts`, `src/lib/api.ts` — SSE 이벤트 포맷(`event: <type>\ndata: <json>\n\n`), 에러 응답 포맷(`{error:{code,message,detail}}`), 401 자동 로그아웃, 503(`LLM_UNAVAILABLE`/`OCR_UNAVAILABLE`) 배너 트리거 조건.
5. `backend/app/`, `backend/docs/01_architecture.md` ~ `05_tech_stack.md` — 기존 스켈레톤과 설계 원칙(레이어 구성, 비동기 상태 폴링, evidence 보존, AI 모듈 인터페이스 분리).
6. `docs/01_system_architecture.md`, `docs/02_data_flow.md` — 팀 전체 공유 아키텍처/데이터 흐름 원칙.

**주의**: `backend/docs/02_db_erd.md`, `03_api_spec.md`는 초안이라 프론트 계약과 다르다(특히 인증, 페이지네이션,
하이라이트, 위험조항 상태, 관리자/평가 API가 빠져 있다). 충돌 시 **프론트 타입(`types/api.ts`)과 mock
핸들러(`mocks/handlers.ts`)를 우선**하고, 작업 마지막에 `02_db_erd.md`/`03_api_spec.md`를 실제 구현에 맞게 갱신한다.

### 1. 구현 원칙

- 기존 `backend/app/` 스켈레톤(레이어 구성: `api/` `services/` `models/` `schemas/` `db/`)을 **재사용/확장**한다. 처음부터 새로 만들지 않는다.
- API 라우팅/스키마는 `front 폴더/src/types/api.ts`의 타입과 필드명을 그대로 따른다(camelCase가 아니라 프론트가 쓰는 snake_case 그대로).
- 에러 응답은 전부 `{ "error": { "code": "...", "message": "...", "detail": {...}? } }` 형식.
- 목록 API는 프론트가 기대하는 `Paginated<T> = { items, total, page, size }` 형태로 응답 (`GET /documents`, `GET /admin/logs/chat`).
- 인증: 프론트는 `Authorization: Bearer <token>` 헤더를 보내고, 401을 받으면 자동 로그아웃한다. 학기 프로젝트 범위이므로 단순 JWT(또는 서명된 opaque 토큰) + 비밀번호 해시(bcrypt/passlib) 정도로 충분하다. 목업처럼 "admin으로 시작하는 이메일 = admin 역할" 같은 하드코딩은 하지 말고 `users` 테이블의 `role` 컬럼으로 관리한다.
- 장시간 작업(OCR/LLM/인덱싱)은 기존 설계 원칙대로 **즉시 202 응답 + 상태 폴링**(FastAPI `BackgroundTasks`로 시작, 필요시 5주차 이후 큐 전환)으로 처리한다.
- AI 파이프라인 호출은 `backend/app/services/ai_client.py` 인터페이스를 통해서만 하고, 실제 AI 파트 구현이 아직 없다면 **결정적인(deterministic) 스텁 구현**을 넣어 API 계약과 상태 전이만이라도 동작하게 한다(프론트 mock의 `fixtures.ts` 패턴을 참고해도 좋다). AI 모듈 내부 로직을 여기서 직접 구현하지 말 것 — 인터페이스 뒤에 숨겨둘 것.
- evidence(bbox/좌표)는 유실 없이 그대로 DB에 저장한다. RAG 챗봇은 근거 청크가 없으면 `NOT_FOUND` 상태로 응답하고 추측 답변을 생성하지 않는다(`docs/02_data_flow.md` 원칙).

### 2. 구현해야 할 엔드포인트 전체 목록

(요청/응답 스키마는 `front 폴더/src/types/api.ts`의 동일 이름 타입을 참고)

**Auth**
- `POST /api/v1/auth/login` `{email, password}` → `LoginResponse{access_token, token_type, user}`
- `GET /api/v1/auth/me` → `User`

**Documents**
- `GET /api/v1/documents?q&status&from&to&page&size` → `Paginated<DocumentListItem>`
- `POST /api/v1/documents` (multipart: `files[]`, `ocr_engine`, `skip_risk`) → 202 `UploadResponse{items}`
- `GET /api/v1/documents/{id}` → `DocumentDetail`
- `GET /api/v1/documents/{id}/status` → `DocumentStatusResponse{status, job}` (폴링용, `job.progress`/`current_step` 포함)
- `GET /api/v1/documents/{id}/pdf` → 정규화된 PDF 바이너리
- `GET /api/v1/documents/{id}/export/pdf` → 하이라이트가 그려진 PDF 다운로드
- `GET /api/v1/documents/{id}/lines?page=` → `LinesResponse` (OCR 라인)
- `POST /api/v1/documents/{id}/reprocess` `{from_step?, ocr_engine?}` → 202 `{job_id}`
- `DELETE /api/v1/documents/{id}` → 204

**Extraction / Highlight**
- `GET /api/v1/documents/{id}/extractions` → `ExtractionResponse{extraction_id, status, fields, color_map}` (`color_map`이 색상의 단일 소스 — 프론트는 하드코딩 안 함)
- `PATCH /api/v1/documents/{id}/extractions/fields/{field_code}` `FieldPatch` → `ExtractionField` (필드 전체 확정 시 `extraction.status`를 `CONFIRMED`로 갱신)
- `POST /api/v1/documents/{id}/highlights` `CreateHighlightBody`(`field_code` 또는 `risk_finding_id` 중 하나) → 201 `Highlight`
- `PATCH /api/v1/highlights/{hid}` `{bbox, page_no}` → `Highlight`
- `DELETE /api/v1/highlights/{hid}` → 204

**Risk**
- `GET /api/v1/documents/{id}/risks` → `RisksResponse{items, summary}` (summary는 `DISMISSED` 제외 집계)
- `PATCH /api/v1/risks/{rid}` `{status, note?}` → `RiskFinding`
- `POST /api/v1/documents/{id}/risks/rerun` → 202 `{job_id}`

**Guarantee Auto-fill**
- `POST /api/v1/guarantee-applications` `{document_id, guarantee_type}` → 201 `GuaranteeApplication` (분석 미완료 문서면 409 `INVALID_STATE`)
- `GET /api/v1/guarantee-applications/{id}` → `GuaranteeApplication`
- `PATCH /api/v1/guarantee-applications/{id}` `{form_values, status?}` → `GuaranteeApplication`

**Regulations**
- `GET /api/v1/regulations` → `{items: RegulationListItem[]}`
- `POST /api/v1/regulations` (multipart: `file, title, doc_type, effective_date?`) → 202 `{regulation_id, job_id, version, status}` (같은 title 재업로드 시 이전 버전은 `ARCHIVED`)
- `GET /api/v1/regulations/{id}` → `RegulationDetail`(+ 구조 트리 `tree`)
- `GET /api/v1/regulations/{id}/pdf` → PDF 바이너리
- `GET /api/v1/regulations/{id}/nodes/{nodeId}` → `RegNodeContent`
- `POST /api/v1/regulations/{id}/reindex` `{chunk_strategy?}` → 202 `{job_id}`
- `DELETE /api/v1/regulations/{id}` → 204 (soft delete: `status=ARCHIVED`)

**Chat (RAG, SSE)**
- `GET /api/v1/chat/sessions` → `{items: ChatSession[]}`
- `POST /api/v1/chat/sessions` `{title?, regulation_ids}` → 201 `{session_id}`
- `GET /api/v1/chat/sessions/{sid}/messages` → `{items: ChatMessage[]}`
- `POST /api/v1/chat/sessions/{sid}/messages` `{content, stream?}` →
  - `stream:false`면 동기 JSON `ChatMessage` 반환
  - 그 외에는 `text/event-stream`으로 `status`(rewrite/retrieve) → `token`(스트리밍 토큰) → `citation`(인용 등장 시) → `done`(message_id, answer_status, latency_ms, suggestions) 이벤트 순서로 전송. 근거 청크가 없으면 `answer_status:"NOT_FOUND"` + `suggestions`(유사 조항 제안) 제공, 답변 생성 금지.
- `POST /api/v1/chat/messages/{mid}/feedback` `{rating: 1|-1, comment?}` → 201

**Admin / Eval** (관리자 role만 접근 가능하도록 인가 추가)
- `GET /api/v1/admin/stats` → `AdminStats`
- `GET /api/v1/admin/jobs?status=` → `{items: AdminJob[]}`
- `GET /api/v1/admin/logs/chat?from&to&answer_status&page&size&format=csv` → `Paginated<ChatLogItem>` 또는 CSV
- `POST /api/v1/eval/run` `{suite}` → 202 `{run_id}`
- `GET /api/v1/eval/runs/{id}` → `EvalRun` (RUNNING이면 프론트가 3초마다 재폴링)
- `GET /api/v1/eval/runs` → `{items: EvalRun[]}` (명세 외 보조 엔드포인트, 없어도 프론트는 빈 배열로 폴백하지만 구현 권장)

### 3. DB 스키마 확장

`backend/docs/02_db_erd.md`의 테이블을 베이스로 하되, 위 API 계약을 만족하려면 최소한 다음을 추가/보강해야 한다:
- `users` (id, email, password_hash, name, role, created_at)
- `documents`: `original_name`, `original_format`, `source_type`, `page_count`, `status`(UPLOADED/NORMALIZING/OCR/EXTRACTING/RISK/DONE/FAILED), `risk_summary` 집계 또는 조회 시 계산
- `extractions`(문서 1:1) + `extracted_fields`: `field_code`, `raw_value`, `normalized_value`(jsonb), `confidence`, `mapping_method`, `is_confirmed`, `reviewer_note`
- `highlights`: `field_id` 또는 `risk_finding_id` FK(nullable, 둘 중 하나), `page_no`, `bbox`(jsonb), `origin`(auto/manual), `ocr_line_id`
- `risk_findings`: `category`, `severity`, `score`, `rule_code`, `title`, `description`, `evidence_text`, `status`(OPEN/ACKNOWLEDGED/DISMISSED), `note`
- `guarantee_applications`: `guarantee_type`, `status`(DRAFT/SUBMITTED), `form_values`(jsonb), `field_sources`(jsonb)
- `regulations` + `regulation_chunks`(트리 구조 위한 `parent_id`/`level`/`number`/`path` 포함) — 기존 ERD의 챕터/조/항 구조를 `RegNode` 트리로 직렬화할 수 있게 보강
- `chat_sessions` / `chat_messages`: `answer_status`, `citations`(jsonb), `suggestions`(jsonb), `latency_ms`, `feedback`
- `jobs`(공용 잡 테이블): `job_type`, `target_id`, `status`, `current_step`, `progress`, `error`, `attempts`, `started_at`, `finished_at` — 문서 처리/규정 인덱싱/평가 실행 상태 폴링에 공통 사용
- `eval_runs`: `suite`, `status`, `metrics`(jsonb), `failures`(jsonb)

컬럼 타입 확정, 인덱스, Alembic 마이그레이션은 실제 구현 시 결정해도 된다.

### 4. 작업 순서 제안

1. `app/models/`에 위 테이블 추가(SQLAlchemy 2.x), Alembic 초기 마이그레이션 생성.
2. `app/schemas/`에 `types/api.ts`와 1:1 매핑되는 Pydantic 스키마 작성.
3. `app/api/`에 도메인별 라우터 작성(기존 `documents.py`/`chat.py`/`regulations.py`/`guarantee_applications.py` 확장 + `auth.py`/`extractions.py`/`risks.py`/`highlights.py`/`admin.py`/`eval.py` 신규).
4. `app/services/ai_client.py`에 정의된 인터페이스(`normalize_to_pdf`, `run_ocr`, `extract_contract_fields`, `detect_risks`, `build_regulation_index`, `answer_question`)를 우선 결정적 스텁으로 구현해 API가 end-to-end로 동작하게 한다.
5. `backend/tests/`에 새 엔드포인트별 pytest 추가(기존 `test_documents.py` 등 패턴 따름). `pytest`로 DB 없이도 라우트/스키마 정합성 검증.
6. `front 폴더`를 `npm run dev`(mock 아님, 실제 백엔드 프록시)로 띄우고 로그인 → 문서 업로드 → 뷰어 → 챗봇 → 관리자 대시보드까지 수동으로 눌러보며 실제 연동 확인.
7. 마지막에 `backend/docs/02_db_erd.md`, `03_api_spec.md`를 실제 구현된 스키마/엔드포인트에 맞게 갱신.

### 5. 하지 말 것

- `front 폴더` 쪽 코드는 수정하지 않는다(이미 구현 완료 상태이며, 여기서는 백엔드만 프론트 계약에 맞춘다).
- AI 모듈(OCR/LLM/RAG)의 실제 정확도 로직을 여기서 새로 설계하지 않는다 — `ai_client.py` 인터페이스 뒤에 스텁만 두고, 실제 구현은 AI 파트 담당 영역으로 남긴다.
- `backend/docs/03_api_spec.md`의 옛 초안 엔드포인트(`/guarantee-applications/auto-fill` 등)를 그대로 구현하지 않는다 — 프론트가 실제로 호출하는 이름(`POST /guarantee-applications`)을 따른다.

## 프롬프트 끝
