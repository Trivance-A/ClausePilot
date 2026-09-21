import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { AlertTriangle, Check, Crosshair, Pencil, X } from 'lucide-react';
import { cn, formatAmount, formatBizNo, parseAmount } from '@/lib/utils';
import { useViewerStore } from '@/stores/viewer';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tip } from '@/components/ui/tooltip';
import type { ExtractionField, FieldCode, FieldPatch, NormalizedValue } from '@/types/api';

interface Props {
  fields: ExtractionField[];
  colorMap: Record<string, string>;
  onPatch: (code: FieldCode, patch: FieldPatch) => Promise<unknown>;
  onGoTo: (field: ExtractionField) => void;
}

export function fieldColor(colorMap: Record<string, string>, f: ExtractionField) {
  return colorMap[f.color_key ?? ''] ?? colorMap[f.field_code] ?? '#94a3b8';
}

export function displayValue(f: ExtractionField): string {
  const nv = f.normalized_value as Record<string, unknown> | null;
  if (nv) {
    if (typeof nv.amount === 'number') return `₩${formatAmount(nv.amount)}`;
    if (typeof nv.date === 'string') return nv.date;
    if (typeof nv.start === 'string' || typeof nv.end === 'string') return `${nv.start ?? '?'} ~ ${nv.end ?? '?'}${nv.derived ? ' (추정)' : ''}`;
    if (typeof nv.text === 'string') return nv.text;
  }
  return f.raw_value ?? '';
}

function toNormalized(code: FieldCode, raw: string, extra?: { start?: string; end?: string }): NormalizedValue {
  if (code === 'contract_amount' || code === 'guarantee_amount') { const a = parseAmount(raw); return a === null ? null : { amount: a }; }
  if (code === 'contract_date' || code === 'performance_due_date') return raw ? { date: raw } : null;
  if (code === 'guarantee_period') return { start: extra?.start ?? '', end: extra?.end ?? '' };
  if (code === 'creditor_biz_no') return raw ? { text: formatBizNo(raw) } : null;
  return raw ? { text: raw.trim() } : null;
}

export function ConfidenceBadge({ value, confirmed, mapping }: { value: number; confirmed?: boolean; mapping?: string }) {
  if (confirmed) return <Badge variant="success"><Check className="h-3 w-3" /> 확정</Badge>;
  if (mapping === 'none' || value <= 0) return null;
  const low = value < 0.7;
  return (
    <Tip text={low ? 'confidence 0.7 미만: 확정 전 값 확인을 권고합니다' : `confidence ${value.toFixed(2)}`}>
      <span><Badge variant={low ? 'warning' : 'muted'} className="tabular-nums">{low && <AlertTriangle className="h-3 w-3" />}{value.toFixed(2)}</Badge></span>
    </Tip>
  );
}

/** SC-04 우측 [추출항목] 탭: 8개 항목 목록, 인라인 수정, 위치 재지정, 키보드 ↑↓/Enter/Esc */
export function FieldPanel({ fields, colorMap, onPatch, onGoTo }: Props) {
  const selected = useViewerStore((s) => s.selectedFieldCode);
  const selectField = useViewerStore((s) => s.selectField);
  const enterSelectMode = useViewerStore((s) => s.enterSelectMode);
  const exitSelectMode = useViewerStore((s) => s.exitSelectMode);
  const selectTarget = useViewerStore((s) => s.selectTarget);
  const listRef = useRef<HTMLDivElement>(null);
  const [editing, setEditing] = useState<FieldCode | null>(null);

  useEffect(() => {
    if (!selected) return;
    listRef.current?.querySelector<HTMLElement>(`[data-field="${selected}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [selected]);

  const onKeyDown = (e: KeyboardEvent) => {
    if (editing) return;
    const idx = fields.findIndex((f) => f.field_code === selected);
    if (e.key === 'ArrowDown') { e.preventDefault(); selectField(fields[Math.min(fields.length - 1, idx + 1)]?.field_code ?? null); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); selectField(fields[Math.max(0, idx - 1)]?.field_code ?? null); }
    else if (e.key === 'Enter' && idx >= 0) { e.preventDefault(); onGoTo(fields[idx]); }
    else if (e.key === 'Escape') { exitSelectMode(); selectField(null); }
  };

  return (
    <div ref={listRef} tabIndex={0} onKeyDown={onKeyDown} className="scrollbar-thin flex-1 overflow-auto outline-none focus-visible:ring-1 focus-visible:ring-ring">
      {fields.map((f) => {
        const color = fieldColor(colorMap, f);
        const missing = f.raw_value === null || f.raw_value === undefined || f.mapping_method === 'none' && !f.raw_value;
        const noBox = !f.highlights.length;
        const active = selected === f.field_code;
        const firstPage = f.highlights[0]?.page_no;
        const inSelect = selectTarget?.kind === 'field' && selectTarget.fieldCode === f.field_code;
        return (
          <div
            key={f.field_code}
            data-field={f.field_code}
            className={cn('cursor-pointer border-b px-3 py-2.5 transition-colors', active ? 'bg-blue-50' : 'hover:bg-slate-50')}
            onClick={() => { selectField(f.field_code); if (!noBox) onGoTo(f); }}
          >
            <div className="flex items-center gap-2">
              <span className="inline-block h-3.5 w-3.5 shrink-0 rounded-sm border" style={{ backgroundColor: color, borderColor: color }} />
              <span className="text-sm font-semibold">{f.label}</span>
              <span className="ml-auto flex items-center gap-1">
                {missing ? <Badge variant="warning"><AlertTriangle className="h-3 w-3" /> 미검출</Badge> : <ConfidenceBadge value={f.confidence} confirmed={f.is_confirmed} mapping={f.mapping_method} />}
                {f.highlights.some((h) => h.origin === 'manual') && <Badge variant="outline" className="border-dashed">수동</Badge>}
              </span>
            </div>

            {editing === f.field_code ? (
              <FieldEditor field={f} onCancel={() => setEditing(null)} onSave={async (patch) => { await onPatch(f.field_code, patch); setEditing(null); }} />
            ) : (
              <div className="mt-1 pl-5">
                <div className="flex items-baseline gap-2">
                  <span className={cn('text-sm', missing ? 'text-slate-400' : 'font-medium')}>{missing ? '—' : displayValue(f)}</span>
                  {firstPage && <span className="ml-auto text-xs text-muted-foreground">p{firstPage}</span>}
                  {!missing && noBox && <span className="ml-auto text-xs text-amber-600">위치 미매핑</span>}
                </div>
                {!missing && f.raw_value && displayValue(f) !== f.raw_value && (
                  <div className="mt-0.5 truncate text-xs text-muted-foreground" title={f.raw_value}>원문: {f.raw_value}</div>
                )}
                {f.reviewer_note && <div className="mt-0.5 text-xs text-slate-500">메모: {f.reviewer_note}</div>}
                <div className="mt-1.5 flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  <Button size="xs" variant="outline" onClick={() => { selectField(f.field_code); setEditing(f.field_code); }}><Pencil /> 수정</Button>
                  {inSelect ? (
                    <Button size="xs" variant="secondary" onClick={exitSelectMode}><X /> 지정 취소</Button>
                  ) : (
                    <Button size="xs" variant={noBox ? 'default' : 'outline'} onClick={() => { selectField(f.field_code); enterSelectMode({ kind: 'field', fieldCode: f.field_code, replaceHighlightId: f.highlights[0]?.id }); }}>
                      <Crosshair /> {noBox ? '직접 지정 →' : '위치 재지정'}
                    </Button>
                  )}
                  {!f.is_confirmed && !missing && (
                    <Button size="xs" variant="ghost" className="text-emerald-700" onClick={() => onPatch(f.field_code, { is_confirmed: true })}><Check /> 확정</Button>
                  )}
                </div>
                {inSelect && <div className="mt-1 text-xs text-blue-700">뷰어에서 드래그하여 영역을 지정하세요 (Esc 취소)</div>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function FieldEditor({ field, onSave, onCancel }: { field: ExtractionField; onSave: (p: FieldPatch) => Promise<void>; onCancel: () => void }) {
  const code = field.field_code;
  const nv = (field.normalized_value ?? {}) as Record<string, unknown>;
  const initRaw = code === 'contract_amount' || code === 'guarantee_amount' ? (typeof nv.amount === 'number' ? formatAmount(nv.amount) : field.raw_value ?? '')
    : code === 'contract_date' || code === 'performance_due_date' ? (typeof nv.date === 'string' ? nv.date : '')
    : field.raw_value ?? (typeof nv.text === 'string' ? nv.text : '');
  const [raw, setRaw] = useState(initRaw);
  const [start, setStart] = useState(typeof nv.start === 'string' ? nv.start : '');
  const [end, setEnd] = useState(typeof nv.end === 'string' ? nv.end : '');
  const [note, setNote] = useState(field.reviewer_note ?? '');
  const [confirm, setConfirm] = useState(field.is_confirmed);
  const [saving, setSaving] = useState(false);
  const isDate = code === 'contract_date' || code === 'performance_due_date';
  const isPeriod = code === 'guarantee_period';

  const save = async () => {
    setSaving(true);
    try {
      const normalized = toNormalized(code, raw, { start, end });
      const rawValue = isPeriod ? `${start} ~ ${end}` : code === 'creditor_biz_no' ? formatBizNo(raw) : raw;
      await onSave({ raw_value: rawValue || null, normalized_value: normalized, is_confirmed: confirm, reviewer_note: note || undefined });
    } finally { setSaving(false); }
  };

  return (
    <div className="mt-1.5 space-y-1.5 pl-5" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => { if (e.key === 'Escape') onCancel(); if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); save(); } }}>
      {isPeriod ? (
        <div className="flex items-center gap-1">
          <Input type="date" className="h-8 text-xs" value={start} onChange={(e) => setStart(e.target.value)} autoFocus /> ~
          <Input type="date" className="h-8 text-xs" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      ) : (
        <Input
          type={isDate ? 'date' : 'text'}
          className="h-8 text-sm"
          value={raw}
          autoFocus
          inputMode={code.includes('amount') ? 'numeric' : undefined}
          placeholder={code === 'creditor_biz_no' ? '123-45-67890' : undefined}
          onChange={(e) => setRaw(code.includes('amount') ? formatAmount(parseAmount(e.target.value) ?? 0) : code === 'creditor_biz_no' ? formatBizNo(e.target.value) : e.target.value)}
        />
      )}
      <Input className="h-7 text-xs" placeholder="검토 메모 (선택) 예: OCR 오인식 수정" value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /> 확정</label>
        <span className="ml-auto flex gap-1">
          <Button size="xs" variant="ghost" onClick={onCancel}>취소</Button>
          <Button size="xs" onClick={save} loading={saving}>저장</Button>
        </span>
      </div>
    </div>
  );
}
