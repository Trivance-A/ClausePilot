# Gold set (FR-18 evaluation)

정답셋. `eval/extraction.py`와 `eval/ocr_benchmark.py`가 읽는다. 문서 1건 = JSON 1개 (+ 원본 파일).

## Schema (03_데이터정의 §3.2)

```json
{
  "doc_id": "contract_0001",
  "doc_name": "표시용 이름 (선택)",
  "source_type": "native | scan",
  "file": "contract_0001.pdf",
  "labels": {
    "contract_amount": {"value": 350000000, "page": 1, "bbox": [0.12, 0.34, 0.48, 0.36], "raw_text": "금 삼억오천만원정(₩350,000,000)"},
    "guarantee_amount": null
  },
  "text_lines": [{"page": 1, "text": "1. 공사명 : ...", "bbox": [0.08, 0.11, 0.48, 0.13]}]
}
```

- `labels`: 8개 항목(`backend/ai/types.py` FIELD_CODES). `null` = 문서에 없음 → 정답은 raw_value null. 키가 아예 없으면 평가하지 않는다.
- `value` 형식: 금액 int, 일자 `YYYY-MM-DD`, `guarantee_period` `{"start", "end"}`, 사업자번호 `###-##-#####`, 이름은 적힌 그대로
  (비교 시 `backend/ai/extract/normalize.py`의 같은 정규화를 양쪽에 적용, "(주)/주식회사/㈜" 통일).
- `bbox`: `[x0,y0,x1,y1]` 0~1, 좌상단 원점, 회전 적용 후 표시 페이지 기준, 값 텍스트만(라벨 제외). 두 줄에 걸친 값은 두 줄의 합집합.
- `file`: 생략 시 같은 폴더의 `<doc_id>.{pdf,hwp,hwpx,docx,xlsx,png,jpg}`. PDF가 아니면 `normalize_to_pdf` 후 평가.
- `text_lines`(선택): 인쇄된 모든 줄(읽기 순서). scan 문서에 있으면 OCR 벤치마크(CER/WER)에 쓰인다.

## 실제 계약서 추가 방법

1. 새 폴더(예: `data/gold/real/`)에 원본 파일을 `<doc_id>.<ext>`로 둔다. 개인정보·실명·실제 번호는 마스킹 후 사용.
2. 문서를 PDF로 열어 각 항목의 값 영역을 표시하고 좌표를 페이지 크기로 나눠 0~1로 적는다(PyMuPDF `page.search_for(raw_text)` 결과 ÷ `page.rect`가 가장 빠름).
3. 위 스키마로 `<doc_id>.json` 작성 → `PYTHONPATH=backend python -m eval.extraction --gold data/gold/real` (잘못된 bbox·필드명은 로드 시 에러).

## Synthetic set (`synthetic/`) — 가공 데이터

`eval/make_synthetic_gold.py`가 만든 30건, **모든 값은 가공**(기관·금액·번호 실존 아님, 사업자번호는 체크섬만 유효). 문서마다 상단에 가공 데이터 표시가 인쇄된다.
금액(한글/숫자/병기/“3억 5,000만원”), 일자 6형식(2자리 연도 포함), 목록형 13 / 괘선 표 17, 두 줄 계약건명 6, 상대 보증기간(“계약일로부터 준공일까지”) 10,
(주)/주식회사/㈜ 표기, null 라벨(보증금 8, 사업자번호 7, 이행기일 3, 보증기간 2), 2페이지 15, scan 10건(200dpi, ±1~3° 회전, 노이즈, JPEG; gold bbox 동일 변환).
JSON만 커밋하고 PDF는 재생성한다(시드 고정, JSON은 바이트 단위로 동일하게 재현됨):

```bash
PYTHONPATH=backend python -m eval.make_synthetic_gold            # -> data/gold/synthetic/*.pdf
PYTHONPATH=backend python -m eval.extraction --gold data/gold/synthetic --extractor rule --ocr-engine tesseract
PYTHONPATH=backend python -m eval.extraction --gold data/gold/synthetic --extractor llm --limit 10   # Ollama qwen2.5:7b
OCR_DPI=200 PYTHONPATH=backend python -m eval.ocr_benchmark --gold data/gold/synthetic --engines tesseract,paddle
PYTHONPATH=backend python -m pytest eval/tests
```

출력: `eval/out/<gold>-<extractor>/metrics.json, failures.json, failures.csv` (gitignore). 실패 사유: `missed | unexpected_value | normalize_failed | value_mismatch | bbox_unmapped | bbox_iou_low`.

## Baseline — 2026-10-12, synthetic 가공 데이터, MacBook M4 (CPU)

이 수치는 가공 데이터 기준이며 실제 계약서 성능이 아니다.

| extractor | docs | field acc (overall) | native | scan | bbox mapping | bbox IoU@0.5 | s/doc (mean) |
|---|---|---|---|---|---|---|---|
| rule (`_extract_rule_based`), scan OCR = tesseract | 30 (20 native / 10 scan) | **25.8%** | 31.3% | 15.0% | 87.7% | **21.4%** | 0.72 (native 0.01, scan 2.13) |
| llm (Ollama qwen2.5:7b) | — | 미측정 | | | | | |

- rule 실패 199건: normalize_failed 80, value_mismatch 57, missed 27, bbox_iou_low 21, unexpected_value 14. 표 레이아웃(라벨·값이 다른 셀)과 `납품기한`·`발주기관` 라벨, 2자리 연도에서 무너지고,
  highlight가 줄 전체라 IoU@0.5가 낮다. 목표(NFR-01 ≥90%, NFR-02 ≥95%) 대비 한참 미달.
- LLM 경로: 공유 Ollama가 바빠 첫 문서에서 120s 타임아웃 ×3 → 측정 못 함. 대신 "gold raw_text를 답하는 가짜 LLM"으로 실제 OCR→extract_fields→bbox 매핑→정규화를 돌리면
  native 20건 전부 정확도·IoU@0.5 100%(gold bbox와 파이프라인 좌표계가 일치함을 확인, `eval/tests`의 test_llm_path_with_fake_client…).

| OCR (scan 10건 / 13p, OCR_DPI=200) | CER | WER | line-bbox agreement (IoU≥0.5) | s/doc |
|---|---|---|---|---|
| tesseract 5.5 kor+eng | 28.2% | 148.7% | 84.8% | 1.5 |
| tesseract (OCR_DPI=300 기본값) | 34.5% | 153.2% | 72.1% | 2.3 |
| PaddleOCR PP-OCRv5 | 미측정 | | | |

- WER > 100%: Tesseract가 한글 어절을 음절 단위로 쪼개 삽입 오류가 많음. CER은 공백 제거 후 계산.
- PaddleOCR: CPU에서 1페이지 약 320s·RSS 7.8GB(같은 페이지 텍스트는 Tesseract보다 눈에 띄게 정확)여서 시간 제약으로 전체 벤치마크는 생략.
