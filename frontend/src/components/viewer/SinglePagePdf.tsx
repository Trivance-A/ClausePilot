import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist';
import { Loader2 } from 'lucide-react';
import { loadPdf } from '@/lib/pdf';
import { normToPx } from '@/lib/bbox';
import type { BBox } from '@/types/api';

/** 근거 팝업(SC-08)용: PDF 특정 페이지 1장 렌더 + bbox 1개 하이라이트 */
export function SinglePagePdf({ pdfPath, pageNo, bbox, width = 420 }: { pdfPath: string; pageNo: number; bbox: BBox | null; width?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [state, setState] = useState<'loading' | 'ok' | 'error'>('loading');

  useEffect(() => {
    let alive = true;
    let task: RenderTask | null = null;
    setState('loading');
    loadPdf(pdfPath).then(async (doc: PDFDocumentProxy) => {
      if (!alive) return;
      const page = await doc.getPage(Math.min(Math.max(1, pageNo), doc.numPages));
      const base = page.getViewport({ scale: 1 });
      const scale = width / base.width;
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = viewport.width * dpr; canvas.height = viewport.height * dpr;
      canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`;
      const ctx = canvas.getContext('2d')!;
      setSize({ w: viewport.width, h: viewport.height });
      task = page.render({ canvasContext: ctx, viewport, transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined });
      await task.promise;
      if (alive) setState('ok');
    }).catch(() => alive && setState('error'));
    return () => { alive = false; task?.cancel(); };
  }, [pdfPath, pageNo, width]);

  if (state === 'error') return <div className="rounded-md border bg-slate-50 p-4 text-xs text-muted-foreground">규정 PDF를 불러올 수 없습니다 (원문 텍스트만 표시).</div>;
  const box = bbox && size ? normToPx(bbox, size.w, size.h) : null;
  return (
    <div className="relative inline-block border bg-white shadow-sm" style={size ? { width: size.w, height: size.h } : { width, minHeight: 200 }}>
      <canvas ref={canvasRef} className="block" />
      {state === 'loading' && <div className="absolute inset-0 flex items-center justify-center bg-slate-50"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>}
      {box && <div className="absolute rounded-sm border-2 border-emerald-500 bg-emerald-400/30 animate-pulse-ring" style={box} />}
    </div>
  );
}
