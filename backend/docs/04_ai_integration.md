# 04. AI 모듈 연동 인터페이스

Backend는 AI·Document 파트가 제공하는 함수/모듈을 `app/services/ai_client.py`를 통해 호출한다.
AI 파트가 6주차부터 실제 구현을 채워 넣을 것을 전제로, 4주차에는 **호출 계약(인터페이스)만 고정**한다.

> 2차 개정: `front 폴더`(실제 구현된 프론트엔드)의 API 계약에 맞춰 함수 시그니처를 다시 정의했다.
> 1차 설계 대비 필드 8개로 확장, bbox 0~1 정규화, RAG는 BM25+Vector 하이브리드+rerank, 챗봇은 SSE 스트리밍
> 생성기(`generate_answer_stream`)로 바뀌었다. 실제 코드: `app/services/ai_client.py`.

## 1. 호출 계약

```python
# app/services/ai_client.py

def normalize_to_pdf(file_path: str, source_format: str) -> NormalizedDocument: ...
# NormalizedDocument = {normalized_pdf_path, pages: [{page_no, width_pt, height_pt, rotation, has_text_layer}]}

def run_ocr(pdf_path: str) -> list[OcrLineDict]: ...
# OcrLineDict = {page_no, line_id, text, bbox(0~1 정규화), confidence, source, table_cell}

def extract_contract_fields(ocr_lines: list[OcrLineDict]) -> list[ExtractionFieldDict]: ...
# FIELD_CODES 8개를 항상 모두 반환(값 못 찾은 필드는 raw_value=None, mapping_method="none")

def detect_risks(ocr_lines, fields) -> list[RiskFindingDict]: ...
# category는 RISK_CATEGORIES(penalty/missing/contradiction/toxic/policy) 중 하나

def parse_regulation_structure(pdf_path: str) -> list[RegulationNodeDict]: ...
# 장·조·항·목 트리 (level/number/title/path/page_no/content/children)

def chunk_regulation(nodes: list[RegulationNodeDict]) -> list[RegulationChunkDict]: ...

def index_chunks(regulation_id: str, chunks: list[RegulationChunkDict]) -> list[str]: ...
# 반환값 = 각 청크의 embedding_ref 리스트(순서 동일)

def hybrid_search(query: str, regulation_ids: list[str] | None, top_k: int = 5) -> list[SearchResultDict]: ...
# BM25 → Vector → RRF 결합 → rerank. 각 단계 점수를 모두 반환(/search 디버그 엔드포인트가 그대로 노출)

async def generate_answer_stream(query: str, chunks: list[SearchResultDict]) -> AsyncIterator[dict]: ...
# POST /chat/sessions/{id}/messages(SSE)의 이벤트를 그대로 yield하는 비동기 제너레이터
# {"event": "status"|"token"|"citation"|"done", "data": {...}}
```

전체 타입 정의는 `app/services/ai_client.py`의 TypedDict들을 참고 — DB 모델(`app/models/*.py`)과
1:1 대응되도록 필드명을 맞췄다.

## 2. 책임 경계

- **AI 파트**: 위 함수들의 내부 로직(파싱/OCR/LLM 호출/하이브리드 검색/RAG 생성) 구현, 정확도 책임
- **Backend 파트**: 위 함수 호출, 반환값을 DB 스키마(`02_db_erd.md`)에 맞게 저장, `generate_answer_stream`의
  이벤트를 그대로 SSE(`text/event-stream`)로 클라이언트에 중계, 실패 시 재시도/상태(`jobs`) 관리

## 3. 챗봇 스트리밍 연동 방식 (신규)

1. Backend가 `hybrid_search(query, session.regulation_ids)`로 후보 청크를 얻는다.
2. `generate_answer_stream(query, chunks)`가 yield하는 이벤트를 그대로
   `StreamingResponse(media_type="text/event-stream")`으로 프론트에 중계한다(변환 없이 그대로 전달).
3. `done` 이벤트를 받으면 그 내용으로 `chat_messages` 행을 저장한다(스트리밍 도중이 아니라 완료 시점에 1회 저장).
4. `chunks`가 비어 있으면(검색 결과 0건) `generate_answer_stream`을 호출하지 않고 바로
   `answer_status=NOT_FOUND`로 `done`만 만들어 보낸다 — 근거 없는 응답 방지 원칙.

## 4. 데이터 동기화 원칙

AI 파트의 출력 스키마가 바뀌면 다음을 함께 갱신해야 한다:
- `02_db_erd.md`의 `extraction_fields`/`risk_findings`/`regulation_chunks` 컬럼
- `03_api_spec.md`의 응답 예시
- `front 폴더/src/types/api.ts` (프론트와 계약이 어긋나면 프론트 빌드가 깨지므로 가장 먼저 확인)

## 5. 실행 방식

- OCR/LLM 호출을 포함하는 문서처리·규정인덱싱·평가실행은 모두 `jobs` 테이블(공용)로 추적한다.
- 장시간 작업은 FastAPI BackgroundTasks(또는 5주차 검토 후 Celery 등 큐)로 감싸 비동기 처리하고,
  `jobs.current_step`/`progress`를 단계별로 갱신한다.
- 챗봇 SSE는 큐를 거치지 않고 요청-응답 커넥션을 유지한 채 실시간으로 스트리밍한다(위 3항).
