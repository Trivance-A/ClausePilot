# 03. API 명세 (초안)

FastAPI 기준, 모든 응답은 JSON. 인증은 4주차에서는 범위 밖(5주차에 데모 수준 인증 결정).

## 1. 계약서 분석

### POST /documents
계약서 파일 업로드 → 처리 파이프라인 시작 (비동기)

- Request: multipart/form-data, `file`
- Response 202:
```json
{ "document_id": "uuid", "status": "pending" }
```

### GET /documents/{document_id}/status
처리 상태 폴링

```json
{ "document_id": "uuid", "status": "ocr", "progress": 0.4 }
```

### GET /documents/{document_id}/result
추출 결과 + 위험조항 + PDF 하이라이팅용 좌표 조회

```json
{
  "document_id": "uuid",
  "normalized_pdf_url": "/files/{document_id}.pdf",
  "fields": { "contract_title": { "value": "...", "confidence": 0.95, "evidence": {"page_no":1,"bbox":[0,0,0,0]} }, "...": "..." },
  "risks": [ { "category": "독소조항", "level": "High", "description": "...", "evidence": {"page_no":3,"bbox":[0,0,0,0]} } ]
}
```

### GET /documents/{document_id}/ocr-blocks
(디버깅/QA용) 원본 OCR 블록 전체 조회

## 2. 보증신청 Auto-fill Demo

### POST /guarantee-applications/auto-fill
```json
// request
{ "document_id": "uuid" }
```
```json
// response
{ "application_id": "uuid", "filled_fields": { "contract_title": "...", "guarantee_amount": 50000000 } }
```

## 3. 규정 챗봇 (RAG)

### POST /regulations
규정/매뉴얼 문서 업로드 → 구조분석/청킹/인덱싱 (비동기)

### GET /regulations/{regulation_id}/status

### POST /chat/sessions
새 채팅 세션 생성

### POST /chat/sessions/{session_id}/messages
```json
// request
{ "content": "출장비 정산 기한이 어떻게 되나요?" }
```
```json
// response
{
  "message_id": "uuid",
  "content": "출장비는 출장 종료일로부터 7일 이내 정산해야 합니다.",
  "evidence": [ { "regulation_title": "여비규정", "chapter": "2장", "article": "5조", "chunk_id": "uuid" } ]
}
```
근거(evidence)가 비어 있으면 "관련 규정을 찾지 못했습니다" 형태로 응답 (근거 없는 응답 방지 원칙, `../../ai/docs` 설계와 일치).

## 4. 공통 규칙

- 에러 응답: `{ "error_code": "...", "message": "..." }` 형식 통일
- 페이지네이션이 필요한 목록 API는 `limit`/`offset` 쿼리 파라미터 사용
- 날짜는 ISO 8601, 금액은 정수(원 단위)

## 5. 5주차로 이월

- 인증/인가 방식 확정 (데모 계정 vs JWT 등)
- 파일 업로드 용량 제한, 허용 확장자 검증 정책
- Swagger(OpenAPI) 문서 자동 생성 확인 및 프론트엔드 공유
