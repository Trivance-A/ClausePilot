import type { BBox, FieldCode, HighlightOrigin, Severity } from '@/types/api';

export type OverlayKind = 'field' | 'risk' | 'search' | 'line';

/** Viewer 오버레이 한 개 (항목 하이라이트 / 위험조항 / 검색 임시 / OCR 라인 디버그) */
export interface OverlayItem {
  id: string;
  kind: OverlayKind;
  page_no: number;
  bbox: BBox;
  color: string;
  label: string;
  fieldCode?: FieldCode;
  riskId?: string;
  severity?: Severity;
  origin?: HighlightOrigin;
  dimmed?: boolean;
  emphasized?: boolean;
}

export const SEVERITY_COLOR: Record<Severity, string> = { HIGH: '#dc2626', MEDIUM: '#f97316', LOW: '#eab308' };
export const SEVERITY_LABEL: Record<Severity, string> = { HIGH: 'H', MEDIUM: 'M', LOW: 'L' };

export function hexAlpha(hex: string, alpha: number) {
  const h = hex.replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(full, 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}
