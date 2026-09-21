import { cn } from '@/lib/utils';

export function Progress({ value, className, barClassName }: { value: number; className?: string; barClassName?: string }) {
  return (
    <div className={cn('relative h-2 w-full overflow-hidden rounded-full bg-slate-200', className)}>
      <div className={cn('h-full rounded-full bg-primary transition-all', barClassName)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}
