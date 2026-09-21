import { useState } from 'react';
import { Link2, Loader2 } from 'lucide-react';
import { useDocumentLines } from '@/api/documents';
import { useViewerStore } from '@/stores/viewer';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { FIELD_LABELS, type OcrLine } from '@/types/api';

interface Props {
  docId: string;
  pageCount: number;
  showBoxes: boolean;
  onToggleBoxes: (v: boolean) => void;
  onGoTo: (line: OcrLine, pageNo: number) => void;
  onAssign: (line: OcrLine, pageNo: number) => void;
  onPageLoaded: (pageNo: number, lines: OcrLine[]) => void;
}

/** V-10 [OCR라인] 탭 (디버그·수동 매핑): 라인 목록·bbox 표시, 라인 클릭 → 선택 항목 근거로 지정 */
export function OcrLinePanel({ docId, pageCount, showBoxes, onToggleBoxes, onGoTo, onAssign, onPageLoaded }: Props) {
  const currentPage = useViewerStore((s) => s.currentPage);
  const selectedField = useViewerStore((s) => s.selectedFieldCode);
  const [page, setPage] = useState<number>(currentPage || 1);
  const { data, isLoading } = useDocumentLines(docId, page);
  if (data) onPageLoaded(data.page_no, data.lines);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b px-3 py-2 text-xs">
        <Select value={String(page)} onValueChange={(v) => setPage(Number(v))}>
          <SelectTrigger className="h-7 w-24 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>{Array.from({ length: Math.max(1, pageCount) }, (_, i) => i + 1).map((n) => <SelectItem key={n} value={String(n)}>p{n}</SelectItem>)}</SelectContent>
        </Select>
        <label className="flex items-center gap-1"><input type="checkbox" checked={showBoxes} onChange={(e) => onToggleBoxes(e.target.checked)} /> bbox 표시</label>
        <span className="ml-auto text-muted-foreground">{data?.lines.length ?? 0}줄</span>
      </div>
      {selectedField ? (
        <div className="border-b bg-blue-50 px-3 py-1 text-[11px] text-blue-800">라인 [지정]을 누르면 <b>{FIELD_LABELS[selectedField]}</b> 항목의 근거로 연결됩니다 (POST /highlights)</div>
      ) : (
        <div className="border-b bg-slate-50 px-3 py-1 text-[11px] text-muted-foreground">[추출항목] 탭에서 항목을 먼저 선택하면 라인을 근거로 지정할 수 있습니다</div>
      )}
      <div className="scrollbar-thin flex-1 overflow-auto font-mono text-[11px]">
        {isLoading && <div className="flex items-center gap-2 p-3 text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> 불러오는 중…</div>}
        {data?.lines.map((l) => (
          <div key={l.id} className={cn('group flex items-start gap-2 border-b px-3 py-1 hover:bg-slate-50', l.confidence < 0.7 && 'bg-amber-50/60')} onClick={() => onGoTo(l, page)}>
            <span className="shrink-0 text-slate-400">{l.line_id}</span>
            <span className="flex-1 break-all">{l.text}</span>
            <span className="shrink-0 tabular-nums text-slate-400">{l.confidence.toFixed(2)}{l.table_cell ? ` ${l.table_cell}` : ''}</span>
            {selectedField && (
              <Button size="xs" variant="outline" className="h-5 shrink-0 px-1 opacity-0 group-hover:opacity-100" onClick={(e) => { e.stopPropagation(); onAssign(l, page); }}><Link2 className="h-3 w-3" /> 지정</Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
