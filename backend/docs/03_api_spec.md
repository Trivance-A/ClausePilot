# 03. API 명세

> 2차 개정: `front 폴더`(실제 구현된 프론트엔드)가 기대하는 계약을 그대로 반영했다.
> 근거: `front 폴더/src/types/api.ts`, `src/api/*.ts`, `src/mocks/handlers.ts`.
> 1차 설계(자체 설계) 대비 경로/필드명이 다수 바뀌었으므로, 문서 하단 "1차 설계 대비 변경 사항" 참고.

## 0. 공통 규칙

- **Base path**: `/api/v1` (프론트 `VITE_API_BASE` 기본값)
- **인증**: `Authorization: Bearer <JWT>` (로그인 응답의 `access_token`). 미인증/만료 시 401 → 프론트가 자동 로그아웃 처리
- **에러 포맷**: `{"error": {"code": "...", "message": "...", "detail"?: {...}}}` — 1차 설계의 `{error_code, message}` 평면 포맷에서 **중첩 포맷으로 변경**
- **날짜**: ISO 8601. **금액은 정수(KRW)**
- **bbox**: `[x0, y0, x1, y1]`, 페이지 폭/높이 기준 **0~1 정규화** 좌표 (절대 px 아님)
- **페이지네이션**: `{items, total, page, size}` 공통 포맷
- **AI 서버 다운**: OCR/LLM 호출 불가 시 503 + `code: OCR_UNAVAILABLE` 또는 `LLM_UNAVAILABLE` → 프론트가 배너 표시

## 1. 인증

| Method | Path | 설명 |
|---|---|---|
| POST | `/auth/login` | `{email, password}` → `{access_token, token_type, user}` |
| GET | `/auth/me` | 현재 사용자 조회 (Bearer 필요) |

## 2. 문서(계약서)

| Method | Path | 설명 |
|---|---|---|
| GET | `/documents` | 쿼리: `q, status(콤마 구분), from, to, page, size` → `Paginated<DocumentListItem>` |
| POST | `/documents` | multipart: `files[], ocr_engine(auto\|paddle\|tesseract), skip_risk` → 202 `{items: UploadItem[]}` |
| GET | `/documents/{id}/status` | 5초 폴링 대상 → `{status, job}` |
| GET | `/documents/{id}/pdf` | 정규화 PDF 바이너리 |
| GET | `/documents/{id}/pages/{n}/image` | 페이지 200dpi PNG (front 폴더는 pdf.js로 PDF를 직접 렌더링해 호출하지 않지만 명세에 있어 구현) |
| GET | `/documents/{id}/export/pdf` | 하이라이트가 합성된 PDF 다운로드 |
| GET | `/documents/{id}/lines?page=` | 페이지별 OCR 라인 → `{page_no, lines}` |
| GET | `/documents/{id}` | 상세(`pages`, `extraction` 참조 포함) |
| POST | `/documents/{id}/reprocess` | `{from_step?(ocr\|extract\|risk), ocr_engine?}` → 202 `{job_id}` |
| DELETE | `/documents/{id}` | 204 |

**DocumentStatus**: `UPLOADED → NORMALIZING → OCR → EXTRACTING → RISK → DONE`, 실패 시 `FAILED`
(진행 중 상태 목록은 프론트 `IN_PROGRESS` 상수와 동일하게 유지해야 5초 폴링 로직이 맞물린다).

## 3. 추출 결과 / 검수

| Method | Path | 설명 |
|---|---|---|
| GET | `/documents/{id}/extractions` | → `ExtractionResponse{extraction_id, status, fields, color_map}` |
| PATCH | `/documents/{id}/extractions/fields/{field_code}` | `{raw_value?, normalized_value?, is_confirmed?, reviewer_note?}` → 수정된 `ExtractionField` |

**FieldCode(8개)**: `contract_name, contract_amount, guarantee_amount, contract_date, performance_due_date, guarantee_period, creditor_name, creditor_biz_no`

`color_map`은 항목별 하이라이트 색상의 **단일 소스**다 — 프론트는 색상을 하드코딩하지 않고 이 값만 사용하므로,
백엔드가 필드 색상을 바꾸면 프론트 전체에 즉시 반영된다.

## 4. 하이라이트

| Method | Path | 설명 |
|---|---|---|
| POST | `/documents/{id}/highlights` | `{field_code \| risk_finding_id, page_no, bbox}` → 201 `Highlight` (수동 생성, `origin=manual`) |
| PATCH | `/highlights/{hid}` | `{bbox, page_no?}` → 수정 후 `origin=manual`로 전환 |
| DELETE | `/highlights/{hid}` | 204 |

필드 하이라이트를 직접 지정했는데 해당 필드의 `raw_value`가 비어 있었다면(누락 필드에 사용자가 수동으로
근거를 지정한 경우), 지정된 위치의 OCR 라인 텍스트로 `raw_value`/`normalized_value`를 채운다(구현 시 참고).

## 5. 위험조항

| Method | Path | 설명 |
|---|---|---|
| GET | `/documents/{id}/risks` | → `{items, summary}` (summary는 `status != DISMISSED`만 집계) |
| PATCH | `/risks/{rid}` | `{status(OPEN\|ACKNOWLEDGED\|DISMISSED), note?}` |
| POST | `/documents/{id}/risks/rerun` | 위험조항 재탐지 → 202 `{job_id}` |

**RiskCategory**: `penalty, missing, contradiction, toxic, policy` / **Severity**: `HIGH, MEDIUM, LOW`

## 6. 보증신청 (Auto-fill)

| Method | Path | 설명 |
|---|---|---|
| POST | `/guarantee-applications` | `{document_id, guarantee_type}` → 201 `GuaranteeApplication` (추출 미완료 시 409 `INVALID_STATE`) |
| GET | `/guarantee-applications/{id}` | 조회 |
| PATCH | `/guarantee-applications/{id}` | `{form_values, status?(DRAFT\|SUBMITTED)}` |

**GuaranteeType**: `contract(계약보증), bid(입찰보증), defect(하자보증), payment(지급보증), advance(선급금보증), other(기타)`
— 유형별 `required_fields`가 다르다(예: `bid`는 보증기간이 필수 아님).

생성 시 `field_sources`에 `{field_code: {field_id, confidence, highlight_ids, page_no}}`를 채워, 프론트가
각 폼 값이 어떤 추출 필드/근거에서 왔는지 역추적하고 Viewer로 연결(`viewer_url`)할 수 있게 한다.

## 7. 규정 문서

| Method | Path | 설명 |
|---|---|---|
| GET | `/regulations` | → `{items}` (`status` PARSING/UPLOADED면 프론트가 5초 폴링) |
| POST | `/regulations` | multipart: `file, title, doc_type(정관\|규정\|지침\|매뉴얼), effective_date?` → 202 `{regulation_id, job_id, version, status}` |
| GET | `/regulations/{id}/pdf` | 근거 팝업 렌더용 PDF 바이너리 |
| GET | `/regulations/{id}/nodes/{nodeId}` | 노드 본문 → `RegNodeContent{content, bbox, chunk_ids}` |
| GET | `/regulations/{id}` | 상세 + `tree`(status=INDEXED일 때만 채움) |
| POST | `/regulations/{id}/reindex` | `{chunk_strategy?(article\|paragraph)}` → 202 `{job_id}` |
| DELETE | `/regulations/{id}` | 204, 실제 삭제 대신 `status=ARCHIVED` (소프트 삭제) |

같은 `title`로 재업로드하면 기존 버전을 `ARCHIVED`로 바꾸고 `version+1`로 새로 등록한다(버전 이력 보존).

## 8. 검색 (디버그)

| Method | Path | 설명 |
|---|---|---|
| POST | `/search` | `{query, regulation_ids?, top_k?}` → `{results, latency_ms}` |

`results[]`는 `bm25_score / vector_score / rrf_score / rerank_score`를 모두 노출한다 — 검색 파이프라인
(BM25 → Vector → RRF 결합 → rerank) 각 단계를 QA/튜닝 시 직접 검증하기 위한 개발자용 엔드포인트.

## 9. 규정 챗봇

| Method | Path | 설명 |
|---|---|---|
| GET | `/chat/sessions` | 세션 목록(최근 활동순) |
| POST | `/chat/sessions` | `{title?, regulation_ids}` → 201 `{session_id}` |
| GET | `/chat/sessions/{sid}/messages` | 세션 내 메시지 이력 |
| POST | `/chat/sessions/{sid}/messages` | `{content, stream}` — 아래 9.1 참고 |
| POST | `/chat/messages/{mid}/feedback` | `{rating(1\|-1), comment?}` → 201 |

### 9.1 메시지 전송 — SSE 스트리밍 (핵심)

`stream=false`면 `ChatMessage` JSON을 한 번에 반환하지만, **기본값(`stream=true`)은 `text/event-stream`**으로
응답한다 (`EventSource`가 아닌 `fetch` 기반 POST 스트리밍 — Authorization 헤더 전송을 위해). 이벤트 순서:

```
event: status   data: {"stage":"rewrite","rewritten_query":"..."}
event: status   data: {"stage":"retrieve","hits": 5}
event: token    data: {"text":"계약보증금은 "}       (여러 번)
event: citation data: {"ref":1,"chunk_id":"...","regulation_title":"...","path":"...","bbox":[...]}
event: done     data: {"message_id":"...","answer_status":"ANSWERED","latency_ms":2300,"suggestions"?:[...]}
```

근거 청크가 없으면(`hits: 0`) 토큰을 스트리밍하지 않고 바로 `done`에 `answer_status:"NOT_FOUND"` +
`content`(고정 안내문) + `suggestions`(유사 조항 제안)을 담아 보낸다 — **근거 없이 답변을 생성하지 않는다**는
원칙이 SSE 흐름에도 그대로 적용된다.

## 10. 관리자 / 평가

| Method | Path | 설명 |
|---|---|---|
| GET | `/admin/stats` | 문서/규정/챗봇 통계 + 평균 지연시간 |
| GET | `/admin/jobs?status=` | `Job` 목록(process_document/index_regulation/eval 공용) |
| GET | `/admin/logs/chat?...&format=csv` | 챗봇 로그 조회, `format=csv`면 CSV 다운로드 |
| POST | `/eval/run` | `{suite(extraction\|retrieval\|faithfulness\|all)}` → 202 `{run_id}` |
| GET | `/eval/runs/{id}` | 3초 폴링 대상(QUEUED/RUNNING 동안) → `EvalRun{metrics, failures}` |
| GET | `/eval/runs` | 실행 이력 (명세 외 보조 엔드포인트, 없으면 빈 목록 처리 가능) |

`EvalRun.metrics`가 성능 목표(추출 정확도 90%+, BBox 95%+, Recall@5 90%+, 근거없는 응답 5%↓)의 **실측 채널**이다.

## 11. 1차 설계 대비 변경 사항 요약

| 항목 | 1차 설계 | 2차(현재) |
|---|---|---|
| Base path | 없음(루트) | `/api/v1` |
| 인증 | 없음 | JWT Bearer 필수 |
| 에러 포맷 | `{error_code, message}` | `{error:{code,message,detail}}` |
| bbox | 절대 px | 0~1 정규화 |
| 필드 개수 | 6개(`contract_title` 등) | 8개(`contract_name`+`performance_due_date`+`creditor_biz_no`) |
| 하이라이트 | 필드/위험조항에 내장 | 독립 리소스(`/highlights/{id}`), 수동 생성/수정 지원 |
| 위험조항 카테고리 | 한글 4종 | 영문 5종(`penalty/missing/contradiction/toxic/policy`) + 상태(OPEN/ACK/DISMISSED) |
| 보증신청 | `POST .../auto-fill` 액션 | `POST /guarantee-applications` 리소스 생성 + 유형별 필수필드 |
| 규정 구조 | "장·조·항·목" 평면 텍스트 | `regulation_nodes` 트리 + 버전 관리(ARCHIVED) |
| 챗봇 응답 | 단순 JSON 동기 응답 | SSE 스트리밍(`status/token/citation/done`) |
| 검수 워크플로 | 없음 | 필드 확정(`is_confirmed`), 위험조항 확인/기각, 하이라이트 수동 보정 |
| 관리자/평가 | 없음 | `/admin/*`, `/eval/*` 신설 |
