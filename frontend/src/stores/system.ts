import { create } from 'zustand';

type AiKind = 'LLM' | 'OCR';
interface SystemState {
  aiDown: AiKind | null;
  setAiDown: (k: AiKind | null) => void;
}
/** 503 LLM_UNAVAILABLE / OCR_UNAVAILABLE 수신 시 상단 배너 표시용 전역 상태 */
export const useSystemStore = create<SystemState>((set) => ({
  aiDown: null,
  setAiDown: (aiDown) => set({ aiDown }),
}));
