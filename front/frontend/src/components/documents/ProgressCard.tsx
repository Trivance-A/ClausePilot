import { Check, Loader2, XCircle } from 'lucide-react';
import { useDocumentStatus } from '@/api/documents';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/ui/progress';
import type { DocumentStatus } from '@/types/api';

const STEPS: { key: string; label: string; statuses: DocumentStatus[] }[] = [
  { key: 'normalize', label: '정규화', statuses: ['NORMALIZING'] },
  { key: 'ocr', label: 'OCR', statuses: ['OCR'] },
  { key: 'extract', label: '추출', statuses: ['EXTRACTING'] },
  { key: 'risk', label: '위험탐지', statuses: ['RISK'] },
];
const ORDER: DocumentStatus[] = ['UPLOADED', 'NORMALIZING', 'OCR', 'EXTRACTING', 'RISK', 'DONE'];

/** 업로드 후 진행 카드: 정규화 ✓ → OCR ◐ 45% → 추출 ○ → 위험탐지 ○ */
export function ProgressCard({ documentId, name, onDone }: { documentId: string; name: string; onDone?: () => void }) {
  const { data } = useDocumentStatus(documentId);
  const status = data?.status ?? 'UPLOADED';
  const progress = data?.job?.progress ?? 0;
  const idx = ORDER.indexOf(status);
  if (status === 'DONE' && onDone) queueMicrotask(onDone);

  return (
    <div className="rounded-lg border bg-white px-4 py-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-medium">{name}</span>
        {status === 'FAILED' ? (
          <span className="flex items-center gap-1 text-xs text-red-600"><XCircle className="h-3.5 w-3.5" /> 실패: {data?.job?.error ?? '알 수 없는 오류'}</span>
        ) : status === 'DONE' ? (
          <span className="flex items-center gap-1 text-xs text-emerald-700"><Check className="h-3.5 w-3.5" /> 완료</span>
        ) : (
          <span className="text-xs text-muted-foreground">예상 소요 약 1분 · 5초마다 갱신</span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {STEPS.map((s, i) => {
          const stepIdx = ORDER.indexOf(s.statuses[0]);
          const done = idx > stepIdx || status === 'DONE';
          const active = s.statuses.includes(status);
          return (
            <div key={s.key} className="flex items-center gap-2">
              <div className={cn('flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs',
                done ? 'border-emerald-300 bg-emerald-50 text-emerald-700' : active ? 'border-amber-300 bg-amber-50 text-amber-700' : 'border-slate-200 text-slate-400')}>
                {done ? <Check className="h-3 w-3" /> : active ? <Loader2 className="h-3 w-3 animate-spin" /> : <span className="inline-block h-2.5 w-2.5 rounded-full border border-slate-300" />}
                {s.label}{active ? ` ${progress}%` : ''}
              </div>
              {i < STEPS.length - 1 && <span className="text-slate-300">→</span>}
            </div>
          );
        })}
        <div className="ml-auto w-40"><Progress value={status === 'DONE' ? 100 : Math.max(0, (idx - 1) * 25) + progress / 4} /></div>
      </div>
    </div>
  );
}
