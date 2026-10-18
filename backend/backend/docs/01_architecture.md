# 01. Backend 아키텍처

> 2차 개정: `front 폴더`(실제 구현된 프론트엔드)가 이미 존재하므로, 1차 설계(추정 기반)를 프론트의
> 실제 API 계약(`front 폴더/src/types/api.ts`, `src/mocks/handlers.ts`)에 맞춰 다시 정리했다.
> 화면 목록/경로는 `front 폴더/README.md`의 "화면 ↔ 경로" 표 참고(SC-01~SC-11).

## 1. 전체 요청 흐름에서 Backend의 위치

Backend는 AI 파이프라인과 Frontend 사이의 오케스트레이션 및 영속성(저장) 계층을 담당한다.
1차 설계 대비 인증(JWT), 하이라이트/위험조항 검수, 보증신청 유형별 처리, 챗봇 SSE 스트리밍,
관리자/평가 서브시스템이 추가됐다.

### A. 계약서 분석 흐름

```
[Frontend] 로그인 → JWT 발급 (POST /auth/login)
[Frontend] 문서 업로드
  → [Backend API] POST /documents  (파일 저장, documents/jobs 레코드 생성, 202)
  → [Backend] AI 모듈 호출: normalize_to_pdf → run_ocr → extract_contract_fields
  → [Backend] 결과 저장 (pages, ocr_lines, extractions, extraction_fields, highlights)
  → [Backend] AI 모듈 호출: detect_risks
  → [Backend] risk_findings, highlights 저장
[Frontend] GET /documents/{id}/status  (5초 폴링, DONE까지)
[Frontend] GET /documents/{id}/extractions, /risks  (Viewer에서 하이라이팅 + 위험조항 표시)
[Frontend] PATCH .../extractions/fields/{code}, POST/PATCH/DELETE /highlights  (검수·수동 보정)
[Frontend] POST /guarantee-applications  (보증 유형 선택 → Auto-fill)
```

### B. 규정 챗봇(RAG) 흐름

```
[Frontend] 규정 문서 업로드
  → [Backend API] POST /regulations → AI 모듈 호출: parse_regulation_structure → chunk_regulation → index_chunks
  → [Backend] regulation_nodes, regulation_chunks 저장 (임베딩 자체는 Vector DB)
[Frontend] 챗봇 질문 (SSE)
  → [Backend API] POST /chat/sessions/{id}/messages (stream=true)
  → [Backend] AI 모듈: hybrid_search → generate_answer_stream
  → [Backend] SSE 이벤트(status/token/citation)를 그대로 중계, done 시점에 chat_messages 저장
```

### C. 관리자 / 평가 (신규)

```
[Admin Frontend] GET /admin/stats, /admin/jobs, /admin/logs/chat
  → [Backend] documents/regulations/chat_messages/jobs 집계
[Admin Frontend] POST /eval/run {suite}
  → [Backend] jobs(job_type=eval) 생성 → AI 모듈 평가 파이프라인 실행 → eval_runs 저장
[Admin Frontend] GET /eval/runs/{id}  (3초 폴링)
```

## 2. 레이어 구성

```
app/api/        FastAPI 라우터 11개 (auth, documents, extractions, highlights, risks,
                 guarantee, regulations, search, chat, admin, eval)
app/services/   비즈니스 로직 + AI 모듈 호출 (app/services/ai_client.py)
app/models/     SQLAlchemy ORM 모델 10개 (user, document, extraction, highlight, risk,
                 guarantee, regulation, chat, job, eval)
app/schemas/    Pydantic 스키마 (프론트 types/api.ts와 1:1 대응)
app/db/         DB 세션, 커넥션 관리
app/core/       설정(.env), (6주차: JWT 발급/검증 유틸리티 추가 예정)
```

## 3. AI 모듈과의 결합 방식

이번 학기 규모상 AI 모듈은 별도 마이크로서비스로 분리하지 않고, **Backend 프로세스 내에서
직접 함수/모듈로 호출**하는 방식(모놀리식)을 기본안으로 한다. 이유:
- 팀 인원(3명) 규모에 비해 별도 서비스 분리는 배포/운영 복잡도만 늘어남
- OCR/LLM 호출은 외부 API 호출이 많아 네트워크 홉을 하나 더 추가할 실익이 적음

단, AI 모듈은 `app/services/ai_client.py` 형태로 **인터페이스를 분리**해두어,
추후 별도 서비스로 분리해야 할 경우 이 계층만 교체하면 되도록 설계한다 (자세한 계약은
`04_ai_integration.md` 참고). 챗봇만은 예외적으로 **동기 함수 호출이 아닌 비동기 제너레이터**
(`generate_answer_stream`)로 연동해 SSE 스트리밍을 그대로 통과시킨다.

## 4. 설계 원칙

- **비동기 처리 고려**: OCR/LLM 호출은 수 초~수십 초가 걸릴 수 있으므로, 문서 업로드/규정 인덱싱/평가
  실행은 모두 즉시 202 응답 후 `jobs` 테이블을 통한 상태 폴링 방식을 기본으로 한다.
- **원문 위치 보존**: 필드/위험조항의 근거는 `highlights` 테이블로 독립 관리하며, 0~1 정규화 bbox를
  그대로 저장한다(px 변환은 프론트 책임). 사용자가 직접 만들거나 수정한 하이라이트는 `origin=manual`로
  구분해 AI 원본 결과와 섞이지 않게 한다.
- **검수는 되돌릴 수 있는 상태**: 필드 확정(`is_confirmed`)·위험조항 기각(`DISMISSED`)은 삭제가 아니라
  상태 전이이므로 언제든 되돌릴 수 있다.
- **실패 격리**: AI 모듈 호출 실패가 전체 요청을 죽이지 않도록 `jobs.status/current_step/error`로
  단계별 진행 상황과 실패 원인을 추적한다.
- **근거 없는 챗봇 응답 금지**: `hybrid_search` 결과가 비면 `generate_answer_stream`을 아예 호출하지
  않고 `NOT_FOUND`로 응답한다(`03_api_spec.md` 9.1절, 성능 목표: 근거 없는 응답 5% 이하).

## 5. 학기 프로젝트 범위 조정

- EBIZ/KOINS 실연동 없음 → 별도 Demo용 `guarantee_applications` 테이블/화면으로 대체
- 인증은 JWT 기반이되, 회원가입·비밀번호 재설정 등 부가 기능은 범위 밖(사전 등록된 admin/user 계정만 사용)
- Vector DB(Chroma/FAISS)와 CSV 내보내기(`/admin/logs/chat?format=csv`) 등은 로컬/파일 기반으로 단순화
