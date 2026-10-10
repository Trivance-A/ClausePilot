# 04. AI 모듈 연동 인터페이스

> 3차 개정 (AI·Document): 계약서 파이프라인 함수 내부를 `backend/ai/` 패키지로 교체했다. 시그니처는 유지하고
> 선택 인자만 추가했다 — `run_ocr(pdf_path, engine=None)`, `detect_risks(..., policy_search=None)`.
> `normalize_to_pdf` 반환값에 `source_type`(native/scan/mixed)·`parsed_text_path`가 추가됐다.
>
> | 모듈 | 내용 (05_OCR_Pipeline 설계서 단계) |
> |---|---|
> | `ai/parser` | ① 포맷 정규화: hwp(olefile)/hwpx(zip+lxml)/docx/xlsx 파싱 → `{id}.parsed_text.json`, LibreOffice headless → PDF, img2pdf |
> | `ai/ocr` | ③ 라우터(텍스트≥50자·폰트·한글비율) ④ native 라인/표 셀 · scan OCR(deskew·표 격자·엔진) ⑤ 읽기 순서·조각 병합·`L{page}-{line}` |
> | `ai/ocr/server.py` | OCR 서빙(`POST /ocr`, `GET /health`) — `docker compose --profile gpu`의 `ocr` 컨테이너, worker는 `OCR_BASE_URL`로 호출 |
> | `ai/extract` | ⑥ LLM 구조화 추출(JSON Schema, 5p 초과 시 키워드 ±10줄) + ⑧ 정규화 |
> | `ai/mapping` | ⑦ bbox 역매핑 llm_ref → exact → fuzzy(rapidfuzz ≥85) → 재질의, 부분 bbox, 실패 원인 로그 |
> | `ai/risk` | ⑨ 룰 4종 + LLM 3종 병렬, 근거 라인 → bbox, 중복 병합, `rules.yaml` 시드 |
> | `ai/llm.py` | OpenAI 호환 클라이언트(temperature 0, 120s, 3회 지수 백오프, `cache` = sha256(model+prompt_version+prompt)) |
>
> 환경변수: `LLM_BASE_URL`(비우면 규칙 기반 오프라인 모드) · `LLM_MODEL` · `LLM_API_KEY` · `OCR_ENGINE`(auto|paddle_vl|paddle|tesseract) · `OCR_BASE_URL` · `OCR_DPI`.
> 장애: `OcrUnavailableError`/`LLMUnavailableError`(API 503 OCR_UNAVAILABLE/LLM_UNAVAILABLE) → 문서 FAILED + jobs.error, reprocess로 재시작.

Backend는 AI·Document 파트가 제공하는 함수/모듈을 `app/services/ai_client.py`를 통해 호출한다.
인터페이스(함수 시그니처)는 여기서 고정하고, **내부 구현은 이미 규칙 기반(정규식/BM25 등) 로직으로
채워져 있다** — 외부 OCR/LLM API 키 없이도 전체 파이프라인이 end-to-end로 동작하도록 하기 위해서다.
AI·Document 파트가 실제 모델로 교체할 때는 이 인터페이스만 유지한 채 함수 내부만 바꾸면 된다.
현재 구현의 범위와 한계는 `../README.md`의 "구현 현황과 한계" 표를 참고.

> 2차 개정: `front 폴더`(실제 구현된 프론트엔드)의 API 계약에 맞춰 함수 시그니처를 다시 정의했다.
> 1차 설계 대비 필드 8개로 확장, bbox 0~1 정규화, RAG는 BM25+Vector 하이브리드+rerank, 챗봇은 SSE 스트리밍
> 생성기(`generate_answer_stream`)로 바뀌었다. 실제 코드: `app/services/ai_client.py`.

## 1. 호출 계약

```python
# app/services/ai_client.py

def normalize_to_pdf(input_path: str, source_format: str, output_path: str) -> NormalizedDocument: ...
# pdf/docx/xlsx/hwpx/hwp 지원. NormalizedDocument = {normalized_pdf_path, pages: [...]}

def run_ocr(pdf_path: str) -> list[OcrLineDict]: ...
# OcrLineDict = {page_no, line_id, text, bbox(0~1 정규화), confidence, source, table_cell}

def extract_contract_fields(ocr_lines: list[OcrLineDict]) -> list[ExtractionFieldDict]: ...
# FIELD_CODES 8개를 항상 모두 반환(값 못 찾은 필드는 raw_value=None, mapping_method="none")

def detect_risks(ocr_lines, fields, rules: list[RiskRuleDict]) -> list[RiskFindingDict]: ...
# rules는 Backend가 risk_rules 테이블(DB, 관리자가 조정 가능)에서 읽어 전달. score→severity는
# 통일 공식(>=0.75 HIGH, >=0.45 MEDIUM, 그 외 LOW)

def parse_regulation_structure(pdf_path: str) -> list[RegulationNodeDict]: ...
# 장·조·항·목 트리 (level/number/title/path/page_no/content/children)

def chunk_regulation(nodes: list[RegulationNodeDict]) -> list[RegulationChunkDict]: ...

def index_chunks(chunks: list[RegulationChunkDict]) -> list[list[float]]: ...
# 반환값 = 각 청크의 임베딩 벡터(384d, 순서 동일). Backend가 regulation_chunks.embedding(pgvector)에 저장

def hybrid_search(query: str, candidates: list[SearchCandidate], top_k: int = 5) -> list[SearchResultDict]: ...
# candidates[i]["embedding"]은 Backend가 pgvector 컬럼에서 미리 읽어 전달(이 함수는 DB에 접근하지 않음).
# BM25(Kiwi 형태소) → 임베딩 코사인 → RRF 결합 → rerank(cross-encoder 미도입, RRF 그대로 사용).
# 각 단계 점수를 모두 반환(/search 디버그 엔드포인트가 그대로 노출)

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
- 장시간 작업은 Redis+RQ 큐로 비동기 처리한다: api 프로세스는 `default_queue.enqueue(...)`로 넣기만
  하고, 별도 `worker` 컨테이너(`rq worker`)가 실제로 실행하며 `jobs.current_step`/`progress`를
  단계별로 갱신한다(`app/core/queue.py`).
- 챗봇 SSE는 큐를 거치지 않고 요청-응답 커넥션을 유지한 채 실시간으로 스트리밍한다(위 3항).
