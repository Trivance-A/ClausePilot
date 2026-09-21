// 03_API_명세서 기준 타입 정의. bbox = [x0, y0, x1, y1] (0~1 정규화, 좌상단 원점)
export type BBox = [number, number, number, number];

export type Role = 'admin' | 'user';
export interface User { id: string; name: string; email?: string; role: Role }
export interface LoginResponse { access_token: string; token_type: string; user: User }

export interface Paginated<T> { items: T[]; total: number; page: number; size: number }

export type DocumentStatus = 'UPLOADED' | 'NORMALIZING' | 'OCR' | 'EXTRACTING' | 'RISK' | 'DONE' | 'FAILED';
export type SourceType = 'native' | 'scan' | 'mixed';
export type Severity = 'HIGH' | 'MEDIUM' | 'LOW';
export type RiskSummary = Record<Severity, number>;

export interface DocumentListItem {
  id: string;
  original_name: string;
  original_format: string;
  source_type: SourceType | null;
  page_count: number | null;
  status: DocumentStatus;
  risk_summary: RiskSummary | null;
  created_at: string;
}

export interface PageMeta { page_no: number; width_pt: number; height_pt: number; rotation: number; has_text_layer: boolean }

export interface DocumentDetail extends DocumentListItem {
  pages: PageMeta[];
  extraction: { id: string; status: ExtractionStatus; model_name: string; created_at: string } | null;
}

export type JobStep = 'normalize' | 'ocr' | 'extract' | 'risk' | string;
export interface Job { id: string; current_step: JobStep | null; progress: number; error: string | null; status?: JobStatus }
export interface DocumentStatusResponse { status: DocumentStatus; job: Job | null }

export interface UploadItem { document_id: string; job_id: string; original_name: string; status: DocumentStatus }
export interface UploadResponse { items: UploadItem[] }

export interface OcrLine {
  id: string; line_id: string; text: string; bbox: BBox; confidence: number; source: string; table_cell: string | null;
}
export interface LinesResponse { page_no: number; lines: OcrLine[] }

export type FieldCode =
  | 'contract_name' | 'contract_amount' | 'guarantee_amount' | 'contract_date'
  | 'performance_due_date' | 'guarantee_period' | 'creditor_name' | 'creditor_biz_no';
export const FIELD_CODES: FieldCode[] = [
  'contract_name', 'contract_amount', 'guarantee_amount', 'contract_date',
  'performance_due_date', 'guarantee_period', 'creditor_name', 'creditor_biz_no',
];
export const FIELD_LABELS: Record<FieldCode, string> = {
  contract_name: '계약건명', contract_amount: '계약금액', guarantee_amount: '보증금액', contract_date: '계약일자',
  performance_due_date: '계약이행기일', guarantee_period: '보증기간', creditor_name: '채권자명', creditor_biz_no: '채권자 사업자번호',
};

export type MappingMethod = 'exact' | 'fuzzy' | 'llm_ref' | 'manual' | 'none';
export type HighlightOrigin = 'auto' | 'manual';
export type ExtractionStatus = 'AUTO' | 'REVIEWED' | 'CONFIRMED';

export interface Highlight { id: string; page_no: number; bbox: BBox; origin: HighlightOrigin; ocr_line_id?: string | null }

export type NormalizedValue =
  | { amount: number } | { date: string } | { start: string; end: string; derived?: boolean } | { text: string } | Record<string, unknown> | null;

export interface ExtractionField {
  field_code: FieldCode;
  label: string;
  color_key?: string;
  raw_value: string | null;
  normalized_value: NormalizedValue;
  confidence: number;
  mapping_method: MappingMethod;
  is_confirmed: boolean;
  reviewer_note?: string | null;
  highlights: Highlight[];
}

export interface ExtractionResponse {
  extraction_id: string;
  status: ExtractionStatus;
  fields: ExtractionField[];
  color_map: Record<string, string>; // 항목 색상의 단일 소스 (프론트 하드코딩 금지)
}

export interface FieldPatch { raw_value?: string | null; normalized_value?: NormalizedValue; is_confirmed?: boolean; reviewer_note?: string }

export type RiskStatus = 'OPEN' | 'ACKNOWLEDGED' | 'DISMISSED';
export type RiskCategory = 'penalty' | 'missing' | 'contradiction' | 'toxic' | 'policy';
export interface RiskFinding {
  id: string; category: RiskCategory; severity: Severity; score: number;
  rule_code: string | null; title: string; description: string; evidence_text: string | null;
  highlights: Highlight[]; llm_reasoning: Record<string, unknown> | null; status: RiskStatus; note?: string | null;
}
export interface RisksResponse { items: RiskFinding[]; summary: RiskSummary }

export type GuaranteeType = 'contract' | 'bid' | 'defect' | 'payment' | 'advance' | 'other';
export const GUARANTEE_TYPE_LABELS: Record<GuaranteeType, string> = {
  contract: '계약보증', bid: '입찰보증', defect: '하자보증', payment: '지급보증', advance: '선급금보증', other: '기타',
};
export interface GuaranteePeriod { start: string | null; end: string | null }
export interface GuaranteeFormValues {
  contract_name: string | null; contract_amount: number | null; guarantee_amount: number | null;
  contract_date: string | null; performance_due_date: string | null; guarantee_period: GuaranteePeriod | null;
  creditor_name: string | null; creditor_biz_no: string | null;
}
export interface FieldSource { field_id: string; confidence: number; highlight_ids: string[]; page_no: number | null }
export interface GuaranteeApplication {
  id: string; document_id: string; guarantee_type: GuaranteeType; status: 'DRAFT' | 'SUBMITTED';
  form_values: GuaranteeFormValues; field_sources: Partial<Record<FieldCode, FieldSource>>;
  required_fields: FieldCode[]; viewer_url: string; risk_summary?: RiskSummary;
}

export type RegulationStatus = 'UPLOADED' | 'PARSING' | 'INDEXED' | 'FAILED' | 'ARCHIVED';
export type RegDocType = '정관' | '규정' | '지침' | '매뉴얼';
export interface RegulationListItem {
  id: string; title: string; doc_type: RegDocType; version: number; status: RegulationStatus;
  chunk_count: number | null; effective_date: string | null; created_at: string; error?: string | null;
}
export type RegNodeLevel = 'chapter' | 'section' | 'article' | 'paragraph' | 'item' | 'subitem' | 'appendix';
export interface RegNode {
  node_id: string; level: RegNodeLevel; number: string; title: string | null; path?: string; page_no?: number | null; children: RegNode[];
}
export interface RegulationDetail extends RegulationListItem { tree: RegNode[] }
export interface RegNodeContent { node_id: string; path: string; content: string; page_no: number | null; bbox: BBox | null; chunk_ids: string[] }

export interface ChatSession { session_id: string; title: string | null; regulation_ids: string[]; created_at?: string; last_active_at?: string }
export type AnswerStatus = 'ANSWERED' | 'NOT_FOUND' | 'ERROR';
export interface Citation {
  ref: number; chunk_id: string; regulation_id: string; regulation_title: string; path: string;
  quoted_span?: string | null; page_no: number | null; bbox: BBox | null; node_id?: string | null;
}
export interface Suggestion { path: string; title: string; regulation_id?: string; node_id?: string }
export interface ChatMessage {
  id: string; role: 'user' | 'assistant'; content: string; created_at?: string;
  answer_status?: AnswerStatus; citations?: Citation[]; suggestions?: Suggestion[]; latency_ms?: number; feedback?: 1 | -1 | null;
}

export type SseEvent =
  | { event: 'status'; data: { stage: 'rewrite' | 'retrieve' | 'generate' | string; rewritten_query?: string; hits?: number } }
  | { event: 'token'; data: { text: string } }
  | { event: 'citation'; data: Citation }
  | { event: 'done'; data: { message_id: string; answer_status: AnswerStatus; latency_ms: number; suggestions?: Suggestion[]; content?: string } }
  | { event: 'error'; data: { code: string; message: string } };

export type JobType = 'process_document' | 'index_regulation' | 'eval';
export type JobStatus = 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED';
export interface AdminJob {
  id: string; job_type: JobType; target_id: string; target_name?: string; status: JobStatus; current_step: string | null;
  progress: number; error: string | null; attempts: number; started_at: string | null; finished_at: string | null;
}
export interface AdminStats {
  documents: { total: number; done: number; failed: number };
  regulations: { indexed: number; chunks: number };
  chat: { messages_7d: number; not_found_rate: number; thumbs_up_rate: number };
  avg_latency_ms: { extract: number; chat_first_token: number };
}
export interface ChatLogItem {
  id: string; session_id: string; question: string; answer: string; answer_status: AnswerStatus;
  citations: { path: string }[]; feedback: 1 | -1 | null; latency_ms: number; created_at: string;
}

export type EvalSuite = 'extraction' | 'retrieval' | 'faithfulness' | 'all';
export interface EvalRun {
  id: string; suite: EvalSuite; status: JobStatus; started_at?: string; finished_at?: string | null;
  metrics: {
    field_accuracy?: { overall: number; by_field: Partial<Record<FieldCode, number>> };
    bbox_mapping_rate?: number; recall_at_5?: number; hallucination_rate?: number;
  } | null;
  failures: { doc_id: string; doc_name?: string; field_code: FieldCode; expected: string; got: string | null }[];
}

export interface ApiErrorBody { error: { code: string; message: string; detail?: Record<string, unknown> } }
