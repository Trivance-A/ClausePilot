import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCheck, ChevronDown, Download, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { isInProgress, useDocument, useDocumentStatus, useReprocessDocument } from '@/api/documents';
import { useConfirmAll, useCreateHighlight, useDeleteHighlight, useExtractions, usePatchField, usePatchHighlight } from '@/api/extractions';
import { usePatchRisk, useRerunRisks, useRisks } from '@/api/risks';
import { api, downloadFile, errorMessage } from '@/lib/api';
import { useIsAdmin } from '@/stores/auth';
import { useViewerStore } from '@/stores/viewer';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ProgressCard } from '@/components/documents/ProgressCard';
import { PdfViewer } from '@/components/viewer/PdfViewer';
import { FieldPanel, fieldColor } from '@/components/viewer/FieldPanel';
import { RiskPanel } from '@/components/viewer/RiskPanel';
import { OcrLinePanel } from '@/components/viewer/OcrLinePanel';
import { Legend } from '@/components/viewer/Legend';
import { SEVERITY_COLOR, type OverlayItem } from '@/components/viewer/types';
import type { BBox, ExtractionField, FieldCode, OcrLine, RiskFinding } from '@/types/api';
import { FIELD_LABELS } from '@/types/api';

const SOURCE_LABEL: Record<string, string> = { native: '네이티브', scan: '스캔', mixed: '혼합' };

export function ViewerPage() {
  const { id = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const isAdmin = useIsAdmin();
  const store = useViewerStore();

  const { data: doc, isLoading: docLoading, error: docError } = useDocument(id);
  const ready = !!doc && doc.status === 'DONE';
  const { data: ext } = useExtractions(id, !!doc && !isInProgress(doc.status));
  const { data: risks } = useRisks(id, !!doc && !isInProgress(doc.status));
  const { data: status } = useDocumentStatus(id, !!doc && isInProgress(doc.status));

  const patchField = usePatchField(id);
  const confirmAll = useConfirmAll(id);
  const createHl = useCreateHighlight(id);
  const patchHl = usePatchHighlight(id);
  const deleteHl = useDeleteHighlight(id);
  const patchRisk = usePatchRisk(id);
  const rerunRisks = useRerunRisks(id);
  const reprocess = useReprocessDocument();

  const [search, setSearch] = useState<{ q: string; matches: { page_no: number; bbox: BBox; text: string }[]; idx: number }>({ q: '', matches: [], idx: 0 });
  const [showLineBoxes, setShowLineBoxes] = useState(false);
  const linesCache = useRef<Record<number, OcrLine[]>>({});
  const [linesVersion, setLinesVersion] = useState(0);

  // 화면 진입 시 상태 초기화
  useEffect(() => { store.reset(); return () => store.reset(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [id]);

  // Esc → 선택 모드 해제
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') useViewerStore.getState().exitSelectMode(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  const goToField = useCallback((f: ExtractionField) => {
    const h = f.highlights[0];
    store.selectField(f.field_code);
    if (h) store.scrollTo({ page_no: h.page_no, bbox: h.bbox, highlightId: h.id });
  }, [store]);

  // V-13 ?field=... 자동 이동 (Auto-fill Demo 연결)
  const autoRan = useRef(false);
  useEffect(() => {
    const code = searchParams.get('field') as FieldCode | null;
    if (!code || !ext || autoRan.current) return;
    const f = ext.fields.find((x) => x.field_code === code);
    if (f) { autoRan.current = true; setTimeout(() => goToField(f), 400); }
  }, [searchParams, ext, goToField]);

  const goToRisk = (r: RiskFinding) => {
    const h = r.highlights[0];
    store.selectRisk(r.id);
    if (h) store.scrollTo({ page_no: h.page_no, bbox: h.bbox, highlightId: h.id });
  };

  // 오버레이 목록 조립
  const items = useMemo<OverlayItem[]>(() => {
    const arr: OverlayItem[] = [];
    const sel = store.selectedFieldCode;
    const selRisk = store.selectedRiskId;
    const anySel = !!sel || !!selRisk;
    ext?.fields.forEach((f) => f.highlights.forEach((h) => arr.push({
      id: h.id, kind: 'field', page_no: h.page_no, bbox: h.bbox, color: fieldColor(ext.color_map, f), label: f.label,
      fieldCode: f.field_code, origin: h.origin, dimmed: anySel && sel !== f.field_code, emphasized: sel === f.field_code,
    })));
    risks?.items.filter((r) => r.status !== 'DISMISSED').forEach((r) => r.highlights.forEach((h) => arr.push({
      id: h.id, kind: 'risk', page_no: h.page_no, bbox: h.bbox, color: SEVERITY_COLOR[r.severity], label: r.title,
      riskId: r.id, severity: r.severity, origin: h.origin, dimmed: anySel && selRisk !== r.id, emphasized: selRisk === r.id,
    })));
    search.matches.forEach((m, i) => arr.push({ id: `search-${i}`, kind: 'search', page_no: m.page_no, bbox: m.bbox, color: '#ca8a04', label: m.text, emphasized: i === search.idx }));
    if (showLineBoxes && store.tab === 'lines') {
      Object.entries(linesCache.current).forEach(([p, lines]) => lines.forEach((l) => arr.push({ id: `line-${l.id}`, kind: 'line', page_no: Number(p), bbox: l.bbox, color: '#64748b', label: l.line_id })));
    }
    return arr;
  }, [ext, risks, store.selectedFieldCode, store.selectedRiskId, store.tab, search, showLineBoxes, linesVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  // V-3 오버레이 클릭 → 우측 패널 포커스
  const onOverlayClick = (it: OverlayItem) => {
    if (it.kind === 'field' && it.fieldCode) { store.setTab('fields'); store.selectField(it.fieldCode); store.pulse(it.id); setTimeout(() => store.pulse(null), 1500); }
    else if (it.kind === 'risk' && it.riskId) { store.setTab('risks'); store.selectRisk(it.riskId); }
  };
  // V-7 드래그/리사이즈 → PATCH
  const onOverlayChange = (it: OverlayItem, bbox: BBox) => {
    if (it.kind !== 'field' && it.kind !== 'risk') return;
    patchHl.mutate({ hid: it.id, bbox, page_no: it.page_no }, { onError: (e) => toast.error(errorMessage(e)) });
  };
  // V-8 우클릭 삭제
  const onOverlayDelete = (it: OverlayItem) => {
    if (it.kind !== 'field' && it.kind !== 'risk') return;
    if (!confirm(`'${it.label}' 하이라이트를 삭제할까요?`)) return;
    deleteHl.mutate(it.id, { onSuccess: () => toast.success('삭제했습니다'), onError: (e) => toast.error(errorMessage(e)) });
  };
  // V-6 선택 모드 완료 → POST /highlights (origin=manual) 또는 기존 PATCH
  const onSelectionDone = (page_no: number, bbox: BBox) => {
    const t = store.selectTarget;
    if (!t) return;
    const done = () => { store.exitSelectMode(); toast.success('위치를 지정했습니다'); };
    const fail = (e: unknown) => toast.error(errorMessage(e));
    if (t.kind === 'field') {
      if (t.replaceHighlightId) patchHl.mutate({ hid: t.replaceHighlightId, bbox, page_no }, { onSuccess: done, onError: fail });
      else createHl.mutate({ field_code: t.fieldCode, page_no, bbox }, { onSuccess: done, onError: fail });
    } else {
      createHl.mutate({ risk_finding_id: t.riskId, page_no, bbox }, { onSuccess: done, onError: fail });
    }
  };

  // V-14 텍스트 검색 (로드된 /lines 대상 클라이언트 검색)
  const runSearch = async (q: string) => {
    if (!q.trim()) { setSearch({ q: '', matches: [], idx: 0 }); return; }
    const pageCount = doc?.page_count ?? 1;
    for (let p = 1; p <= pageCount; p++) {
      if (!linesCache.current[p]) {
        try { const r = await api<{ page_no: number; lines: OcrLine[] }>(`/documents/${id}/lines`, { query: { page: p } }); linesCache.current[p] = r.lines; } catch { /* skip */ }
      }
    }
    const needle = q.toLowerCase();
    const matches: { page_no: number; bbox: BBox; text: string }[] = [];
    Object.entries(linesCache.current).forEach(([p, lines]) => lines.forEach((l) => { if (l.text.toLowerCase().includes(needle)) matches.push({ page_no: Number(p), bbox: l.bbox, text: l.text }); }));
    matches.sort((a, b) => a.page_no - b.page_no || a.bbox[1] - b.bbox[1]);
    setSearch({ q, matches, idx: 0 });
    if (matches.length) store.scrollTo({ page_no: matches[0].page_no, bbox: matches[0].bbox, highlightId: 'search-0' });
    else toast.info('검색 결과가 없습니다');
  };
  const navSearch = (dir: 1 | -1) => {
    if (!search.matches.length) return;
    const idx = (search.idx + dir + search.matches.length) % search.matches.length;
    setSearch({ ...search, idx });
    const m = search.matches[idx];
    store.scrollTo({ page_no: m.page_no, bbox: m.bbox, highlightId: `search-${idx}` });
  };

  const exportPdf = () => downloadFile(`/documents/${id}/export/pdf`, `${doc?.original_name?.replace(/\.[^.]+$/, '') ?? 'document'}_highlight.pdf`, { include: 'fields,risks' })
    .then(() => toast.success('PDF를 내려받았습니다')).catch((e) => toast.error(errorMessage(e)));

  const allConfirmed = !!ext && ext.fields.every((f) => f.is_confirmed);
  const riskCount = risks?.items.filter((r) => r.status === 'OPEN').length ?? 0;

  if (docLoading) return <div className="p-8 text-sm text-muted-foreground">문서 정보를 불러오는 중…</div>;
  if (docError || !doc) return <div className="p-8 text-sm text-red-600">문서를 불러올 수 없습니다: {errorMessage(docError)}</div>;

  return (
    <div className="flex h-[calc(100vh-56px)] min-h-0 flex-col">
      {/* 헤더 */}
      <div className="flex shrink-0 items-center gap-3 border-b bg-white px-4 py-2">
        <Button variant="ghost" size="sm" asChild><Link to="/documents"><ArrowLeft /> 목록</Link></Button>
        <div className="flex items-center gap-2">
          <span className="font-semibold">{doc.original_name}</span>
          <span className="text-xs text-muted-foreground">({doc.source_type ? SOURCE_LABEL[doc.source_type] : '-'} · {doc.page_count ?? '?'}p)</span>
          {ext && <Badge variant={ext.status === 'CONFIRMED' ? 'success' : ext.status === 'REVIEWED' ? 'info' : 'muted'}>{ext.status}</Badge>}
          {searchParams.get('field') && (
            <Badge variant="info" className="cursor-pointer" onClick={() => setSearchParams({})}>Auto-fill 연결: {FIELD_LABELS[searchParams.get('field') as FieldCode] ?? searchParams.get('field')} ✕</Badge>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline" size="sm" disabled={isInProgress(doc.status)}><RefreshCw /> 재추출 <ChevronDown /></Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => reprocess.mutate({ id, from_step: 'ocr' }, { onSuccess: () => toast.success('OCR부터 재처리합니다'), onError: (e) => toast.error(errorMessage(e)) })}>OCR부터 재처리</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => reprocess.mutate({ id, from_step: 'extract' }, { onSuccess: () => toast.success('항목 재추출을 시작합니다'), onError: (e) => toast.error(errorMessage(e)) })}>항목 재추출</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => rerunRisks.mutate(undefined, { onSuccess: () => toast.success('위험조항 재탐지를 시작합니다'), onError: (e) => toast.error(errorMessage(e)) })}>위험조항 재탐지</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="outline" size="sm" onClick={exportPdf} disabled={!ready}><Download /> PDF 내보내기</Button>
          <Button variant="success" size="sm" disabled={!ext || allConfirmed} loading={confirmAll.isPending}
            onClick={() => { if (confirm('모든 항목을 확정 처리할까요?')) confirmAll.mutate(ext!.fields, { onSuccess: () => toast.success('전체 항목을 확정했습니다'), onError: (e) => toast.error(errorMessage(e)) }); }}>
            <CheckCheck /> {allConfirmed ? '확정 완료' : '확정'}
          </Button>
        </div>
      </div>

      {isInProgress(doc.status) && (
        <div className="border-b bg-amber-50 px-4 py-2">
          <ProgressCard documentId={id} name={`분석 진행 중 (${status?.job?.current_step ?? doc.status})`} />
        </div>
      )}
      {doc.status === 'FAILED' && (
        <div className="border-b bg-red-50 px-4 py-2 text-sm text-red-700">처리 실패: {status?.job?.error ?? '상세 오류 없음'} — 상단 [재추출]로 재처리할 수 있습니다.</div>
      )}

      <div className="flex min-h-0 flex-1">
        {/* 좌: PDF Viewer */}
        <div className="min-w-0 flex-1 border-r">
          <PdfViewer
            pdfPath={`/documents/${id}/pdf`}
            pages={doc.pages ?? []}
            pageCount={doc.page_count ?? 0}
            items={items}
            editable={isAdmin}
            onOverlayClick={onOverlayClick}
            onOverlayChange={onOverlayChange}
            onOverlayDelete={onOverlayDelete}
            onSelectionDone={onSelectionDone}
            onSearch={runSearch}
            searchCount={search.matches.length}
            searchIndex={search.idx}
            onSearchNav={navSearch}
            selectionLabel={store.selectTarget?.kind === 'field' ? `${FIELD_LABELS[store.selectTarget.fieldCode]} 위치를 드래그로 지정` : store.selectTarget ? '위험조항 근거 위치를 드래그로 지정' : null}
          />
        </div>

        {/* 우: 패널 */}
        <aside className="flex w-[380px] shrink-0 flex-col bg-white">
          <Tabs value={store.tab} onValueChange={(v) => store.setTab(v as typeof store.tab)} className="px-2 pt-2">
            <TabsList className="w-full">
              <TabsTrigger value="fields" className="flex-1">추출항목</TabsTrigger>
              <TabsTrigger value="risks" className="flex-1">위험조항 {riskCount > 0 && <span className="rounded-full bg-red-600 px-1.5 text-[10px] text-white">{riskCount}</span>}</TabsTrigger>
              <TabsTrigger value="lines" className="flex-1">OCR라인</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="mt-2 flex min-h-0 flex-1 flex-col border-t">
            {store.tab === 'fields' && (ext ? (
              <FieldPanel fields={ext.fields} colorMap={ext.color_map} onGoTo={goToField}
                onPatch={(code, patch) => patchField.mutateAsync({ field_code: code, patch }).then(() => toast.success('저장했습니다')).catch((e) => { toast.error(errorMessage(e)); throw e; })} />
            ) : <div className="p-4 text-sm text-muted-foreground">추출 결과가 아직 없습니다.</div>)}
            {store.tab === 'risks' && (
              <RiskPanel data={risks} onGoTo={goToRisk} onStatus={(rid, st) => patchRisk.mutate({ rid, status: st }, { onError: (e) => toast.error(errorMessage(e)) })} />
            )}
            {store.tab === 'lines' && (
              <OcrLinePanel
                docId={id}
                pageCount={doc.page_count ?? 1}
                showBoxes={showLineBoxes}
                onToggleBoxes={setShowLineBoxes}
                onPageLoaded={(p, lines) => { if (linesCache.current[p] !== lines) { linesCache.current[p] = lines; setLinesVersion((v) => v + 1); } }}
                onGoTo={(l, p) => store.scrollTo({ page_no: p, bbox: l.bbox, highlightId: `line-${l.id}` })}
                onAssign={(l, p) => {
                  const code = store.selectedFieldCode;
                  if (!code) return;
                  createHl.mutate({ field_code: code, page_no: p, bbox: l.bbox }, { onSuccess: () => toast.success(`${FIELD_LABELS[code]} 근거로 ${l.line_id}를 지정했습니다`), onError: (e) => toast.error(errorMessage(e)) });
                }}
              />
            )}
          </div>
          {ext && <Legend colorMap={ext.color_map} />}
        </aside>
      </div>
    </div>
  );
}
