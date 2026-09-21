# 02. DB ERD 설계 (초안)

## 1. 테이블 개요

| 테이블 | 목적 |
|---|---|
| `documents` | 업로드된 계약서 원본/정규화 PDF 메타데이터, 처리 상태 |
| `ocr_blocks` | OCR/Layout 분석 결과 (텍스트 + 좌표 블록 단위) |
| `extracted_fields` | 계약서 주요정보 추출 결과 (필드별 값 + 근거 위치) |
| `risk_flags` | 위험조항 탐지 결과 |
| `regulations` | 업로드된 규정/매뉴얼 문서 메타데이터 |
| `regulation_chunks` | 규정 문서의 장·조·항·목 단위 청크 (RAG 검색 대상) |
| `chat_sessions` / `chat_messages` | 규정 챗봇 대화 이력 및 근거 조항 |
| `guarantee_applications` | 보증신청 Auto-fill Demo 데이터 |

## 2. 테이블 상세

### documents
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| original_filename | varchar | |
| source_format | varchar | hwp / hwpx / pdf / xlsx |
| normalized_pdf_path | varchar | 정규화된 PDF 저장 경로 |
| status | varchar | pending / parsing / ocr / extracting / done / failed |
| page_count | int | |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### ocr_blocks
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK → documents.id) | |
| page_no | int | |
| block_id | varchar | AI 모듈이 부여한 블록 식별자 (예: p1_b1) |
| text | text | |
| bbox | jsonb / numeric[4] | [x0,y0,x1,y1] |
| block_type | varchar | line / table_cell / paragraph |
| confidence | float | |

### extracted_fields
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK) | |
| field_key | varchar | contract_title / contract_amount / guarantee_amount / contract_date / guarantee_period_start / guarantee_period_end / creditor_name |
| value | text | 정규화된 값 (금액은 문자열로 직렬화하거나 별도 numeric 컬럼 병행 검토) |
| confidence | float | |
| evidence_page_no | int | nullable |
| evidence_block_id | varchar | nullable |
| evidence_bbox | jsonb | nullable, [x0,y0,x1,y1] |

`ai/docs/04_extraction_schema.md`(AI 파트 스키마)와 1:1 매핑되도록 설계 — 필드 추가 시 양쪽 동시 갱신 필요.

### risk_flags
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK) | |
| category | varchar | 독소조항 / 과도한위약금 / 필수항목누락 / 내용모순 |
| level | varchar | High / Medium / Low |
| description | text | |
| evidence_page_no | int | nullable |
| evidence_bbox | jsonb | nullable |

### regulations / regulation_chunks
| 컬럼 (regulations) | 타입 |
|---|---|
| id | UUID (PK) |
| title | varchar |
| uploaded_at | timestamptz |

| 컬럼 (regulation_chunks) | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| regulation_id | UUID (FK) | |
| chapter | varchar | 장 |
| article | varchar | 조 |
| clause | varchar | 항·목 |
| text | text | 청크 본문 |
| embedding_ref | varchar | 외부 Vector DB의 인덱스 참조 ID (임베딩 값 자체는 Vector DB에 저장) |

### chat_sessions / chat_messages
| 컬럼 (chat_sessions) | 타입 |
|---|---|
| id | UUID (PK) |
| started_at | timestamptz |

| 컬럼 (chat_messages) | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| session_id | UUID (FK) | |
| role | varchar | user / assistant |
| content | text | |
| evidence_chunk_ids | jsonb | 답변 근거로 사용된 regulation_chunks.id 목록 |
| created_at | timestamptz | |

### guarantee_applications
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID (FK) | 어떤 계약서에서 auto-fill 되었는지 |
| filled_fields | jsonb | Auto-fill 된 필드 스냅샷 |
| created_at | timestamptz | |

## 3. 관계

```
documents 1 --- N ocr_blocks
documents 1 --- N extracted_fields
documents 1 --- N risk_flags
documents 1 --- N guarantee_applications
regulations 1 --- N regulation_chunks
chat_sessions 1 --- N chat_messages
```

## 4. 4주차 결정 / 5주차 이월 사항

- **결정**: 정규화된 데이터 위주 관계형 스키마(PostgreSQL) + `jsonb`로 bbox/유연 필드 저장
- **결정**: 벡터 임베딩 자체는 PostgreSQL이 아닌 별도 Vector DB(Chroma/FAISS 등)에 저장하고, `regulation_chunks.embedding_ref`로 참조만 연결 (AI 파트와 5주차 협의)
- **이월**: 정확한 컬럼 타입(예: 금액을 numeric으로 별도 컬럼화할지), 인덱스 설계, Alembic 마이그레이션 초안 작성은 5주차
