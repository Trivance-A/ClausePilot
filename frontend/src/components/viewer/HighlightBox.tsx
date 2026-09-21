import { useRef, useState, type PointerEvent as RPointerEvent } from 'react';
import { cn } from '@/lib/utils';
import { normToPx, pxToNorm, round4 } from '@/lib/bbox';
import type { BBox } from '@/types/api';
import { hexAlpha, SEVERITY_LABEL, type OverlayItem } from './types';

type Rect = { left: number; top: number; width: number; height: number };
type Handle = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';
const HANDLES: { h: Handle; cls: string; cursor: string }[] = [
  { h: 'nw', cls: '-left-1 -top-1', cursor: 'nwse-resize' }, { h: 'n', cls: 'left-1/2 -top-1 -translate-x-1/2', cursor: 'ns-resize' },
  { h: 'ne', cls: '-right-1 -top-1', cursor: 'nesw-resize' }, { h: 'e', cls: '-right-1 top-1/2 -translate-y-1/2', cursor: 'ew-resize' },
  { h: 'se', cls: '-right-1 -bottom-1', cursor: 'nwse-resize' }, { h: 's', cls: 'left-1/2 -bottom-1 -translate-x-1/2', cursor: 'ns-resize' },
  { h: 'sw', cls: '-left-1 -bottom-1', cursor: 'nesw-resize' }, { h: 'w', cls: '-left-1 top-1/2 -translate-y-1/2', cursor: 'ew-resize' },
];

interface Props {
  item: OverlayItem;
  width: number;
  height: number;
  editable: boolean;
  pulse: boolean;
  onClick: (item: OverlayItem) => void;
  onChange: (item: OverlayItem, bbox: BBox) => void;
  onDelete: (item: OverlayItem) => void;
}

/**
 * 오버레이 사각형. 항목 = 채움 30% + 테두리 2px(항목색), 위험 = 빗금 + 좌측 H/M/L 배지, 수동 = 점선.
 * editable(관리자)일 때 8방향 핸들로 리사이즈·드래그 이동, 우클릭 삭제.
 */
export function HighlightBox({ item, width, height, editable, pulse, onClick, onChange, onDelete }: Props) {
  const base = normToPx(item.bbox, width, height);
  const [draft, setDraft] = useState<Rect | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ mode: 'move' | Handle; sx: number; sy: number; start: Rect; moved: boolean } | null>(null);
  const rect = draft ?? base;
  const canEdit = editable && (item.kind === 'field' || item.kind === 'risk');

  const begin = (e: RPointerEvent, mode: 'move' | Handle) => {
    if (!canEdit || e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    boxRef.current?.setPointerCapture(e.pointerId);
    drag.current = { mode, sx: e.clientX, sy: e.clientY, start: base, moved: false };
  };
  const move = (e: RPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.sx, dy = e.clientY - d.sy;
    if (!d.moved && Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
    d.moved = true;
    const r: Rect = { ...d.start };
    if (d.mode === 'move') { r.left += dx; r.top += dy; }
    else {
      if (d.mode.includes('e')) r.width += dx;
      if (d.mode.includes('s')) r.height += dy;
      if (d.mode.includes('w')) { r.left += dx; r.width -= dx; }
      if (d.mode.includes('n')) { r.top += dy; r.height -= dy; }
    }
    if (r.width < 4) { r.width = 4; }
    if (r.height < 4) { r.height = 4; }
    r.left = Math.max(0, Math.min(width - r.width, r.left));
    r.top = Math.max(0, Math.min(height - r.height, r.top));
    setDraft(r);
  };
  const end = (e: RPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    boxRef.current?.releasePointerCapture(e.pointerId);
    if (d.moved && draft) onChange(item, round4(pxToNorm(draft, width, height)));
    else onClick(item);
    setDraft(null);
  };

  const style: React.CSSProperties = {
    left: rect.left, top: rect.top, width: rect.width, height: rect.height,
    opacity: item.dimmed ? 0.25 : 1,
    zIndex: item.emphasized ? 20 : item.kind === 'risk' ? 12 : item.kind === 'search' ? 15 : 10,
  };
  if (item.kind === 'field') {
    style.backgroundColor = hexAlpha(item.color, 0.3);
    style.border = `${item.emphasized ? 3 : 2}px ${item.origin === 'manual' ? 'dashed' : 'solid'} ${item.color}`;
  } else if (item.kind === 'risk') {
    style.border = `2px ${item.origin === 'manual' ? 'dashed' : 'solid'} ${item.color}`;
  } else if (item.kind === 'search') {
    style.backgroundColor = 'rgba(250,204,21,0.45)';
    style.border = '2px dashed #ca8a04';
  } else {
    style.border = '1px dotted rgba(100,116,139,0.8)';
  }

  return (
    <div
      ref={boxRef}
      data-hid={item.id}
      role="button"
      tabIndex={-1}
      title={`${item.label}${item.origin === 'manual' ? ' (수동)' : ''}`}
      className={cn('absolute select-none rounded-[2px] transition-opacity',
        item.kind === 'risk' && item.severity && `hatch-${item.severity.toLowerCase()}`,
        canEdit ? 'cursor-move' : 'cursor-pointer',
        pulse && 'animate-pulse-ring')}
      style={style}
      onPointerDown={(e) => begin(e, 'move')}
      onPointerMove={move}
      onPointerUp={end}
      onClick={(e) => { e.stopPropagation(); if (!canEdit) onClick(item); }}
      onContextMenu={(e) => { if (canEdit) { e.preventDefault(); e.stopPropagation(); onDelete(item); } }}
    >
      {item.kind === 'risk' && item.severity && (
        <span className="absolute -left-[2px] -top-[2px] -translate-x-full rounded-l px-1 text-[10px] font-bold leading-4 text-white" style={{ backgroundColor: item.color }}>
          {SEVERITY_LABEL[item.severity]}
        </span>
      )}
      {item.kind === 'line' && (
        <span className="absolute -top-3 left-0 text-[9px] leading-3 text-slate-500">{item.label}</span>
      )}
      {canEdit && HANDLES.map((h) => (
        <span
          key={h.h}
          className={cn('absolute h-2 w-2 rounded-sm border border-white bg-slate-700', h.cls)}
          style={{ cursor: h.cursor }}
          onPointerDown={(e) => begin(e, h.h)}
        />
      ))}
    </div>
  );
}
