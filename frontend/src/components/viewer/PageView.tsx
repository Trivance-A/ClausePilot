import { forwardRef, useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import type { RenderTask } from 'pdfjs-dist';
import type { BBox, PageMeta } from '@/types/api';
import { HighlightBox } from './HighlightBox';
import { SelectionLayer } from './SelectionLayer';
import type { OverlayItem } from './types';

interface Props {
  pdf: PDFDocumentProxy;
  pageNo: number;
  meta: PageMeta | undefined;
  scale: number;
  items: OverlayItem[];
  editable: boolean;
  selectionMode: boolean;
  pulseId: string | null;
  onOverlayClick: (item: OverlayItem) => void;
  onOverlayChange: (item: OverlayItem, bbox: BBox) => void;
  onOverlayDelete: (item: OverlayItem) => void;
  onSelectionDone: (pageNo: number, bbox: BBox) => void;
  onSize: (pageNo: number, w: number, h: number) => void;
}

/** 페이지 1장 = pdf.js 캔버스 + 절대좌표 오버레이 레이어 (bbox 0~1 × 렌더 크기) */
export const PageView = forwardRef<HTMLDivElement, Props>(function PageView(
  { pdf, pageNo, meta, scale, items, editable, selectionMode, pulseId, onOverlayClick, onOverlayChange, onOverlayDelete, onSelectionDone, onSize }, ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ w: (meta?.width_pt ?? 595) * scale, h: (meta?.height_pt ?? 842) * scale });
  const [rendered, setRendered] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let task: RenderTask | null = null;
    setRendered(false);
    pdf.getPage(pageNo).then((page) => {
      if (cancelled) return;
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * dpr);
      canvas.height = Math.floor(viewport.height * dpr);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      setSize({ w: viewport.width, h: viewport.height });
      onSize(pageNo, viewport.width, viewport.height);
      task = page.render({ canvasContext: ctx, viewport, transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined });
      task.promise.then(() => { if (!cancelled) setRendered(true); }).catch(() => { /* cancelled */ });
    }).catch(() => { /* page load error */ });
    return () => { cancelled = true; task?.cancel(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdf, pageNo, scale]);

  return (
    <div ref={ref} data-page={pageNo} className="relative mx-auto mb-4 bg-white shadow-md" style={{ width: size.w, height: size.h }}>
      <canvas ref={canvasRef} className="block" />
      {!rendered && <div className="absolute inset-0 animate-pulse bg-slate-100" />}
      <div className="absolute inset-0">
        {items.map((it) => (
          <HighlightBox key={it.id} item={it} width={size.w} height={size.h} editable={editable && !selectionMode} pulse={pulseId === it.id}
            onClick={onOverlayClick} onChange={onOverlayChange} onDelete={onOverlayDelete} />
        ))}
        {selectionMode && <SelectionLayer width={size.w} height={size.h} onDone={(b) => onSelectionDone(pageNo, b)} />}
      </div>
      <div className="pointer-events-none absolute -bottom-4 right-0 text-[10px] text-slate-400">p.{pageNo}</div>
    </div>
  );
});
