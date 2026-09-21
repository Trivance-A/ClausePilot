import type { RiskSummary } from '@/types/api';
import { cn } from '@/lib/utils';

export function RiskSummaryDots({ summary, size = 'sm' }: { summary: RiskSummary | null | undefined; size?: 'sm' | 'md' }) {
  if (!summary) return <span className="text-muted-foreground">-</span>;
  const items: { k: keyof RiskSummary; cls: string; label: string }[] = [
    { k: 'HIGH', cls: 'bg-red-600', label: 'HIGH' },
    { k: 'MEDIUM', cls: 'bg-orange-500', label: 'MEDIUM' },
    { k: 'LOW', cls: 'bg-yellow-400', label: 'LOW' },
  ];
  const visible = items.filter((i) => (summary[i.k] ?? 0) > 0);
  if (!visible.length) return <span className="text-xs text-emerald-700">없음</span>;
  return (
    <span className={cn('inline-flex items-center gap-2', size === 'md' ? 'text-sm' : 'text-xs')}>
      {visible.map((i) => (
        <span key={i.k} className="inline-flex items-center gap-1" title={i.label}>
          <span className={cn('inline-block rounded-full', i.cls, size === 'md' ? 'h-3 w-3' : 'h-2.5 w-2.5')} />
          {summary[i.k]}
        </span>
      ))}
    </span>
  );
}
