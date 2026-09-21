// MSW 목 데이터 — 03_API_명세서 예시 + 04_화면설계서 와이어프레임 값 기준
import type {
  AdminJob, AdminStats, BBox, ChatLogItem, ChatMessage, ChatSession, DocumentListItem, EvalRun, ExtractionField, PageMeta,
  RegNode, RegNodeContent, RegulationListItem, RiskFinding,
} from '@/types/api';

export const PAGE_W = 595.3;
export const PAGE_H = 841.9;

export interface MockLine { page: number; no: number; text: string; bbox: BBox; size?: number; conf?: number; cell?: string }
/** 목 PDF 본문 라인 = /lines 응답 = 하이라이트 bbox 의 단일 소스 (Helvetica 표준 폰트라 영문) */
export const MOCK_LINES: MockLine[] = [
  { page: 1, no: 1, text: 'CONSTRUCTION CONTRACT AGREEMENT', bbox: [0.22, 0.08, 0.78, 0.115], size: 18 },
  { page: 1, no: 2, text: '1. Project Name : OO City Road Expansion Works', bbox: [0.10, 0.20, 0.66, 0.225] },
  { page: 1, no: 3, text: '2. Contract Amount : KRW 350,000,000 (Three Hundred Fifty Million Won)', bbox: [0.10, 0.25, 0.88, 0.275] },
  { page: 1, no: 4, text: '3. Contract Date : March 5, 2026', bbox: [0.10, 0.30, 0.48, 0.325] },
  { page: 1, no: 5, text: '4. Completion Due Date : December 31, 2026', bbox: [0.10, 0.35, 0.58, 0.375], conf: 0.62 },
  { page: 1, no: 6, text: '5. Contract Guarantee Amount : KRW 35,000,000 (10% of contract amount)', bbox: [0.10, 0.40, 0.86, 0.425] },
  { page: 1, no: 7, text: '6. Guarantee Period : 2026-03-05 ~ 2027-03-04', bbox: [0.10, 0.45, 0.62, 0.475] },
  { page: 1, no: 8, text: '7. Client (Creditor) : OO Public Corporation', bbox: [0.10, 0.50, 0.60, 0.525] },
  { page: 1, no: 9, text: '   Business Registration No. : (see attachment)', bbox: [0.10, 0.55, 0.62, 0.575], conf: 0.55 },
  { page: 1, no: 10, text: '8. Contractor : ABC Construction Co., Ltd.', bbox: [0.10, 0.60, 0.60, 0.625] },
  { page: 1, no: 11, text: 'Item | Amount', bbox: [0.10, 0.70, 0.30, 0.72], cell: 'r1,c1' },
  { page: 1, no: 12, text: 'Contract Guarantee | KRW 35,000,000', bbox: [0.10, 0.73, 0.50, 0.75], cell: 'r2,c1' },
  { page: 2, no: 1, text: 'Article 8 (Liquidated Damages for Delay)', bbox: [0.10, 0.12, 0.62, 0.15], size: 13 },
  { page: 2, no: 2, text: 'The Contractor shall pay liquidated damages of 3/1000 of the contract', bbox: [0.10, 0.30, 0.90, 0.325] },
  { page: 2, no: 3, text: 'amount for each day of delay beyond the completion due date.', bbox: [0.10, 0.33, 0.82, 0.355] },
  { page: 2, no: 4, text: 'Article 9 (Payment)', bbox: [0.10, 0.45, 0.42, 0.48], size: 13 },
  { page: 2, no: 5, text: 'Payment shall be made within 30 days after inspection and acceptance.', bbox: [0.10, 0.50, 0.86, 0.525] },
  { page: 3, no: 1, text: 'Article 15 (Termination)', bbox: [0.10, 0.12, 0.45, 0.15], size: 13 },
  { page: 3, no: 2, text: 'The Client may terminate this Contract at any time at its sole discretion', bbox: [0.10, 0.40, 0.92, 0.425] },
  { page: 3, no: 3, text: 'without prior notice, and the Contractor shall have no claim for damages.', bbox: [0.10, 0.43, 0.92, 0.455] },
  { page: 3, no: 4, text: 'Article 16 (Governing Law)', bbox: [0.10, 0.60, 0.45, 0.63], size: 13 },
  { page: 3, no: 5, text: 'This Contract shall be governed by the laws of the Republic of Korea.', bbox: [0.10, 0.65, 0.86, 0.675] },
];
const L = (p: number, n: number) => MOCK_LINES.find((l) => l.page === p && l.no === n)!;
const lineId = (p: number, n: number) => `L${p}-${n}`;

export const PAGES: PageMeta[] = [1, 2, 3].map((n) => ({ page_no: n, width_pt: PAGE_W, height_pt: PAGE_H, rotation: 0, has_text_layer: n !== 2 }));

export const COLOR_MAP: Record<string, string> = {
  contract_name: '#FFD54F', contract_amount: '#4FC3F7', guarantee_amount: '#81C784', contract_date: '#FF8A65',
  performance_due_date: '#BA68C8', guarantee_period: '#A1887F', creditor_name: '#F06292', creditor_biz_no: '#90A4AE',
};

export const now = () => new Date().toISOString();
const daysAgo = (d: number) => new Date(Date.now() - d * 86400000).toISOString();

export const documents: DocumentListItem[] = [
  { id: 'd1', original_name: 'OO공사계약서.hwp', original_format: 'hwp', source_type: 'scan', page_count: 3, status: 'DONE', risk_summary: { HIGH: 1, MEDIUM: 2, LOW: 0 }, created_at: daysAgo(1) },
  { id: 'd2', original_name: '용역계약서.pdf', original_format: 'pdf', source_type: 'native', page_count: 2, status: 'OCR', risk_summary: null, created_at: daysAgo(1) },
  { id: 'd3', original_name: '물품계약서.pdf', original_format: 'pdf', source_type: null, page_count: null, status: 'FAILED', risk_summary: null, created_at: daysAgo(2) },
  { id: 'd4', original_name: '하자보수계약.hwpx', original_format: 'hwpx', source_type: 'native', page_count: 3, status: 'DONE', risk_summary: { HIGH: 0, MEDIUM: 1, LOW: 0 }, created_at: daysAgo(3) },
];

export function makeFields(): ExtractionField[] {
  return [
    { field_code: 'contract_name', label: '계약건명', color_key: 'contract_name', raw_value: 'OO City Road Expansion Works', normalized_value: { text: 'OO시 도로 확장공사' }, confidence: 0.97, mapping_method: 'exact', is_confirmed: false,
      highlights: [{ id: 'h-name', page_no: 1, bbox: L(1, 2).bbox, origin: 'auto', ocr_line_id: lineId(1, 2) }] },
    { field_code: 'contract_amount', label: '계약금액', color_key: 'contract_amount', raw_value: 'KRW 350,000,000 (Three Hundred Fifty Million Won)', normalized_value: { amount: 350000000 }, confidence: 0.93, mapping_method: 'llm_ref', is_confirmed: false,
      highlights: [{ id: 'h-amount', page_no: 1, bbox: L(1, 3).bbox, origin: 'auto', ocr_line_id: lineId(1, 3) }] },
    { field_code: 'guarantee_amount', label: '보증금액', color_key: 'guarantee_amount', raw_value: 'KRW 35,000,000', normalized_value: { amount: 35000000 }, confidence: 0.90, mapping_method: 'exact', is_confirmed: false,
      highlights: [{ id: 'h-gamount', page_no: 1, bbox: L(1, 6).bbox, origin: 'auto', ocr_line_id: lineId(1, 6) }, { id: 'h-gamount2', page_no: 1, bbox: L(1, 12).bbox, origin: 'auto', ocr_line_id: lineId(1, 12) }] },
    { field_code: 'contract_date', label: '계약일자', color_key: 'contract_date', raw_value: 'March 5, 2026', normalized_value: { date: '2026-03-05' }, confidence: 0.98, mapping_method: 'exact', is_confirmed: false,
      highlights: [{ id: 'h-date', page_no: 1, bbox: L(1, 4).bbox, origin: 'auto', ocr_line_id: lineId(1, 4) }] },
    { field_code: 'performance_due_date', label: '계약이행기일', color_key: 'performance_due_date', raw_value: 'December 31, 2026', normalized_value: { date: '2026-12-31' }, confidence: 0.62, mapping_method: 'fuzzy', is_confirmed: false,
      highlights: [{ id: 'h-due', page_no: 1, bbox: L(1, 5).bbox, origin: 'auto', ocr_line_id: lineId(1, 5) }] },
    { field_code: 'guarantee_period', label: '보증기간', color_key: 'guarantee_period', raw_value: '2026-03-05 ~ 2027-03-04', normalized_value: { start: '2026-03-05', end: '2027-03-04' }, confidence: 0.85, mapping_method: 'exact', is_confirmed: false,
      highlights: [{ id: 'h-period', page_no: 1, bbox: L(1, 7).bbox, origin: 'auto', ocr_line_id: lineId(1, 7) }] },
    { field_code: 'creditor_name', label: '채권자명', color_key: 'creditor_name', raw_value: 'OO Public Corporation', normalized_value: { text: 'OO공사' }, confidence: 0.91, mapping_method: 'llm_ref', is_confirmed: false,
      highlights: [{ id: 'h-creditor', page_no: 1, bbox: L(1, 8).bbox, origin: 'auto', ocr_line_id: lineId(1, 8) }] },
    { field_code: 'creditor_biz_no', label: '채권자 사업자번호', color_key: 'creditor_biz_no', raw_value: null, normalized_value: null, confidence: 0, mapping_method: 'none', is_confirmed: false, highlights: [] },
  ];
}

export function makeRisks(): RiskFinding[] {
  return [
    { id: 'r1', category: 'penalty', severity: 'HIGH', score: 0.86, rule_code: 'PENALTY_RATE_HIGH', title: '지체상금율 과다 (1일 0.3%)', description: '표준계약서 기준(0.1%/일)의 3배입니다.',
      evidence_text: 'liquidated damages of 3/1000 of the contract amount for each day of delay', highlights: [{ id: 'h-r1', page_no: 2, bbox: [0.10, 0.30, 0.90, 0.355], origin: 'auto' }], llm_reasoning: null, status: 'OPEN' },
    { id: 'r2', category: 'missing', severity: 'MEDIUM', score: 0.5, rule_code: 'MISSING_ARTICLE', title: '필수조항 누락: 하자담보책임', description: '표준계약서 필수 조항이 문서에 없습니다.', evidence_text: null, highlights: [], llm_reasoning: null, status: 'OPEN' },
    { id: 'r3', category: 'toxic', severity: 'MEDIUM', score: 0.58, rule_code: null, title: '일방적 계약해지 조항', description: '발주자 단독 해지권, 수급인 구제 조항 없음',
      evidence_text: 'The Client may terminate this Contract at any time at its sole discretion without prior notice', highlights: [{ id: 'h-r3', page_no: 3, bbox: [0.10, 0.40, 0.92, 0.455], origin: 'auto' }],
      llm_reasoning: { clause: '제15조(계약해지)', reason: '해지 사유·사전 통지·손해배상 청구권을 발주자에게만 유리하게 규정하여 수급인의 구제 수단이 없음', standard: '표준계약서 제44조는 상호 해지 사유와 통지 절차를 규정' }, status: 'OPEN' },
  ];
}

export const regulations: RegulationListItem[] = [
  { id: 'reg1', title: '계약사무규정', doc_type: '규정', version: 2, status: 'INDEXED', chunk_count: 142, effective_date: '2025-01-01', created_at: daysAgo(30) },
  { id: 'reg2', title: '인사규정', doc_type: '규정', version: 1, status: 'PARSING', chunk_count: null, effective_date: '2024-03-01', created_at: daysAgo(0) },
  { id: 'reg3', title: '업무매뉴얼(보증)', doc_type: '매뉴얼', version: 1, status: 'FAILED', chunk_count: null, effective_date: null, created_at: daysAgo(2), error: 'PARSE_FAILED: hwp BodyText/Section0 zlib 해제 실패 (record tag_id=67) — LibreOffice 변환 PDF 경로로 폴백 필요' },
  { id: 'reg4', title: '정관', doc_type: '정관', version: 3, status: 'INDEXED', chunk_count: 58, effective_date: '2023-06-01', created_at: daysAgo(60) },
];

export const regTree: RegNode[] = [
  { node_id: 'n-ch1', level: 'chapter', number: '1', title: '총칙', page_no: 1, children: [
    { node_id: 'n-a1', level: 'article', number: '1', title: '목적', path: '제1장>제1조(목적)', page_no: 1, children: [] },
    { node_id: 'n-a2', level: 'article', number: '2', title: '정의', path: '제1장>제2조(정의)', page_no: 1, children: [] },
  ] },
  { node_id: 'n-ch3', level: 'chapter', number: '3', title: '계약의 체결', page_no: 4, children: [
    { node_id: 'n-a11', level: 'article', number: '11', title: '입찰보증금', path: '제3장>제11조(입찰보증금)', page_no: 4, children: [
      { node_id: 'n-a11-p1', level: 'paragraph', number: '①', title: null, path: '제3장>제11조(입찰보증금)>제1항', page_no: 4, children: [] },
    ] },
    { node_id: 'n-a12', level: 'article', number: '12', title: '계약보증금', path: '제3장>제12조(계약보증금)', page_no: 4, children: [
      { node_id: 'n-a12-p1', level: 'paragraph', number: '①', title: null, path: '제3장>제12조(계약보증금)>제1항', page_no: 4, children: [] },
      { node_id: 'n-a12-p2', level: 'paragraph', number: '②', title: null, path: '제3장>제12조(계약보증금)>제2항', page_no: 4, children: [] },
      { node_id: 'n-a12-p3', level: 'paragraph', number: '③', title: null, path: '제3장>제12조(계약보증금)>제3항', page_no: 4, children: [] },
    ] },
    { node_id: 'n-a13', level: 'article', number: '13', title: '보증금 면제', path: '제3장>제13조(보증금 면제)', page_no: 5, children: [
      { node_id: 'n-a13-p1', level: 'paragraph', number: '①', title: null, path: '제3장>제13조(보증금 면제)>제1항', page_no: 5, children: [] },
    ] },
    { node_id: 'n-a15', level: 'article', number: '15', title: '하자보수보증금', path: '제3장>제15조(하자보수보증금)', page_no: 5, children: [] },
  ] },
  { node_id: 'n-ch5', level: 'chapter', number: '5', title: '복리후생', page_no: 9, children: [
    { node_id: 'n-a7', level: 'article', number: '7', title: '출장비', path: '제5장>제7조(출장비)', page_no: 9, children: [
      { node_id: 'n-a7-p1', level: 'paragraph', number: '①', title: null, path: '제5장>제7조(출장비)>제1항', page_no: 9, children: [] },
    ] },
    { node_id: 'n-a9', level: 'article', number: '9', title: '급식비', path: '제5장>제9조(급식비)', page_no: 9, children: [] },
  ] },
];

export const regNodes: Record<string, RegNodeContent> = {
  'n-a1': { node_id: 'n-a1', path: '제1장>제1조(목적)', content: '제1조(목적) 이 규정은 조합의 계약 사무 처리에 관한 기본 사항을 정함을 목적으로 한다.', page_no: 1, bbox: [0.1, 0.2, 0.9, 0.25], chunk_ids: ['c-1'] },
  'n-a2': { node_id: 'n-a2', path: '제1장>제2조(정의)', content: '제2조(정의) 이 규정에서 사용하는 용어의 정의는 다음과 같다.\n1. "계약담당자"란 계약 사무를 담당하는 직원을 말한다.\n2. "보증금"이란 입찰보증금·계약보증금·하자보수보증금을 말한다.', page_no: 1, bbox: [0.1, 0.3, 0.9, 0.42], chunk_ids: ['c-2'] },
  'n-a11': { node_id: 'n-a11', path: '제3장>제11조(입찰보증금)', content: '제11조(입찰보증금) ① 입찰에 참가하고자 하는 자는 입찰금액의 100분의 5 이상을 입찰보증금으로 납부하여야 한다.\n② 입찰보증금은 현금 또는 보증서로 납부할 수 있다.', page_no: 4, bbox: [0.1, 0.2, 0.9, 0.3], chunk_ids: ['c-11'] },
  'n-a11-p1': { node_id: 'n-a11-p1', path: '제3장>제11조(입찰보증금)>제1항', content: '① 입찰에 참가하고자 하는 자는 입찰금액의 100분의 5 이상을 입찰보증금으로 납부하여야 한다.', page_no: 4, bbox: [0.1, 0.22, 0.9, 0.27], chunk_ids: ['c-11'] },
  'n-a12': { node_id: 'n-a12', path: '제3장>제12조(계약보증금)', content: '제12조(계약보증금) ① 계약담당자는 계약을 체결하고자 할 때에는 계약상대자로 하여금 계약보증금을 납부하게 하여야 한다.\n② 계약보증금은 계약금액의 100분의 10 이상으로 한다.\n③ 제2항에도 불구하고 계약의 성질상 필요하다고 인정되는 경우에는 계약보증금을 감액할 수 있다.', page_no: 4, bbox: [0.1, 0.36, 0.9, 0.52], chunk_ids: ['c-12'] },
  'n-a12-p1': { node_id: 'n-a12-p1', path: '제3장>제12조(계약보증금)>제1항', content: '① 계약담당자는 계약을 체결하고자 할 때에는 계약상대자로 하여금 계약보증금을 납부하게 하여야 한다.', page_no: 4, bbox: [0.1, 0.37, 0.9, 0.41], chunk_ids: ['c-12'] },
  'n-a12-p2': { node_id: 'n-a12-p2', path: '제3장>제12조(계약보증금)>제2항', content: '제12조(계약보증금)\n① 계약담당자는 계약을 체결하고자 할 때에는 계약상대자로 하여금 계약보증금을 납부하게 하여야 한다.\n② 계약보증금은 계약금액의 100분의 10 이상으로 한다.\n③ 제2항에도 불구하고 계약의 성질상 필요하다고 인정되는 경우에는 계약보증금을 감액할 수 있다.', page_no: 4, bbox: [0.1, 0.42, 0.9, 0.47], chunk_ids: ['c-12'] },
  'n-a12-p3': { node_id: 'n-a12-p3', path: '제3장>제12조(계약보증금)>제3항', content: '③ 제2항에도 불구하고 계약의 성질상 필요하다고 인정되는 경우에는 계약보증금을 감액할 수 있다.', page_no: 4, bbox: [0.1, 0.47, 0.9, 0.52], chunk_ids: ['c-12'] },
  'n-a13': { node_id: 'n-a13', path: '제3장>제13조(보증금 면제)', content: '제13조(보증금 면제) ① 국가기관·지방자치단체 또는 공공기관과 계약하는 경우에는 계약보증금의 전부 또는 일부를 면제할 수 있다.', page_no: 5, bbox: [0.1, 0.15, 0.9, 0.22], chunk_ids: ['c-13'] },
  'n-a13-p1': { node_id: 'n-a13-p1', path: '제3장>제13조(보증금 면제)>제1항', content: '① 국가기관·지방자치단체 또는 공공기관과 계약하는 경우에는 계약보증금의 전부 또는 일부를 면제할 수 있다.', page_no: 5, bbox: [0.1, 0.17, 0.9, 0.22], chunk_ids: ['c-13'] },
  'n-a15': { node_id: 'n-a15', path: '제3장>제15조(하자보수보증금)', content: '제15조(하자보수보증금) 하자보수보증금은 계약금액의 100분의 2 이상 100분의 10 이하로 한다.', page_no: 5, bbox: [0.1, 0.4, 0.9, 0.46], chunk_ids: ['c-15'] },
  'n-a7': { node_id: 'n-a7', path: '제5장>제7조(출장비)', content: '제7조(출장비) ① 국내 출장의 일비는 1일 3만원, 숙박비는 실비(1박 10만원 한도)로 한다.', page_no: 9, bbox: [0.1, 0.2, 0.9, 0.27], chunk_ids: ['c-7'] },
  'n-a7-p1': { node_id: 'n-a7-p1', path: '제5장>제7조(출장비)>제1항', content: '① 국내 출장의 일비는 1일 3만원, 숙박비는 실비(1박 10만원 한도)로 한다.', page_no: 9, bbox: [0.1, 0.22, 0.9, 0.27], chunk_ids: ['c-7'] },
  'n-a9': { node_id: 'n-a9', path: '제5장>제9조(급식비)', content: '제9조(급식비) 직원의 중식은 구내식당을 이용하며, 급식비는 조합이 부담한다.', page_no: 9, bbox: [0.1, 0.4, 0.9, 0.46], chunk_ids: ['c-9'] },
};

export const chatSessions: ChatSession[] = [
  { session_id: 's1', title: '계약보증금', regulation_ids: [], created_at: daysAgo(1), last_active_at: daysAgo(1) },
  { session_id: 's2', title: '출장비 규정', regulation_ids: [], created_at: daysAgo(3), last_active_at: daysAgo(3) },
  { session_id: 's3', title: '휴가 신청', regulation_ids: [], created_at: daysAgo(5), last_active_at: daysAgo(5) },
];

export const chatMessages: Record<string, ChatMessage[]> = {
  s1: [
    { id: 'm1', role: 'user', content: '계약보증금은 얼마야?', created_at: daysAgo(1) },
    { id: 'm2', role: 'assistant', answer_status: 'ANSWERED', content: '계약보증금은 계약금액의 100분의 10 이상입니다 [1].\n다만 국가기관과 계약하는 경우 면제될 수 있습니다 [2].', latency_ms: 2100, created_at: daysAgo(1),
      citations: [
        { ref: 1, chunk_id: 'c-12', regulation_id: 'reg1', regulation_title: '계약사무규정', path: '제3장>제12조(계약보증금)>제2항', quoted_span: '계약금액의 100분의 10 이상', page_no: 4, bbox: [0.1, 0.42, 0.9, 0.47], node_id: 'n-a12-p2' },
        { ref: 2, chunk_id: 'c-13', regulation_id: 'reg1', regulation_title: '계약사무규정', path: '제3장>제13조(보증금 면제)>제1항', quoted_span: '계약보증금의 전부 또는 일부를 면제할 수 있다', page_no: 5, bbox: [0.1, 0.17, 0.9, 0.22], node_id: 'n-a13-p1' },
      ] },
  ],
  s2: [
    { id: 'm3', role: 'user', content: '출장비 한도는?', created_at: daysAgo(3) },
    { id: 'm4', role: 'assistant', answer_status: 'ANSWERED', content: '국내 출장 일비는 1일 3만원이며, 숙박비는 1박 10만원 한도의 실비입니다 [1].', latency_ms: 1800, created_at: daysAgo(3),
      citations: [{ ref: 1, chunk_id: 'c-7', regulation_id: 'reg1', regulation_title: '계약사무규정', path: '제5장>제7조(출장비)>제1항', quoted_span: '일비는 1일 3만원', page_no: 9, bbox: [0.1, 0.22, 0.9, 0.27], node_id: 'n-a7-p1' }] },
  ],
  s3: [
    { id: 'm5', role: 'user', content: '휴가 신청 절차 알려줘', created_at: daysAgo(5) },
    { id: 'm6', role: 'assistant', answer_status: 'NOT_FOUND', content: '등록된 규정에서 해당 내용을 찾을 수 없습니다.', latency_ms: 900, created_at: daysAgo(5), citations: [],
      suggestions: [{ path: '제5장>제7조(출장비)', title: '제7조(출장비)', regulation_id: 'reg1', node_id: 'n-a7' }, { path: '제5장>제9조(급식비)', title: '제9조(급식비)', regulation_id: 'reg1', node_id: 'n-a9' }] },
  ],
};

export const adminStats: AdminStats = {
  documents: { total: 42, done: 40, failed: 2 },
  regulations: { indexed: 12, chunks: 1830 },
  chat: { messages_7d: 210, not_found_rate: 0.08, thumbs_up_rate: 0.87 },
  avg_latency_ms: { extract: 41000, chat_first_token: 1800 },
};

export const adminJobs: AdminJob[] = [
  { id: 'j3', job_type: 'process_document', target_id: 'd3', target_name: '물품계약서.pdf', status: 'FAILED', current_step: 'normalize', progress: 0, error: 'PARSE_FAILED: PDF 폰트 깨짐(U+FFFD 다수) → scan 라우팅 후 OCR 엔진 응답 없음 (OCR_UNAVAILABLE)', attempts: 3, started_at: daysAgo(2), finished_at: daysAgo(2) },
  { id: 'j-reg3', job_type: 'index_regulation', target_id: 'reg3', target_name: '업무매뉴얼(보증)', status: 'FAILED', current_step: 'parse', progress: 10, error: 'PARSE_FAILED: hwp BodyText/Section0 zlib 해제 실패', attempts: 1, started_at: daysAgo(2), finished_at: daysAgo(2) },
];

export const chatLogs: ChatLogItem[] = [
  { id: 'l1', session_id: 's1', question: '계약보증금은 얼마야?', answer: '계약보증금은 계약금액의 100분의 10 이상입니다 [1].', answer_status: 'ANSWERED', citations: [{ path: '제3장>제12조(계약보증금)>제2항' }], feedback: 1, latency_ms: 2100, created_at: daysAgo(1) },
  { id: 'l2', session_id: 's2', question: '출장비 한도', answer: '국내 출장 일비는 1일 3만원…', answer_status: 'ANSWERED', citations: [{ path: '제5장>제7조(출장비)>제1항' }], feedback: null, latency_ms: 1800, created_at: daysAgo(3) },
  { id: 'l3', session_id: 's3', question: '점심 메뉴 추천', answer: '등록된 규정에서 해당 내용을 찾을 수 없습니다.', answer_status: 'NOT_FOUND', citations: [], feedback: -1, latency_ms: 900, created_at: daysAgo(4) },
  { id: 'l4', session_id: 's1', question: '그럼 입찰보증금은?', answer: '입찰보증금은 입찰금액의 100분의 5 이상으로 합니다 [1].', answer_status: 'ANSWERED', citations: [{ path: '제3장>제11조(입찰보증금)>제1항' }], feedback: 1, latency_ms: 2300, created_at: daysAgo(1) },
];

export const evalRunDone = (id: string, suite: EvalRun['suite']): EvalRun => ({
  id, suite, status: 'DONE', started_at: daysAgo(0), finished_at: now(),
  metrics: {
    field_accuracy: { overall: 0.91, by_field: { contract_name: 0.95, contract_amount: 0.95, guarantee_amount: 0.92, contract_date: 0.97, performance_due_date: 0.88, guarantee_period: 0.86, creditor_name: 0.93, creditor_biz_no: 0.82 } },
    bbox_mapping_rate: 0.96, recall_at_5: 0.92, hallucination_rate: 0.04,
  },
  failures: [
    { doc_id: 'd1', doc_name: 'OO공사계약서.hwp', field_code: 'creditor_biz_no', expected: '123-45-67890', got: null },
    { doc_id: 'd4', doc_name: '하자보수계약.hwpx', field_code: 'guarantee_period', expected: '2026-03-05 ~ 2027-03-04', got: '2026-03-05 ~ 2026-12-31' },
    { doc_id: 'd4', doc_name: '하자보수계약.hwpx', field_code: 'performance_due_date', expected: '2026-12-31', got: '2026-12-13' },
  ],
});
