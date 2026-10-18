import type { BBox } from '@/types/api';

/** 0~1 정규화 bbox → 렌더 캔버스 px 사각형 (pdf.js viewport는 좌상단 원점이므로 y 반전 불필요) */
export function normToPx(bbox: BBox, width: number, height: number) {
  const [x0, y0, x1, y1] = bbox;
  return { left: x0 * width, top: y0 * height, width: (x1 - x0) * width, height: (y1 - y0) * height };
}

export function pxToNorm(rect: { left: number; top: number; width: number; height: number }, width: number, height: number): BBox {
  const x0 = clamp01(rect.left / width);
  const y0 = clamp01(rect.top / height);
  const x1 = clamp01((rect.left + rect.width) / width);
  const y1 = clamp01((rect.top + rect.height) / height);
  return [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)];
}

export function clamp01(v: number) { return Math.max(0, Math.min(1, v)); }

export function round4(b: BBox): BBox { return b.map((v) => Math.round(v * 10000) / 10000) as BBox; }
