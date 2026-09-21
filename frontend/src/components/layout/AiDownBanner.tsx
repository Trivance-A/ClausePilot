import { AlertTriangle, RefreshCw, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useSystemStore } from '@/stores/system';
import { Button } from '@/components/ui/button';

/** LLM/OCR 서버 다운(503) 시 상단 배너 + 재시도 */
export function AiDownBanner() {
  const aiDown = useSystemStore((s) => s.aiDown);
  const setAiDown = useSystemStore((s) => s.setAiDown);
  const qc = useQueryClient();
  if (!aiDown) return null;
  return (
    <div className="flex items-center gap-3 border-b border-red-200 bg-red-50 px-5 py-2 text-sm text-red-800">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span className="font-medium">AI 서버({aiDown}) 연결 불가</span>
      <span className="text-red-700/80">잠시 후 다시 시도해 주세요.</span>
      <Button size="xs" variant="outline" className="ml-auto border-red-300 bg-white" onClick={() => { setAiDown(null); qc.invalidateQueries(); }}>
        <RefreshCw /> 재시도
      </Button>
      <button className="rounded p-1 hover:bg-red-100" onClick={() => setAiDown(null)} aria-label="닫기"><X className="h-4 w-4" /></button>
    </div>
  );
}
