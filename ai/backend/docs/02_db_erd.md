# 02. DB ERD 설계

> 2차 개정: `front 폴더`(실제 구현된 프론트엔드)의 API 계약(`src/types/api.ts`, `src/mocks/handlers.ts`)에 맞춰
> 테이블 구조를 다시 설계했다. 1차 설계 대비 달라진 점은 문서 하단 "1차 설계 대비 변경 사항" 참고.

## 1. 테이블 개요

| 테이블 | 목적 |
|---|---|
| `users` | 로그인 사용자 (admin/user) |
| `documents` | 업로드된 계약서 메타데이터, 처리 상태 |
| `pages` | 문서 페이지 메타(크기, 회전, 텍스트 레이어 여부) — PDF 렌더링에 필요 |
| `ocr_lines` | OCR/텍스트 추출 결과 (줄 단위, bbox 포함) |
| `extractions` | 문서당 1개, 추출 세션의 상태(AUTO/REVIEWED/CONFIRMED) |
| `extraction_fields` | 계약서 주요정보 8개 필드의 값 + 검수 상태 |
| `highlights` | PDF 하이라이팅 좌표 — 필드 또는 위험조항에 종속되는 독립 리소스 |
| `risk_findings` | 위험조항 탐지 결과 |
| `guarantee_applications` | 보증신청 Auto-fill Demo |
| `regulations` | 업로드된 규정/매뉴얼 메타데이터 (버전 관리) |
| `regulation_nodes` | 장·조·항·목 트리 |
| `regulation_chunks` | RAG 검색 대상 청크 |
| `chat_sessions` / `chat_messages` | 규정 챗봇 대화 (근거 조항, 피드백 포함) |
| `jobs` | 문서처리/규정인덱싱/평가 실행 공용 비동기 작업 테이블 |
| `eval_runs` | 정확도/검색 성능 평가 실행 결과 |

## 2. 테이블 상세

### users
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| name | varchar | |
| email | varchar, unique, nullable | |
| password_hash | varchar | |
| role | varchar | admin \| user |
| created_at | timestamptz | |

### documents
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| owner_id | UUID (FK → users.id) | |
| original_name | varchar | |
| original_format | varchar | hwp/hwpx/pdf/xlsx 등 |
| source_type | varchar, nullable | native \| scan \| mixed (파싱 후 판별) |
| normalized_pdf_path | varchar, nullable | |
| page_count | int, nullable | |
| status | varchar | UPLOADED→NORMALIZING→OCR→EXTRACTING→RISK→DONE, 또는 FAILED |
| failure_step | varchar, nullable | 실패 시 어느 단계였는지 |
| failure_reason | varchar, nullable | |
| created_at / updated_at | timestamptz | |

`risk_summary`(HIGH/MEDIUM/LOW 개수)는 컬럼으로 저장하지 않고, `risk_findings`에서 조회 시점에
`status != DISMISSED` 조건으로 집계한다 (프론트 `GET /documents`, `GET /documents/{id}/risks` 응답 동일 소스 유지).

### pages
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK) | |
| page_no | int | |
| width_pt / height_pt | float | PDF 포인트 단위 |
| rotation | int | 0/90/180/270 |
| has_text_layer | boolean | false면 스캔 이미지 페이지(OCR 필요) |

### ocr_lines
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK) | |
| page_no | int | |
| line_id | varchar | 페이지 내 식별자 (예: `L1-2`) — highlights.ocr_line_id가 참조 |
| text | text | |
| bbox | jsonb | `[x0,y0,x1,y1]`, 페이지 폭/높이 기준 **0~1 정규화** 좌표 |
| confidence | float | |
| source | varchar | pdf_text \| paddle \| tesseract 등 |
| table_cell | varchar, nullable | 표 셀 위치(예: `r1,c1`), 표가 아니면 null |

> **1차 설계 대비 변경**: bbox를 절대 px 좌표로 뒀던 1차 설계와 달리, 프론트 `PdfViewer`가 0~1 정규화 좌표만
> 다루므로 모든 bbox(ocr_lines/highlights/regulation_nodes)는 정규화 좌표로 통일한다.

### extractions / extraction_fields
| 컬럼 (extractions) | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK, unique) | 문서당 1건 |
| status | varchar | AUTO \| REVIEWED \| CONFIRMED |
| model_name | varchar | |
| created_at | timestamptz | |

| 컬럼 (extraction_fields) | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| extraction_id | UUID (FK) | |
| field_code | varchar | `contract_name`\|`contract_amount`\|`guarantee_amount`\|`contract_date`\|`performance_due_date`\|`guarantee_period`\|`creditor_name`\|`creditor_biz_no` |
| label | varchar | 필드 한글 라벨 |
| color_key | varchar, nullable | 하이라이팅 색상 매핑 키 |
| raw_value | text, nullable | OCR 원문 그대로 |
| normalized_value | jsonb, nullable | `{amount}`\|`{date}`\|`{start,end}`\|`{text}` |
| confidence | float | |
| mapping_method | varchar | exact \| fuzzy \| llm_ref \| manual \| none |
| is_confirmed | boolean | 검수 완료 여부 (전체 필드 true → extractions.status=CONFIRMED) |
| reviewer_note | text, nullable | |

> **1차 설계 대비 변경**: 필드 6개(`contract_title` 포함) → **8개**로 확장(`contract_name`으로 개명,
> `performance_due_date`·`creditor_biz_no` 추가). 검수 워크플로(`is_confirmed`, `reviewer_note`,
> `extractions.status`)를 1차 설계에는 없던 개념으로 새로 추가 — 프론트가 AI 추출 결과를 사람이
> 검수/수정하는 화면(SC-04)을 전제로 하기 때문.

### highlights
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK) | 조회 편의용 비정규화 컬럼 |
| extraction_field_id | UUID (FK, nullable) | 필드 근거 하이라이트일 때 |
| risk_finding_id | UUID (FK, nullable) | 위험조항 근거 하이라이트일 때 |
| page_no | int | |
| bbox | jsonb | `[x0,y0,x1,y1]` 0~1 정규화 |
| origin | varchar | auto(AI 생성) \| manual(사용자 지정/수정) |
| ocr_line_id | varchar, nullable | `ocr_lines.line_id` 참조(느슨한 참조, 페이지 범위 내 식별자) |

CHECK 제약: `extraction_field_id`와 `risk_finding_id` 중 정확히 하나만 NOT NULL.

> **1차 설계 대비 변경**: 1차 설계에서는 bbox를 `extracted_fields`/`risk_flags`의 컬럼으로 뒀지만,
> 프론트가 하이라이트를 **독립적으로 생성/수정/삭제**(`POST .../highlights`, `PATCH/DELETE /highlights/{id}`)
> 하고 필드 하나가 여러 하이라이트를 가질 수 있어(예: 보증금액이 본문+표에 중복 등장) 별도 테이블로 분리했다.

### risk_findings
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK) | |
| category | varchar | penalty \| missing \| contradiction \| toxic \| policy |
| severity | varchar | HIGH \| MEDIUM \| LOW |
| score | float | |
| rule_code | varchar, nullable | 룰 기반 탐지 시 규칙 코드 |
| title | varchar | |
| description | text | |
| evidence_text | text, nullable | |
| llm_reasoning | jsonb, nullable | LLM 판단 근거(조항/사유/기준 등 자유 형식) |
| status | varchar | OPEN \| ACKNOWLEDGED \| DISMISSED |
| note | text, nullable | 검토자 메모 |

> **1차 설계 대비 변경**: 카테고리를 한글 4종(독소조항/과도한위약금/필수항목누락/내용모순)에서
> 영문 5종(penalty/missing/contradiction/toxic/policy)으로, 상태값(OPEN/ACKNOWLEDGED/DISMISSED)과
> `score`/`rule_code`/`llm_reasoning`을 새로 추가 — 위험조항도 검수 워크플로(확인/기각) 대상이기 때문.

### guarantee_applications
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK) | |
| guarantee_type | varchar | contract \| bid \| defect \| payment \| advance \| other |
| status | varchar | DRAFT \| SUBMITTED |
| form_values | jsonb | GuaranteeFormValues 스냅샷 (사용자가 수정 가능) |
| field_sources | jsonb | `{field_code: {field_id, confidence, highlight_ids, page_no}}` |
| required_fields | jsonb | guarantee_type별 필수 필드 목록 |
| created_at / updated_at | timestamptz | |

`viewer_url`은 저장하지 않고 응답 시 `document_id` 기반으로 생성한다(`/documents/{id}/viewer?field=...`).

> **1차 설계 대비 변경**: "Auto-fill"이 별도 액션(`POST /auto-fill`)이 아니라 **보증서 유형(guarantee_type)별
> 신청서 생성**(`POST /guarantee-applications`)이며, 이후 사용자가 폼을 수정해 제출(SUBMITTED)하는
> 라이프사이클이 있다는 점이 1차 설계에는 반영되지 않았다.

### regulations / regulation_nodes / regulation_chunks
| 컬럼 (regulations) | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| title | varchar | |
| doc_type | varchar | 정관 \| 규정 \| 지침 \| 매뉴얼 |
| version | int | 동일 title 재업로드 시 +1, 이전 버전은 ARCHIVED |
| status | varchar | UPLOADED \| PARSING \| INDEXED \| FAILED \| ARCHIVED |
| source_pdf_path | varchar, nullable | |
| chunk_count | int, nullable | |
| effective_date | date, nullable | |
| error | varchar, nullable | |
| created_at | timestamptz | |

| 컬럼 (regulation_nodes) | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| regulation_id | UUID (FK) | |
| parent_id | UUID (FK, self, nullable) | 트리 구조 |
| level | varchar | chapter\|section\|article\|paragraph\|item\|subitem\|appendix |
| number | varchar | 예: "12", "①" |
| title | varchar, nullable | |
| path | varchar | 표시용 경로, 예: `제3장>제12조(계약보증금)>제2항` |
| page_no | int, nullable | |
| bbox | jsonb, nullable | |
| content | text | 해당 노드의 본문 |
| sort_order | int | 형제 노드 순서 |

| 컬럼 (regulation_chunks) | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| regulation_id | UUID (FK) | |
| node_id | UUID (FK, nullable) | 주로 대응되는 노드 |
| content | text | |
| embedding_ref | varchar, nullable | Vector DB 인덱스 참조 ID |

> **1차 설계 대비 변경**: "장·조·항·목"을 평면 청크 테이블로만 뒀던 1차 설계와 달리, 프론트가 트리 UI
> (`GET /regulations/{id}` → `tree`, `GET /regulations/{id}/nodes/{nodeId}`)를 요구하므로
> `regulation_nodes`를 자기참조 트리로 분리하고 `regulation_chunks`가 이를 참조하는 구조로 바꿨다.
> 버전 관리(`version`, `ARCHIVED`)도 새로 추가.

### chat_sessions / chat_messages
| 컬럼 (chat_sessions) | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| owner_id | UUID (FK) | |
| title | varchar, nullable | |
| regulation_ids | jsonb | 검색 범위를 좁힐 규정 id 목록(빈 배열=전체) |
| created_at / last_active_at | timestamptz | |

| 컬럼 (chat_messages) | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| session_id | UUID (FK) | |
| role | varchar | user \| assistant |
| content | text | |
| answer_status | varchar, nullable | ANSWERED \| NOT_FOUND \| ERROR (assistant만) |
| citations | jsonb | Citation[] (근거 조항, chunk_id/path/bbox 포함) |
| suggestions | jsonb, nullable | NOT_FOUND일 때 유사 조항 제안 |
| latency_ms | int, nullable | |
| feedback | int, nullable | 1(도움됨) \| -1(도움안됨) \| null |
| created_at | timestamptz | |

> **1차 설계 대비 변경**: `evidence_chunk_ids`만 저장하던 1차 설계와 달리, 프론트가 citation마다
> `regulation_title`/`path`/`quoted_span`/`bbox`를 그대로 렌더링하므로 citations를 완전한 구조로 저장한다.
> 답변 스트리밍(SSE)과 사용자 피드백(`feedback`)도 새로 추가.

### jobs
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| job_type | varchar | process_document \| index_regulation \| eval |
| target_id | UUID | documents.id / regulations.id / eval_runs.id 중 하나(다형 참조, FK 제약 없음) |
| target_name | varchar, nullable | 목록 화면 표시용 캐시 |
| status | varchar | QUEUED \| RUNNING \| DONE \| FAILED |
| current_step | varchar, nullable | normalize\|ocr\|extract\|risk 등 |
| progress | int | 0~100 |
| error | varchar, nullable | |
| attempts | int | 재시도 횟수 |
| started_at / finished_at | timestamptz, nullable | |

> **1차 설계 대비 변경**: 문서 상태만 `documents.status`로 추적하던 1차 설계를 확장해, 문서처리·규정인덱싱·
> 평가실행을 **공용 Job 테이블**로 통합 관리한다 — 프론트 관리자 대시보드(`GET /admin/jobs`)가 세 종류를
> 한 화면에서 보여주기 때문. `documents.status`는 여전히 유지하되(목록 화면 조회 최적화용),
> 진행률/에러 상세는 `jobs`가 단일 소스다.

### eval_runs
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| suite | varchar | extraction \| retrieval \| faithfulness \| all |
| status | varchar | QUEUED \| RUNNING \| DONE \| FAILED |
| started_at / finished_at | timestamptz, nullable | |
| metrics | jsonb, nullable | `{field_accuracy:{overall,by_field}, bbox_mapping_rate, recall_at_5, hallucination_rate}` |
| failures | jsonb | `[{doc_id, doc_name?, field_code, expected, got}]` |

> **신규 테이블**: 성능 목표(정보추출 90%+, BBox 95%+, Recall@5 90%+, 근거없는 응답 5%↓)를 실측하고
> 이력을 보관하기 위한 테이블. 1차 설계에는 "성능 목표"만 문서로 존재했고 이를 실제로 측정/기록하는
> 구조는 없었다.

## 3. 관계 요약

```
users 1 --- N documents
users 1 --- N chat_sessions
documents 1 --- N pages
documents 1 --- N ocr_lines
documents 1 --- 1 extractions --- N extraction_fields --- N highlights
documents 1 --- N risk_findings --- N highlights
documents 1 --- N guarantee_applications
regulations 1 --- N regulation_nodes (자기참조 트리) --- N regulation_chunks
chat_sessions 1 --- N chat_messages
jobs, eval_runs: 다른 테이블을 참조하되 FK 제약 없음(다형 참조 / 독립 실행 이력)
```

## 4. 5주차 이월

- `extraction_fields`/`risk_findings`/`regulation_nodes` 등 자주 조회되는 컬럼(`document_id`, `status`, `regulation_id+parent_id`)에 대한 인덱스 설계
- Alembic 마이그레이션 스크립트 작성
- `jobs.target_id` 다형 참조를 애플리케이션 레벨에서 어떻게 검증할지(잘못된 job_type+target_id 조합 방지)
