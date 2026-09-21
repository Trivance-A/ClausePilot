import { useMemo, useState } from 'react';
import { Check, ChevronDown, ChevronRight, Crosshair, EyeOff, Locate, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useViewerStore } from '@/stores/viewer';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Empty } from '@/components/ui/empty';
import type { RiskFinding, RiskStatus, RisksResponse, Severity } from '@/types/api';
import { SEVERITY_COLOR } from './types';

const SEV_ORDER: Severity[] = ['HIGH', 'MEDIUM', 'LOW'];
const CATEGORY_LABEL: Record<string, string> = { penalty: 'PENALTY', missing: 'MISSING', contradiction: 'CONTRADICTION', toxic: 'TOXIC', policy: 'POLICY' };

interface Props {
  data: RisksResponse | undefined;
  onGoTo: (r: RiskFinding) => void;
  onStatus: (rid: string, status: RiskStatus) => void;
}

/** SC-05 위험조항 패널 */
export function RiskPanel({ data, onGoTo, onStatus }: Props) {
  const [sev, setSev] = useState<'ALL' | Severity>('ALL');
  const [showClosed, setShowClosed] = useState(false);
  const selectedRiskId = useViewerStore((s) => s.selectedRiskId);
  const selectRisk = useViewerStore((s) => s.selectRisk);
  const enterSelectMode = useViewerStore((s) => s.enterSelectMode);

  const items = useMemo(() => {
    const list = (data?.items ?? []).filter((r) => (sev === 'ALL' || r.severity === sev) && (showClosed || r.status === 'OPEN'));
    return [...list].sort((a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity) || b.score - a.score);
  }, [data, sev, showClosed]);
  const summary = data?.summary ?? { HIGH: 0, MEDIUM: 0, LOW: 0 };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-3 border-b px-3 py-2 text-xs">
        <span className="font-semibold">요약</span>
        {SEV_ORDER.map((s) => (
          <span key={s} className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: SEVERITY_COLOR[s] }} />{s} {summary[s] ?? 0}</span>
        ))}
        <span className="ml-auto flex items-center gap-1">
          <Select value={sev} onValueChange={(v) => setSev(v as 'ALL' | Severity)}>
            <SelectTrigger className="h-7 w-28 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">필터: 전체</SelectItem>
              {SEV_ORDER.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
        </span>
      </div>
      <label className="flex items-center gap-1.5 border-b px-3 py-1 text-[11px] text-muted-foreground">
        <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} /> 확인·무시 처리된 항목 포함
      </label>
      <div className="scrollbar-thin flex-1 overflow-auto">
        {items.length === 0 && <Empty title="표시할 위험조항이 없습니다" description={data ? '필터를 조정하거나 재탐지를 실행하세요.' : '위험조항을 불러오는 중…'} />}
        {items.map((r) => {
          const active = selectedRiskId === r.id;
          const page = r.highlights[0]?.page_no;
          const engine = r.rule_code ? '룰' : 'LLM';
          return (
            <div key={r.id} className={cn('border-b border-l-4 px-3 py-2.5 transition-colors', active ? 'bg-blue-50' : 'hover:bg-slate-50')} style={{ borderLeftColor: SEVERITY_COLOR[r.severity] }} onClick={() => selectRisk(r.id)}>
              <div className="flex items-start gap-2">
                <Badge variant={r.severity.toLowerCase() as 'high' | 'medium' | 'low'}>{r.severity}</Badge>
                <span className="text-sm font-semibold leading-5">{r.title}</span>
                <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{page ? `p${page}` : '—'} · {engine} {CATEGORY_LABEL[r.category] ?? r.category.toUpperCase()}</span>
              </div>
              <p className="mt-1 text-xs text-slate-700">{r.description}</p>
              {r.evidence_text && <p className="mt-1 text-xs text-slate-500">근거: “{r.evidence_text}”</p>}
              {r.llm_reasoning && <Reasoning data={r.llm_reasoning} />}
              {r.status !== 'OPEN' && <div className="mt-1 text-[11px] text-slate-500">상태: {r.status === 'ACKNOWLEDGED' ? '확인됨' : '무시됨'}{r.note ? ` · ${r.note}` : ''}</div>}
              <div className="mt-2 flex flex-wrap items-center gap-1" onClick={(e) => e.stopPropagation()}>
                {r.highlights.length ? (
                  <Button size="xs" variant="outline" onClick={() => { selectRisk(r.id); onGoTo(r); }}><Locate /> 근거로 이동</Button>
                ) : (
                  <Button size="xs" variant="outline" onClick={() => { selectRisk(r.id); enterSelectMode({ kind: 'risk', riskId: r.id }); }}><Crosshair /> 근거 위치 지정</Button>
                )}
                {r.status === 'OPEN' ? (
                  <>
                    <Button size="xs" variant="outline" className="text-emerald-700" onClick={() => onStatus(r.id, 'ACKNOWLEDGED')}><Check /> 확인</Button>
                    <Button size="xs" variant="outline" className="text-slate-600" onClick={() => onStatus(r.id, 'DISMISSED')}><EyeOff /> 무시</Button>
                  </>
                ) : (
                  <Button size="xs" variant="ghost" onClick={() => onStatus(r.id, 'OPEN')}><RotateCcw /> 되돌리기</Button>
                )}
                <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">score {r.score.toFixed(2)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Reasoning({ data }: { data: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1">
      <button className="flex items-center gap-0.5 text-[11px] text-blue-700 hover:underline" onClick={(e) => { e.stopPropagation(); setOpen(!open); }}>
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />} LLM 판단 근거 {open ? '접기' : '펼치기'}
      </button>
      {open && (
        <dl className="mt-1 space-y-0.5 rounded bg-slate-50 p-2 text-[11px]">
          {Object.entries(data).map(([k, v]) => (
            <div key={k} className="grid grid-cols-[80px_1fr] gap-1"><dt className="text-slate-500">{k}</dt><dd className="break-words">{typeof v === 'string' ? v : JSON.stringify(v)}</dd></div>
          ))}
        </dl>
      )}
    </div>
  );
}
