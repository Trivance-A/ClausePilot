import { create } from 'zustand';
import type { BBox, FieldCode } from '@/types/api';

export type ViewerTab = 'fields' | 'risks' | 'lines';
/** 선택 모드 대상: 특정 항목의 하이라이트를 새로 그리거나(재지정) 위험조항 근거를 지정 */
export type SelectTarget = { kind: 'field'; fieldCode: FieldCode; replaceHighlightId?: string } | { kind: 'risk'; riskId: string };
export interface ScrollTarget { page_no: number; bbox: BBox; highlightId?: string; key: number }

interface ViewerState {
  tab: ViewerTab;
  selectedFieldCode: FieldCode | null;
  selectedRiskId: string | null;
  selectTarget: SelectTarget | null;
  pulseHighlightId: string | null;
  scrollTarget: ScrollTarget | null;
  zoom: number;
  currentPage: number;
  setTab: (t: ViewerTab) => void;
  selectField: (code: FieldCode | null) => void;
  selectRisk: (id: string | null) => void;
  enterSelectMode: (t: SelectTarget) => void;
  exitSelectMode: () => void;
  pulse: (hid: string | null) => void;
  scrollTo: (t: Omit<ScrollTarget, 'key'>) => void;
  setZoom: (z: number) => void;
  setCurrentPage: (p: number) => void;
  reset: () => void;
}

const initial = {
  tab: 'fields' as ViewerTab,
  selectedFieldCode: null,
  selectedRiskId: null,
  selectTarget: null,
  pulseHighlightId: null,
  scrollTarget: null,
  zoom: 1,
  currentPage: 1,
};

export const useViewerStore = create<ViewerState>((set) => ({
  ...initial,
  setTab: (tab) => set({ tab }),
  selectField: (selectedFieldCode) => set({ selectedFieldCode, selectedRiskId: null }),
  selectRisk: (selectedRiskId) => set({ selectedRiskId, selectedFieldCode: null }),
  enterSelectMode: (selectTarget) => set({ selectTarget }),
  exitSelectMode: () => set({ selectTarget: null }),
  pulse: (pulseHighlightId) => set({ pulseHighlightId }),
  scrollTo: (t) => set({ scrollTarget: { ...t, key: Date.now() } }),
  setZoom: (zoom) => set({ zoom: Math.min(3, Math.max(0.5, zoom)) }),
  setCurrentPage: (currentPage) => set({ currentPage }),
  reset: () => set({ ...initial }),
}));
