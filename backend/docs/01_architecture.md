# 01. Backend 아키텍처

## 1. 전체 요청 흐름에서 Backend의 위치

발표자료(8페이지 시스템 구성도) 기준, Backend는 AI 파이프라인과 Frontend 사이의 오케스트레이션 및
영속성(저장) 계층을 담당한다.

### A. 계약서 분석 흐름

```
[Frontend] 문서 업로드
  → [Backend API] POST /documents  (파일 저장, documents 레코드 생성)
  → [Backend] AI 모듈 호출: parsing → OCR → extraction → bbox mapping
  → [Backend] 결과를 DB에 저장 (ocr_results, extracted_fields)
  → [Backend] AI 모듈 호출: risk_detection
  → [Backend] risk_flags 저장
  → [Frontend] GET /documents/{id}/result  (PDF Viewer, 위험조항 조회)
  → [Frontend] POST /guarantee-applications/auto-fill  (Auto-fill Demo)
```

### B. 규정 챗봇(RAG) 흐름

```
[Frontend] 규정 문서 업로드
  → [Backend API] POST /regulations  → AI 모듈 호출(구조분석/청킹/인덱싱)
  → [Backend] regulation_chunks 저장, 벡터 인덱스는 AI/RAG 계층이 관리
[Frontend] 챗봇 질문
  → [Backend API] POST /chat/messages
  → [Backend] AI 모듈(RAG) 호출 → 답변 + 근거 조항
  → [Backend] chat_messages 저장, 응답 반환
```

## 2. 레이어 구성

```
app/api/        FastAPI 라우터 (요청 검증, 응답 직렬화)
app/services/   비즈니스 로직 + AI 모듈 호출 (AI 파트가 제공하는 함수/서비스를 여기서 호출)
app/models/     SQLAlchemy ORM 모델 (DB 테이블 매핑)
app/schemas/    Pydantic 스키마 (요청/응답 DTO, AI 모듈 JSON과 매핑)
app/db/         DB 세션, 커넥션 관리
```

## 3. AI 모듈과의 결합 방식

이번 학기 규모상 AI 모듈은 별도 마이크로서비스로 분리하지 않고, **Backend 프로세스 내에서
직접 함수/모듈로 호출**하는 방식(모놀리식)을 기본안으로 한다. 이유:
- 팀 인원(3명) 규모에 비해 별도 서비스 분리는 배포/운영 복잡도만 늘어남
- OCR/LLM 호출은 외부 API 호출이 많아 네트워크 홉을 하나 더 추가할 실익이 적음

단, AI 모듈은 `app/services/ai_client.py` 형태로 **인터페이스를 분리**해두어,
추후 별도 서비스로 분리해야 할 경우 이 계층만 교체하면 되도록 설계한다 (자세한 계약은
`04_ai_integration.md` 참고).

## 4. 설계 원칙

- **비동기 처리 고려**: OCR/LLM 호출은 수 초~수십 초가 걸릴 수 있으므로, 문서 업로드는
  즉시 202(처리중) 응답 후 상태 폴링(GET /documents/{id}/status) 방식을 기본으로 한다.
  (동기 처리는 5주차 PoC에서 처리 시간을 측정한 뒤 최종 결정)
- **원문 위치 보존**: AI가 반환하는 evidence(bbox)는 그대로 DB에 저장하고 절대 유실하지 않는다.
- **실패 격리**: AI 모듈 호출 실패가 전체 요청을 죽이지 않도록 단계별 상태(`pending/parsing/ocr/extracting/done/failed`)를 문서 단위로 추적한다.

## 5. 학기 프로젝트 범위 조정

- EBIZ/KOINS 실연동 없음 → 별도 Demo용 `guarantee_applications` 테이블/화면으로 대체
- 인증/권한은 학기 프로젝트 범위에서 단순화 (기본 인증 또는 데모 계정 수준, 5주차에 확정)
