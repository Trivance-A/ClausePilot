import { delay, http, HttpResponse } from 'msw';
import type { ChatMessage, Citation, DocumentListItem, DocumentStatus, ExtractionField, FieldCode, GuaranteeApplication, GuaranteeFormValues, GuaranteeType, RegulationListItem, RiskFinding, Suggestion } from '@/types/api';
import * as F from './fixtures';
import { getContractPdf, getRegulationPdf } from './pdf';

const B = '*/api/v1';
const err = (status: number, code: string, message: string, detail?: Record<string, unknown>) => HttpResponse.json({ error: { code, message, detail } }, { status });
const uid = (p: string) => `${p}${Math.random().toString(36).slice(2, 8)}`;

// ---- 상태 (메모리) ----
const docs: DocumentListItem[] = structuredClone(F.documents);
const fields: Record<string, ExtractionField[]> = { d1: F.makeFields(), d4: F.makeFields().map((f) => ({ ...f, highlights: f.highlights.map((h) => ({ ...h, id: `${h.id}-d4` })) })) };
const risks: Record<string, RiskFinding[]> = { d1: F.makeRisks(), d4: F.makeRisks().filter((r) => r.id === 'r3').map((r) => ({ ...r, highlights: r.highlights.map((h) => ({ ...h, id: `${h.id}-d4` })) })) };
const extStatus: Record<string, 'AUTO' | 'REVIEWED' | 'CONFIRMED'> = {};
const progress: Record<string, { status: DocumentStatus; pct: number; step: string }> = { d2: { status: 'OCR', pct: 45, step: 'ocr' } };
const regs: RegulationListItem[] = structuredClone(F.regulations);
const regParse: Record<string, number> = { reg2: 0 };
const sessions = structuredClone(F.chatSessions);
const messages: Record<string, ChatMessage[]> = structuredClone(F.chatMessages);
const apps: Record<string, GuaranteeApplication> = {};
const evalRuns: Record<string, { suite: 'extraction' | 'retrieval' | 'faithfulness' | 'all'; polls: number }> = {};
let evalHistory: { id: string; suite: 'all' | 'extraction' | 'retrieval' | 'faithfulness' }[] = [{ id: 'ev-prev', suite: 'all' }];

const STEP_FLOW: { status: DocumentStatus; step: string }[] = [{ status: 'NORMALIZING', step: 'normalize' }, { status: 'OCR', step: 'ocr' }, { status: 'EXTRACTING', step: 'extract' }, { status: 'RISK', step: 'risk' }];
function advance(id: string) {
  const p = progress[id];
  if (!p) return;
  p.pct += 35;
  if (p.pct >= 100) {
    const i = STEP_FLOW.findIndex((s) => s.status === p.status);
    if (i < 0 || i === STEP_FLOW.length - 1) {
      const d = docs.find((x) => x.id === id);
      if (d) { d.status = 'DONE'; d.risk_summary = { HIGH: 1, MEDIUM: 2, LOW: 0 }; d.page_count = 3; d.source_type ??= 'native'; }
      fields[id] ??= F.makeFields().map((f) => ({ ...f, highlights: f.highlights.map((h) => ({ ...h, id: `${h.id}-${id}` })) }));
      risks[id] ??= F.makeRisks().map((r) => ({ ...r, id: `${r.id}-${id}`, highlights: r.highlights.map((h) => ({ ...h, id: `${h.id}-${id}` })) }));
      delete progress[id];
      return;
    }
    p.status = STEP_FLOW[i + 1].status; p.step = STEP_FLOW[i + 1].step; p.pct = 10;
    const d = docs.find((x) => x.id === id);
    if (d) d.status = p.status;
  }
}
const findHl = (hid: string) => {
  for (const list of Object.values(fields)) for (const f of list) { const h = f.highlights.find((x) => x.id === hid); if (h) return { h, field: f }; }
  for (const list of Object.values(risks)) for (const r of list) { const h = r.highlights.find((x) => x.id === hid); if (h) return { h, risk: r }; }
  return null;
};

const REQUIRED: Record<GuaranteeType, FieldCode[]> = {
  contract: ['contract_name', 'contract_amount', 'guarantee_amount', 'contract_date', 'performance_due_date', 'guarantee_period', 'creditor_name', 'creditor_biz_no'],
  bid: ['contract_name', 'contract_amount', 'contract_date', 'creditor_name', 'creditor_biz_no'],
  defect: ['contract_name', 'contract_amount', 'guarantee_amount', 'performance_due_date', 'guarantee_period', 'creditor_name', 'creditor_biz_no'],
  payment: ['contract_name', 'contract_amount', 'guarantee_amount', 'contract_date', 'creditor_name', 'creditor_biz_no'],
  advance: ['contract_name', 'contract_amount', 'guarantee_amount', 'contract_date', 'guarantee_period', 'creditor_name', 'creditor_biz_no'],
  other: ['contract_name', 'contract_amount', 'guarantee_amount', 'contract_date', 'performance_due_date', 'guarantee_period', 'creditor_name', 'creditor_biz_no'],
};

const sse = (lines: { ev: string; data: unknown; wait?: number }[]) => {
  const enc = new TextEncoder();
  const stream = new ReadableStream({
    async start(c) {
      for (const l of lines) { await delay(l.wait ?? 60); c.enqueue(enc.encode(`event: ${l.ev}\ndata: ${JSON.stringify(l.data)}\n\n`)); }
      c.close();
    },
  });
  return new HttpResponse(stream, { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' } });
};

export const handlers = [
  // ---- Auth ----
  http.post(`${B}/auth/login`, async ({ request }) => {
    const { email } = (await request.json()) as { email: string };
    await delay(300);
    const admin = email.toLowerCase().startsWith('admin');
    return HttpResponse.json({ access_token: `mock-${admin ? 'admin' : 'user'}`, token_type: 'bearer', user: { id: admin ? 'u-admin' : 'u-user', name: admin ? '홍길동' : '김조합', email, role: admin ? 'admin' : 'user' } });
  }),
  http.get(`${B}/auth/me`, ({ request }) => {
    const auth = request.headers.get('Authorization') ?? '';
    if (!auth.startsWith('Bearer mock-')) return err(401, 'UNAUTHORIZED', '토큰 없음/만료');
    const admin = auth.includes('admin');
    return HttpResponse.json({ id: admin ? 'u-admin' : 'u-user', name: admin ? '홍길동' : '김조합', email: admin ? 'admin@example.com' : 'user@example.com', role: admin ? 'admin' : 'user' });
  }),

  // ---- Documents ----
  http.get(`${B}/documents`, ({ request }) => {
    const u = new URL(request.url);
    const q = u.searchParams.get('q')?.toLowerCase();
    const status = u.searchParams.get('status')?.split(',');
    const page = Number(u.searchParams.get('page') ?? 1), size = Number(u.searchParams.get('size') ?? 20);
    let items = docs.filter((d) => (!q || d.original_name.toLowerCase().includes(q)) && (!status || status.includes(d.status)));
    items = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
    return HttpResponse.json({ items: items.slice((page - 1) * size, page * size), total: items.length, page, size });
  }),
  http.post(`${B}/documents`, async ({ request }) => {
    const form = await request.formData();
    const files = form.getAll('files') as File[];
    await delay(600);
    const items = files.map((f) => {
      const id = uid('d');
      const ext = f.name.split('.').pop()?.toLowerCase() ?? 'pdf';
      docs.unshift({ id, original_name: f.name, original_format: ext, source_type: ext === 'pdf' ? 'native' : 'scan', page_count: null, status: 'NORMALIZING', risk_summary: null, created_at: F.now() });
      progress[id] = { status: 'NORMALIZING', pct: 20, step: 'normalize' };
      return { document_id: id, job_id: uid('j'), original_name: f.name, status: 'UPLOADED' };
    });
    return HttpResponse.json({ items }, { status: 202 });
  }),
  http.get(`${B}/documents/:id/status`, ({ params }) => {
    const id = String(params.id);
    const d = docs.find((x) => x.id === id);
    if (!d) return err(404, 'NOT_FOUND', '문서 없음');
    if (d.status === 'FAILED') return HttpResponse.json({ status: 'FAILED', job: { id: 'j3', current_step: 'normalize', progress: 0, error: 'PARSE_FAILED: PDF 폰트 깨짐(U+FFFD 다수) → OCR 엔진 응답 없음' } });
    const p = progress[id];
    if (!p) return HttpResponse.json({ status: d.status, job: { id: 'j-done', current_step: null, progress: 100, error: null } });
    const res = { status: p.status, job: { id: `j-${id}`, current_step: p.step, progress: p.pct, error: null } };
    advance(id);
    return HttpResponse.json(res);
  }),
  http.get(`${B}/documents/:id/pdf`, async () => new HttpResponse(await getContractPdf(), { headers: { 'Content-Type': 'application/pdf' } })),
  http.get(`${B}/documents/:id/export/pdf`, async () => new HttpResponse(await getContractPdf(), { headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="highlight.pdf"' } })),
  http.get(`${B}/documents/:id/lines`, ({ params, request }) => {
    const page = Number(new URL(request.url).searchParams.get('page') ?? 1);
    const id = String(params.id);
    const lines = F.MOCK_LINES.filter((l) => l.page === page).map((l) => ({ id: `${id}-L${l.page}-${l.no}`, line_id: `L${l.page}-${l.no}`, text: l.text, bbox: l.bbox, confidence: l.conf ?? 0.96, source: page === 2 ? 'paddle' : 'pdf_text', table_cell: l.cell ?? null }));
    return HttpResponse.json({ page_no: page, lines });
  }),
  http.get(`${B}/documents/:id`, ({ params }) => {
    const d = docs.find((x) => x.id === params.id);
    if (!d) return err(404, 'NOT_FOUND', '문서 없음');
    return HttpResponse.json({ ...d, pages: d.status === 'DONE' ? F.PAGES.slice(0, d.page_count ?? 3) : [], extraction: fields[d.id] ? { id: `ext-${d.id}`, status: extStatus[d.id] ?? 'AUTO', model_name: 'qwen2.5-14b', created_at: d.created_at } : null });
  }),
  http.post(`${B}/documents/:id/reprocess`, async ({ params, request }) => {
    const id = String(params.id);
    const body = (await request.json().catch(() => ({}))) as { from_step?: string };
    const d = docs.find((x) => x.id === id);
    if (!d) return err(404, 'NOT_FOUND', '문서 없음');
    const start = body.from_step === 'risk' ? 3 : body.from_step === 'extract' ? 2 : body.from_step === 'ocr' ? 1 : 0;
    d.status = STEP_FLOW[start].status;
    progress[id] = { status: STEP_FLOW[start].status, pct: 10, step: STEP_FLOW[start].step };
    return HttpResponse.json({ job_id: uid('j') }, { status: 202 });
  }),
  http.delete(`${B}/documents/:id`, ({ params }) => { const i = docs.findIndex((x) => x.id === params.id); if (i >= 0) docs.splice(i, 1); return new HttpResponse(null, { status: 204 }); }),

  // ---- Extraction / Highlight ----
  http.get(`${B}/documents/:id/extractions`, ({ params }) => {
    const id = String(params.id);
    const f = fields[id];
    if (!f) return err(404, 'NOT_FOUND', '추출 결과 없음');
    return HttpResponse.json({ extraction_id: `ext-${id}`, status: extStatus[id] ?? 'AUTO', fields: f, color_map: F.COLOR_MAP });
  }),
  http.patch(`${B}/documents/:id/extractions/fields/:code`, async ({ params, request }) => {
    const id = String(params.id);
    const f = fields[id]?.find((x) => x.field_code === params.code);
    if (!f) return err(404, 'NOT_FOUND', '필드 없음');
    const body = (await request.json()) as Partial<ExtractionField>;
    if (body.raw_value !== undefined) { f.raw_value = body.raw_value; f.mapping_method = f.mapping_method === 'none' ? 'manual' : f.mapping_method; }
    if (body.normalized_value !== undefined) f.normalized_value = body.normalized_value;
    if (body.is_confirmed !== undefined) f.is_confirmed = body.is_confirmed;
    if (body.reviewer_note !== undefined) f.reviewer_note = body.reviewer_note;
    if (body.confidence === undefined && body.raw_value !== undefined) f.confidence = 1;
    extStatus[id] = fields[id].every((x) => x.is_confirmed) ? 'CONFIRMED' : 'REVIEWED';
    await delay(200);
    return HttpResponse.json(f);
  }),
  http.post(`${B}/documents/:id/highlights`, async ({ params, request }) => {
    const id = String(params.id);
    const body = (await request.json()) as { field_code?: FieldCode; risk_finding_id?: string; page_no: number; bbox: [number, number, number, number] };
    const h = { id: uid('h-manual-'), page_no: body.page_no, bbox: body.bbox, origin: 'manual' as const, ocr_line_id: null };
    if (body.field_code) {
      const f = fields[id]?.find((x) => x.field_code === body.field_code);
      if (!f) return err(404, 'NOT_FOUND', '필드 없음');
      f.highlights.push(h); f.mapping_method = 'manual';
      if (!f.raw_value) { const line = F.MOCK_LINES.find((l) => l.page === body.page_no && Math.abs(l.bbox[1] - body.bbox[1]) < 0.02); if (line) { f.raw_value = line.text; f.normalized_value = { text: line.text }; f.confidence = 1; } }
    } else if (body.risk_finding_id) {
      const r = risks[id]?.find((x) => x.id === body.risk_finding_id);
      if (!r) return err(404, 'NOT_FOUND', '위험조항 없음');
      r.highlights.push(h);
    } else return err(400, 'VALIDATION_ERROR', 'field_code 또는 risk_finding_id 필요');
    return HttpResponse.json(h, { status: 201 });
  }),
  http.patch(`${B}/highlights/:hid`, async ({ params, request }) => {
    const found = findHl(String(params.hid));
    if (!found) return err(404, 'NOT_FOUND', '하이라이트 없음');
    const body = (await request.json()) as { bbox: [number, number, number, number]; page_no?: number };
    found.h.bbox = body.bbox; if (body.page_no) found.h.page_no = body.page_no; found.h.origin = 'manual';
    if (found.field) found.field.mapping_method = 'manual';
    return HttpResponse.json(found.h);
  }),
  http.delete(`${B}/highlights/:hid`, ({ params }) => {
    const hid = String(params.hid);
    for (const list of Object.values(fields)) for (const f of list) f.highlights = f.highlights.filter((h) => h.id !== hid);
    for (const list of Object.values(risks)) for (const r of list) r.highlights = r.highlights.filter((h) => h.id !== hid);
    return new HttpResponse(null, { status: 204 });
  }),

  // ---- Risk ----
  http.get(`${B}/documents/:id/risks`, ({ params }) => {
    const items = risks[String(params.id)] ?? [];
    const summary = { HIGH: 0, MEDIUM: 0, LOW: 0 };
    items.filter((r) => r.status !== 'DISMISSED').forEach((r) => { summary[r.severity]++; });
    return HttpResponse.json({ items, summary });
  }),
  http.patch(`${B}/risks/:rid`, async ({ params, request }) => {
    const body = (await request.json()) as { status: RiskFinding['status']; note?: string };
    for (const list of Object.values(risks)) { const r = list.find((x) => x.id === params.rid); if (r) { r.status = body.status; r.note = body.note ?? null; return HttpResponse.json(r); } }
    return err(404, 'NOT_FOUND', '위험조항 없음');
  }),
  http.post(`${B}/documents/:id/risks/rerun`, ({ params }) => { const id = String(params.id); progress[id] = { status: 'RISK', pct: 30, step: 'risk' }; const d = docs.find((x) => x.id === id); if (d) d.status = 'RISK'; return HttpResponse.json({ job_id: uid('j') }, { status: 202 }); }),

  // ---- Guarantee (Auto-fill) ----
  http.post(`${B}/guarantee-applications`, async ({ request }) => {
    const body = (await request.json()) as { document_id: string; guarantee_type: GuaranteeType };
    const f = fields[body.document_id];
    if (!f) return err(409, 'INVALID_STATE', '분석이 완료되지 않은 문서입니다');
    const get = (c: FieldCode) => f.find((x) => x.field_code === c)!;
    const nv = (c: FieldCode) => (get(c).normalized_value ?? {}) as Record<string, unknown>;
    const form_values: GuaranteeFormValues = {
      contract_name: (nv('contract_name').text as string) ?? get('contract_name').raw_value, contract_amount: (nv('contract_amount').amount as number) ?? null,
      guarantee_amount: (nv('guarantee_amount').amount as number) ?? null, contract_date: (nv('contract_date').date as string) ?? null,
      performance_due_date: (nv('performance_due_date').date as string) ?? null,
      guarantee_period: nv('guarantee_period').start ? { start: nv('guarantee_period').start as string, end: nv('guarantee_period').end as string } : null,
      creditor_name: (nv('creditor_name').text as string) ?? get('creditor_name').raw_value, creditor_biz_no: (nv('creditor_biz_no').text as string) ?? null,
    };
    const field_sources: GuaranteeApplication['field_sources'] = {};
    for (const x of f) if (x.raw_value) field_sources[x.field_code] = { field_id: `f-${x.field_code}`, confidence: x.confidence, highlight_ids: x.highlights.map((h) => h.id), page_no: x.highlights[0]?.page_no ?? null };
    const app: GuaranteeApplication = { id: uid('g'), document_id: body.document_id, guarantee_type: body.guarantee_type, status: 'DRAFT', form_values, field_sources, required_fields: REQUIRED[body.guarantee_type], viewer_url: `/documents/${body.document_id}/viewer?field=contract_amount`, risk_summary: docs.find((d) => d.id === body.document_id)?.risk_summary ?? undefined };
    apps[app.id] = app;
    await delay(500);
    return HttpResponse.json(app, { status: 201 });
  }),
  http.get(`${B}/guarantee-applications/:id`, ({ params }) => apps[String(params.id)] ? HttpResponse.json(apps[String(params.id)]) : err(404, 'NOT_FOUND', '없음')),
  http.patch(`${B}/guarantee-applications/:id`, async ({ params, request }) => {
    const app = apps[String(params.id)];
    if (!app) return err(404, 'NOT_FOUND', '없음');
    const body = (await request.json()) as { form_values: GuaranteeFormValues; status?: 'DRAFT' | 'SUBMITTED' };
    app.form_values = body.form_values; if (body.status) app.status = body.status;
    await delay(300);
    return HttpResponse.json(app);
  }),

  // ---- Regulations ----
  http.get(`${B}/regulations`, () => {
    for (const r of regs) if (r.status === 'PARSING' || r.status === 'UPLOADED') { regParse[r.id] = (regParse[r.id] ?? 0) + 1; if (regParse[r.id] > 3) { r.status = 'INDEXED'; r.chunk_count = 97; } else r.status = 'PARSING'; }
    return HttpResponse.json({ items: regs });
  }),
  http.post(`${B}/regulations`, async ({ request }) => {
    const form = await request.formData();
    const title = String(form.get('title'));
    const prev = regs.filter((r) => r.title === title && r.status !== 'ARCHIVED');
    prev.forEach((r) => { r.status = 'ARCHIVED'; });
    const id = uid('reg');
    regs.unshift({ id, title, doc_type: String(form.get('doc_type')) as RegulationListItem['doc_type'], version: (prev[0]?.version ?? 0) + 1, status: 'UPLOADED', chunk_count: null, effective_date: (form.get('effective_date') as string) || null, created_at: F.now() });
    regParse[id] = 0;
    await delay(500);
    return HttpResponse.json({ regulation_id: id, job_id: uid('j'), version: (prev[0]?.version ?? 0) + 1, status: 'UPLOADED' }, { status: 202 });
  }),
  http.get(`${B}/regulations/:id/pdf`, async () => new HttpResponse(await getRegulationPdf(), { headers: { 'Content-Type': 'application/pdf' } })),
  http.get(`${B}/regulations/:id/nodes/:nodeId`, ({ params }) => { const n = F.regNodes[String(params.nodeId)]; return n ? HttpResponse.json(n) : err(404, 'NOT_FOUND', '노드 없음'); }),
  http.get(`${B}/regulations/:id`, ({ params }) => { const r = regs.find((x) => x.id === params.id); return r ? HttpResponse.json({ ...r, tree: r.status === 'INDEXED' ? F.regTree : [] }) : err(404, 'NOT_FOUND', '규정 없음'); }),
  http.post(`${B}/regulations/:id/reindex`, ({ params }) => { const r = regs.find((x) => x.id === params.id); if (r) { r.status = 'PARSING'; r.error = null; regParse[r.id] = 0; } return HttpResponse.json({ job_id: uid('j') }, { status: 202 }); }),
  http.delete(`${B}/regulations/:id`, ({ params }) => { const r = regs.find((x) => x.id === params.id); if (r) r.status = 'ARCHIVED'; return new HttpResponse(null, { status: 204 }); }),

  // ---- Search (디버그) ----
  http.post(`${B}/search`, () => HttpResponse.json({ results: [{ chunk_id: 'c-12', regulation_title: '계약사무규정', path: '제3장>제12조>제2항', content: F.regNodes['n-a12-p2'].content, bm25_score: 8.1, vector_score: 0.81, rrf_score: 0.032, rerank_score: 0.94 }], latency_ms: 180 })),

  // ---- Chat ----
  http.get(`${B}/chat/sessions`, () => HttpResponse.json({ items: [...sessions].sort((a, b) => (b.last_active_at ?? '').localeCompare(a.last_active_at ?? '')) })),
  http.post(`${B}/chat/sessions`, async ({ request }) => {
    const body = (await request.json()) as { title?: string; regulation_ids: string[] };
    const s = { session_id: uid('s'), title: body.title ?? null, regulation_ids: body.regulation_ids ?? [], created_at: F.now(), last_active_at: F.now() };
    sessions.unshift(s); messages[s.session_id] = [];
    return HttpResponse.json({ session_id: s.session_id }, { status: 201 });
  }),
  http.get(`${B}/chat/sessions/:sid/messages`, ({ params }) => HttpResponse.json({ items: messages[String(params.sid)] ?? [] })),
  http.post(`${B}/chat/sessions/:sid/messages`, async ({ params, request }) => {
    const sid = String(params.sid);
    const body = (await request.json()) as { content: string; stream?: boolean };
    const q = body.content;
    const s = sessions.find((x) => x.session_id === sid);
    if (s) { s.last_active_at = F.now(); s.title ??= q.slice(0, 20); }
    (messages[sid] ??= []).push({ id: uid('m'), role: 'user', content: q, created_at: F.now() });
    const mid = uid('m');
    const cite = (ref: number, nodeId: string): Citation => { const n = F.regNodes[nodeId]; return { ref, chunk_id: n.chunk_ids[0], regulation_id: 'reg1', regulation_title: '계약사무규정', path: n.path, quoted_span: '', page_no: n.page_no, bbox: n.bbox, node_id: nodeId }; };

    let content: string; let citations: Citation[] = []; let suggestions: Suggestion[] | undefined; let status: ChatMessage['answer_status'] = 'ANSWERED';
    if (/점심|메뉴|날씨|주식|추천/.test(q)) {
      status = 'NOT_FOUND'; content = '등록된 규정에서 해당 내용을 찾을 수 없습니다.';
      suggestions = [{ path: '제5장>제7조(출장비)', title: '제7조(출장비)', regulation_id: 'reg1', node_id: 'n-a7' }, { path: '제5장>제9조(급식비)', title: '제9조(급식비)', regulation_id: 'reg1', node_id: 'n-a9' }, { path: '제1장>제2조(정의)', title: '제2조(정의)', regulation_id: 'reg1', node_id: 'n-a2' }];
    } else if (/입찰/.test(q)) {
      content = '입찰보증금은 입찰금액의 100분의 5 이상으로 합니다 [1]. 현금 또는 보증서로 납부할 수 있습니다 [1].';
      citations = [{ ...cite(1, 'n-a11-p1'), quoted_span: '입찰금액의 100분의 5 이상' }];
    } else if (/출장|일비|숙박/.test(q)) {
      content = '국내 출장의 일비는 1일 3만원이며, 숙박비는 실비로 1박 10만원 한도입니다 [1].';
      citations = [{ ...cite(1, 'n-a7-p1'), quoted_span: '일비는 1일 3만원' }];
    } else if (/하자/.test(q)) {
      content = '하자보수보증금은 계약금액의 100분의 2 이상 100분의 10 이하로 합니다 [1].';
      citations = [{ ...cite(1, 'n-a15'), quoted_span: '100분의 2 이상 100분의 10 이하' }];
    } else {
      content = '계약보증금은 계약금액의 100분의 10 이상입니다 [1]. 다만 국가기관·지방자치단체 또는 공공기관과 계약하는 경우 면제될 수 있습니다 [2].';
      citations = [{ ...cite(1, 'n-a12-p2'), quoted_span: '계약금액의 100분의 10 이상' }, { ...cite(2, 'n-a13-p1'), quoted_span: '계약보증금의 전부 또는 일부를 면제할 수 있다' }];
    }
    const final: ChatMessage = { id: mid, role: 'assistant', content, answer_status: status, citations, suggestions, latency_ms: 2300, created_at: F.now() };
    messages[sid].push(final);
    if (body.stream === false) return HttpResponse.json(final);

    const events: { ev: string; data: unknown; wait?: number }[] = [
      { ev: 'status', data: { stage: 'rewrite', rewritten_query: `${q} 계약사무규정` }, wait: 400 },
      { ev: 'status', data: { stage: 'retrieve', hits: status === 'NOT_FOUND' ? 0 : 5 }, wait: 500 },
    ];
    if (status === 'ANSWERED') {
      const tokens = content.match(/[^\s]+\s*/g) ?? [content];
      let seen = new Set<number>();
      tokens.forEach((t, i) => {
        events.push({ ev: 'token', data: { text: t }, wait: i === 0 ? 700 : 70 });
        for (const m of t.matchAll(/\[(\d+)\]/g)) { const ref = Number(m[1]); if (!seen.has(ref)) { seen.add(ref); const c = citations.find((x) => x.ref === ref); if (c) events.push({ ev: 'citation', data: c, wait: 10 }); } }
      });
      seen = new Set();
    }
    events.push({ ev: 'done', data: { message_id: mid, answer_status: status, latency_ms: 2300, suggestions, content: status === 'NOT_FOUND' ? content : undefined }, wait: 200 });
    return sse(events);
  }),
  http.post(`${B}/chat/messages/:mid/feedback`, async () => { await delay(150); return HttpResponse.json({ ok: true }, { status: 201 }); }),

  // ---- Admin / Eval ----
  http.get(`${B}/admin/stats`, () => HttpResponse.json(F.adminStats)),
  http.get(`${B}/admin/jobs`, ({ request }) => { const st = new URL(request.url).searchParams.get('status'); return HttpResponse.json({ items: F.adminJobs.filter((j) => !st || j.status === st) }); }),
  http.get(`${B}/admin/logs/chat`, ({ request }) => {
    const u = new URL(request.url);
    const st = u.searchParams.get('answer_status');
    const items = F.chatLogs.filter((l) => !st || l.answer_status === st);
    if (u.searchParams.get('format') === 'csv') {
      const csv = ['id,question,answer_status,citations,feedback,latency_ms,created_at', ...items.map((l) => [l.id, JSON.stringify(l.question), l.answer_status, JSON.stringify(l.citations.map((c) => c.path).join('|')), l.feedback ?? '', l.latency_ms, l.created_at].join(','))].join('\n');
      return new HttpResponse(`﻿${csv}`, { headers: { 'Content-Type': 'text/csv; charset=utf-8' } });
    }
    return HttpResponse.json({ items, total: items.length, page: 1, size: 20 });
  }),
  http.post(`${B}/eval/run`, async ({ request }) => {
    const { suite } = (await request.json()) as { suite: 'all' | 'extraction' | 'retrieval' | 'faithfulness' };
    const id = uid('ev');
    evalRuns[id] = { suite, polls: 0 };
    evalHistory = [{ id, suite }, ...evalHistory];
    return HttpResponse.json({ run_id: id }, { status: 202 });
  }),
  http.get(`${B}/eval/runs/:id`, ({ params }) => {
    const id = String(params.id);
    const r = evalRuns[id];
    if (!r) return HttpResponse.json(F.evalRunDone(id, 'all'));
    r.polls++;
    if (r.polls < 3) return HttpResponse.json({ id, suite: r.suite, status: 'RUNNING', started_at: F.now(), finished_at: null, metrics: null, failures: [] });
    return HttpResponse.json(F.evalRunDone(id, r.suite));
  }),
  http.get(`${B}/eval/runs`, () => HttpResponse.json({ items: evalHistory.map((h) => ({ ...F.evalRunDone(h.id, h.suite), status: evalRuns[h.id] && evalRuns[h.id].polls < 3 ? 'RUNNING' : 'DONE' })) })),
];
