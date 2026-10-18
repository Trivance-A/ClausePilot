import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ExternalLink, Link2 } from 'lucide-react';
import { cn, formatAmount, formatBizNo, parseAmount } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tip } from '@/components/ui/tooltip';
import { FIELD_CODES, FIELD_LABELS, type FieldCode, type GuaranteeApplication, type GuaranteeFormValues } from '@/types/api';

interface Props {
  app: GuaranteeApplication;
  values: GuaranteeFormValues;
  onChange: (v: GuaranteeFormValues) => void;
  showErrors: boolean;
}

/** SC-06 자동입력 폼: 자동 입력 필드 = 연한 파랑 + confidence 배지, 사용자가 수정하면 배경 해제. 🔗 클릭 → Viewer ?field= 새 탭 */
export function AutofillForm({ app, values, onChange, showErrors }: Props) {
  const required = app.required_fields?.length ? app.required_fields : FIELD_CODES;
  const [touched, setTouched] = useState<Set<FieldCode>>(new Set());
  useEffect(() => setTouched(new Set()), [app.id]);

  const set = (code: FieldCode, v: GuaranteeFormValues[FieldCode]) => {
    setTouched((t) => new Set(t).add(code));
    onChange({ ...values, [code]: v } as GuaranteeFormValues);
  };
  const viewerBase = useMemo(() => app.viewer_url?.split('?')[0] ?? `/documents/${app.document_id}/viewer`, [app]);

  return (
    <div className="divide-y rounded-lg border bg-white">
      {required.map((code) => {
        const src = app.field_sources?.[code];
        const value = values[code];
        const empty = value === null || value === undefined || value === '' || (code === 'guarantee_period' && !(value as { start?: string | null })?.start);
        const auto = !!src && !touched.has(code) && !empty;
        const missing = !src && empty;
        const invalid = showErrors && empty;
        const inputCls = cn('h-9', auto && 'bg-blue-50 border-blue-200', invalid && 'border-red-400 focus-visible:ring-red-400');
        return (
          <div key={code} className="grid grid-cols-[150px_1fr_auto] items-center gap-3 px-4 py-2.5">
            <label className="text-sm font-medium">{FIELD_LABELS[code]}<span className="text-red-500">*</span></label>
            <div>
              {code === 'contract_amount' || code === 'guarantee_amount' ? (
                <Input className={inputCls} inputMode="numeric" value={formatAmount(value as number | null)} placeholder="숫자 입력" onChange={(e) => set(code, parseAmount(e.target.value))} />
              ) : code === 'contract_date' || code === 'performance_due_date' ? (
                <Input type="date" className={inputCls} value={(value as string | null) ?? ''} onChange={(e) => set(code, e.target.value || null)} />
              ) : code === 'guarantee_period' ? (
                <div className="flex items-center gap-2">
                  <Input type="date" className={inputCls} value={(value as { start: string | null } | null)?.start ?? ''} onChange={(e) => set(code, { start: e.target.value || null, end: (value as { end: string | null } | null)?.end ?? null })} />
                  <span>~</span>
                  <Input type="date" className={inputCls} value={(value as { end: string | null } | null)?.end ?? ''} onChange={(e) => set(code, { start: (value as { start: string | null } | null)?.start ?? null, end: e.target.value || null })} />
                </div>
              ) : code === 'creditor_biz_no' ? (
                <Input className={inputCls} placeholder="___-__-_____" value={(value as string | null) ?? ''} onChange={(e) => set(code, formatBizNo(e.target.value) || null)} />
              ) : (
                <Input className={inputCls} value={(value as string | null) ?? ''} onChange={(e) => set(code, e.target.value || null)} />
              )}
              {invalid && <div className="mt-0.5 text-[11px] text-red-600">필수 항목입니다</div>}
            </div>
            <div className="flex w-32 items-center justify-end gap-1">
              {src ? (
                <Tip text={<span>계약서 p{src.page_no ?? '?'} 근거 위치 보기 (Viewer 새 탭)</span>}>
                  <a href={`${viewerBase}?field=${code}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700 hover:bg-blue-100">
                    <Link2 className="h-3 w-3" /> {src.confidence.toFixed(2)} <ExternalLink className="h-3 w-3" />
                  </a>
                </Tip>
              ) : missing ? (
                <Badge variant="warning"><AlertTriangle className="h-3 w-3" /> 미검출·직접입력</Badge>
              ) : (
                <Badge variant="muted">직접입력</Badge>
              )}
              {src && src.confidence < 0.7 && <Tip text="confidence 0.7 미만: 값 확인 권고"><AlertTriangle className="h-4 w-4 text-amber-500" /></Tip>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
