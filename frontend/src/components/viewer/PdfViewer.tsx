import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Loader2, Search, X, ZoomIn, ZoomOut } from 'lucide-react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { loadPdf } from '@/lib/pdf';
import { errorMessage } from '@/lib/api';
import { cn } from '@/lib/utils';
import { useViewerStore } from '@/stores/viewer';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { BBox, PageMeta } from '@/types/api';
import { PageView } from './PageView';
import type { OverlayItem } from './types';

interface Props {
  pdfPath: string;
  pages: PageMeta[];
  pageCount: number;
  items: OverlayItem[];
  editable: boolean;
  onOverlayClick: (item: OverlayItem) => void;
  onOverlayChange: (item: OverlayItem, bbox: BBox) => void;
  onOverlayDelete: (item: OverlayItem) => void;
  onSelectionDone: (pageNo: number, bbox: BBox) => void;
  onSearch: (q: string) => void;
  searchCount: number;
  searchIndex: number;
  onSearchNav: (dir: 1 | -1) => void;
  selectionLabel?: string | null;
}

export function PdfViewer({ pdfPath, pages, pageCount, items, editable, onOverlayClick, onOverlayChange, onOverlayDelete, onSelectionDone, onSearch, searchCount, searchIndex, onSearchNav, selectionLabel }: Props) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [containerW, setContainerW] = useState(0);
  const [baseWidthPt, setBaseWidthPt] = useState<number>(pages[0]?.width_pt ?? 595.3);
  const [q, setQ] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const sizes = useRef<Record<number, { w: number; h: number }>>({});

  const zoom = useViewerStore((s) => s.zoom);
  const setZoom = useViewerStore((s) => s.setZoom);
  const currentPage = useViewerStore((s) => s.currentPage);
  const setCurrentPage = useViewerStore((s) => s.setCurrentPage);
  const selectTarget = useViewerStore((s) => s.selectTarget);
  const exitSelectMode = useViewerStore((s) => s.exitSelectMode);
  const scrollTarget = useViewerStore((s) => s.scrollTarget);
  const pulseId = useViewerStore((s) => s.pulseHighlightId);
  const pulse = useViewerStore((s) => s.pulse);

  // PDF 로드
  useEffect(() => {
    let alive = true;
    setPdf(null); setError(null);
    loadPdf(pdfPath).then(async (doc) => {
      if (!alive) return;
      if (!pages.length) { const p1 = await doc.getPage(1); setBaseWidthPt(p1.getViewport({ scale: 1 }).width); }
      setPdf(doc);
    }).catch((e) => alive && setError(errorMessage(e)));
    return () => { alive = false; };
  }, [pdfPath, pages.length]);

  // 컨테이너 폭 추적 → fit-width 스케일
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => setContainerW(entries[0].contentRect.width));
    ro.observe(el);
    setContainerW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const widthPt = useMemo(() => (pages.length ? Math.max(...pages.map((p) => p.width_pt)) : baseWidthPt), [pages, baseWidthPt]);
  const scale = useMemo(() => (containerW > 0 ? ((containerW - 48) / widthPt) * zoom : zoom), [containerW, widthPt, zoom]);
  const total = pageCount || pages.length || pdf?.numPages || 0;

  // V-2 스크롤 이동 + 1.5초 펄스
  useEffect(() => {
    if (!scrollTarget || !pdf) return;
    const el = pageRefs.current[scrollTarget.page_no];
    const c = containerRef.current;
    if (!el || !c) return;
    const size = sizes.current[scrollTarget.page_no] ?? { w: el.clientWidth, h: el.clientHeight };
    const [, y0, , y1] = scrollTarget.bbox;
    const centerY = el.offsetTop + ((y0 + y1) / 2) * size.h;
    c.scrollTo({ top: Math.max(0, centerY - c.clientHeight / 2), behavior: 'smooth' });
    if (scrollTarget.highlightId) {
      pulse(scrollTarget.highlightId);
      const t = setTimeout(() => pulse(null), 1500);
      return () => clearTimeout(t);
    }
  }, [scrollTarget, pdf, pulse]);

  // 현재 페이지 계산
  const onScroll = useCallback(() => {
    const c = containerRef.current;
    if (!c) return;
    const mid = c.scrollTop + c.clientHeight / 2;
    let best = 1;
    for (const [no, el] of Object.entries(pageRefs.current)) {
      if (el && el.offsetTop <= mid) best = Number(no);
    }
    if (best !== currentPage) setCurrentPage(best);
  }, [currentPage, setCurrentPage]);

  const goPage = (n: number) => {
    const el = pageRefs.current[n];
    const c = containerRef.current;
    if (el && c) c.scrollTo({ top: el.offsetTop - 8, behavior: 'smooth' });
  };

  const byPage = useMemo(() => {
    const m: Record<number, OverlayItem[]> = {};
    for (const it of items) (m[it.page_no] ??= []).push(it);
    return m;
  }, [items]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 툴바 */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b bg-white px-3 py-1.5 text-sm">
        <Button variant="ghost" size="icon-sm" onClick={() => setZoom(zoom - 0.1)} aria-label="축소"><ZoomOut /></Button>
        <button className="w-12 text-center tabular-nums hover:underline" onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button>
        <Button variant="ghost" size="icon-sm" onClick={() => setZoom(zoom + 0.1)} aria-label="확대"><ZoomIn /></Button>
        <span className="mx-1 h-5 w-px bg-border" />
        <Button variant="ghost" size="icon-sm" disabled={currentPage <= 1} onClick={() => goPage(currentPage - 1)}><ChevronLeft /></Button>
        <span className="tabular-nums">{currentPage} / {total}</span>
        <Button variant="ghost" size="icon-sm" disabled={currentPage >= total} onClick={() => goPage(currentPage + 1)}><ChevronRight /></Button>
        <span className="mx-1 h-5 w-px bg-border" />
        <form className="relative flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); onSearch(q); }}>
          <Search className="absolute left-2 h-3.5 w-3.5 text-muted-foreground" />
          <Input className="h-7 w-48 pl-7 text-xs" placeholder="텍스트 검색 (Enter)" value={q} onChange={(e) => setQ(e.target.value)} />
          {searchCount > 0 && (
            <span className="flex items-center gap-0.5 text-xs text-muted-foreground">
              {searchIndex + 1}/{searchCount}
              <Button type="button" variant="ghost" size="icon-sm" onClick={() => onSearchNav(-1)}><ChevronLeft /></Button>
              <Button type="button" variant="ghost" size="icon-sm" onClick={() => onSearchNav(1)}><ChevronRight /></Button>
            </span>
          )}
          {q && <Button type="button" variant="ghost" size="icon-sm" onClick={() => { setQ(''); onSearch(''); }}><X /></Button>}
        </form>
        {selectTarget && (
          <div className="ml-auto flex items-center gap-2 rounded-md bg-blue-50 px-2 py-1 text-xs text-blue-800 ring-1 ring-blue-200">
            <span className="font-semibold">선택 모드</span> {selectionLabel ?? '드래그로 영역을 지정하세요'} · Esc 취소
            <Button size="xs" variant="outline" onClick={exitSelectMode}>취소</Button>
          </div>
        )}
      </div>

      {/* 페이지 연속 스크롤 */}
      <div ref={containerRef} onScroll={onScroll} className={cn('scrollbar-thin relative flex-1 overflow-auto bg-slate-200/70 px-6 py-4', selectTarget && 'ring-2 ring-inset ring-blue-400')}>
        {error && <div className="rounded-md bg-red-50 p-4 text-sm text-red-700">PDF를 불러오지 못했습니다: {error}</div>}
        {!pdf && !error && <div className="flex items-center justify-center gap-2 py-20 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> PDF 로딩 중…</div>}
        {pdf && Array.from({ length: total }, (_, i) => i + 1).map((n) => (
          <PageView
            key={n}
            ref={(el) => { pageRefs.current[n] = el; }}
            pdf={pdf}
            pageNo={n}
            meta={pages.find((p) => p.page_no === n)}
            scale={scale}
            items={byPage[n] ?? []}
            editable={editable}
            selectionMode={!!selectTarget}
            pulseId={pulseId}
            onOverlayClick={onOverlayClick}
            onOverlayChange={onOverlayChange}
            onOverlayDelete={onOverlayDelete}
            onSelectionDone={onSelectionDone}
            onSize={(p, w, h) => { sizes.current[p] = { w, h }; }}
          />
        ))}
      </div>
    </div>
  );
}
