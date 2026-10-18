import { FIELD_LABELS, type FieldCode } from '@/types/api';
import { hexAlpha, SEVERITY_COLOR } from './types';

/** 범례: 항목명 병기(색상만으로 구분하지 않음) + 위험 빗금 + 수동 점선 */
export function Legend({ colorMap }: { colorMap: Record<string, string> }) {
  const entries = Object.entries(colorMap);
  return (
    <div className="border-t bg-slate-50 px-3 py-2 text-[11px]">
      <div className="mb-1 font-semibold text-muted-foreground">범례</div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {entries.map(([k, c]) => (
          <span key={k} className="inline-flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-sm border" style={{ backgroundColor: hexAlpha(c, 0.4), borderColor: c }} />
            {FIELD_LABELS[k as FieldCode] ?? k}
          </span>
        ))}
        <span className="inline-flex items-center gap-1"><span className="hatch-high inline-block h-3 w-3 rounded-sm border" style={{ borderColor: SEVERITY_COLOR.HIGH }} />위험조항(빗금 H/M/L)</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-sm border-2 border-dashed border-slate-500" />수동 지정(점선)</span>
      </div>
    </div>
  );
}
