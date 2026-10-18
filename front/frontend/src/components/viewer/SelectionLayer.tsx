import { useRef, useState, type PointerEvent as RPointerEvent } from 'react';
import { pxToNorm, round4 } from '@/lib/bbox';
import type { BBox } from '@/types/api';

type Rect = { left: number; top: number; width: number; height: number };

/** V-6 선택 모드: 드래그로 사각형을 그려 bbox(0~1) 반환 */
export function SelectionLayer({ width, height, onDone }: { width: number; height: number; onDone: (bbox: BBox) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);

  const local = (e: RPointerEvent) => {
    const b = ref.current!.getBoundingClientRect();
    return { x: Math.max(0, Math.min(width, e.clientX - b.left)), y: Math.max(0, Math.min(height, e.clientY - b.top)) };
  };
  return (
    <div
      ref={ref}
      className="absolute inset-0 z-30 cursor-crosshair"
      onPointerDown={(e) => { e.preventDefault(); ref.current?.setPointerCapture(e.pointerId); start.current = local(e); setRect({ ...start.current, left: start.current.x, top: start.current.y, width: 0, height: 0 }); }}
      onPointerMove={(e) => {
        if (!start.current) return;
        const p = local(e);
        setRect({ left: Math.min(p.x, start.current.x), top: Math.min(p.y, start.current.y), width: Math.abs(p.x - start.current.x), height: Math.abs(p.y - start.current.y) });
      }}
      onPointerUp={(e) => {
        ref.current?.releasePointerCapture(e.pointerId);
        const r = rect; start.current = null; setRect(null);
        if (r && r.width > 3 && r.height > 3) onDone(round4(pxToNorm(r, width, height)));
      }}
    >
      {rect && <div className="absolute border-2 border-dashed border-blue-600 bg-blue-500/20" style={rect} />}
    </div>
  );
}
