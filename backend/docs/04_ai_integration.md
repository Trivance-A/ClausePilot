# 04. AI 모듈 연동 인터페이스

Backend는 AI·Document 파트가 제공하는 함수/모듈을 `app/services/ai_client.py`를 통해 호출한다.
AI 파트가 6주차부터 실제 구현을 채워 넣을 것을 전제로, 4주차에는 **호출 계약(인터페이스)만 고정**한다.

## 1. 호출 계약 (초안)

```python
# app/services/ai_client.py 의 예상 시그니처 (AI 파트와 합의 필요)

def normalize_to_pdf(file_path: str, source_format: str) -> NormalizedDocument: ...

def run_ocr(pdf_path: str) -> OcrResult: ...
# OcrResult: 03_ocr_pipeline.md 의 출력 스키마와 동일

def extract_contract_fields(ocr_result: OcrResult) -> ContractExtractionResult: ...
# ContractExtractionResult: ai/schemas/contract_extraction.schema.json 과 동일 구조 (AI 폴더 삭제 전 확정된 스키마 기준,
# 5주차에 AI 파트 재작업 시 이 문서와 다시 동기화 필요)

def detect_risks(ocr_result: OcrResult, extraction: ContractExtractionResult) -> list[RiskFlag]: ...

def build_regulation_index(pdf_path: str) -> None: ...

def answer_question(query: str, session_id: str) -> ChatAnswer: ...
```

## 2. 책임 경계

- **AI 파트**: 위 함수들의 내부 로직(파싱/OCR/LLM 호출/RAG) 구현, 정확도 책임
- **Backend 파트**: 위 함수 호출, 반환값을 DB 스키마(`02_db_erd.md`)에 맞게 저장, 실패 시 재시도/상태 관리, API로 노출

## 3. 데이터 동기화 원칙

AI 파트의 출력 스키마가 바뀌면 다음 문서를 함께 갱신해야 한다:
- `02_db_erd.md`의 `extracted_fields`, `risk_flags` 테이블 컬럼
- `03_api_spec.md`의 응답 예시

> 참고: 이번 세션에서 AI 파트 설계 문서(`ai/` 폴더)는 방향 전환으로 삭제되었습니다.
> 본 문서의 필드 목록(계약건명/계약금액/보증금액/계약일자/보증기간/채권자명)은 발표 대본 원문을 근거로 했으므로
> AI 파트가 추후 설계를 진행할 때 이 문서를 기준점으로 다시 맞추면 됩니다.

## 4. 실행 방식 (4주차 결정)

- 동기 함수 호출을 FastAPI의 BackgroundTasks(또는 5주차 검토 후 Celery 등 큐)로 감싸 비동기 처리
- 장시간 작업(OCR/LLM)은 문서 상태(`documents.status`)를 단계별로 갱신하며 진행
