import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, Play } from 'lucide-react';
import { toast } from 'sonner';
import { useEvalRun, useEvalRuns, useRunEval } from '@/api/admin';
import { errorMessage } from '@/lib/api';
import { cn, formatDate, pct } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PageHeader } from '@/components/layout/PageHeader';
import { FIELD_CODES, FIELD_LABELS, type EvalRun, type EvalSuite } from '@/types/api';

const METRICS: { key: string; label: string; target: number; lowerIsBetter?: boolean; get: (m: NonNullable<EvalRun['metrics']>) => number | undefined }[] = [
  { key: 'acc', label: '항목 정확도', target: 0.9, get: (m) => m.field_accuracy?.overall },
  { key: 'bbox', label: 'bbox 매핑률', target: 0.95, get: (m) => m.bbox_mapping_rate },
  { key: 'recall', label: 'Recall@5', target: 0.9, get: (m) => m.recall_at_5 },
  { key: 'hall', label: '환각률 (낮을수록 좋음)', target: 0.05, lowerIsBetter: true, get: (m) => m.hallucination_rate },
];

function MetricBar({ label, value, target, lowerIsBetter }: { label: string; value: number | undefined; target: number; lowerIsBetter?: boolean }) {
  const ok = value !== undefined && (lowerIsBetter ? value <= target : value >= target);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm"><span className="font-medium">{label}</span>
        <span className={cn('font-semibold tabular-nums', value === undefined ? 'text-muted-foreground' : ok ? 'text-emerald-700' : 'text-red-600')}>{pct(value)} <span className="text-xs font-normal text-muted-foreground">(목표 {pct(target)})</span></span></div>
      <div className="relative h-3 w-full rounded-full bg-slate-200">
        <div className={cn('h-3 rounded-full', ok ? 'bg-violet-600' : 'bg-red-400')} style={{ width: `${(value ?? 0) * 100}%` }} />
        <div className="absolute top-[-3px] h-[18px] w-0.5 bg-red-500" style={{ left: `${target * 100}%` }} title={`목표 ${pct(target)}`} />
      </div>
    </div>
  );
}

export function AdminEvalPage() {
  const [suite, setSuite] = useState<EvalSuite>('all');
  const [runId, setRunId] = useState<string | undefined>();
  const run = useRunEval();
  const { data: runs } = useEvalRuns();
  const { data } = useEvalRun(runId);
  useEffect(() => { if (!runId && runs?.items?.length) setRunId(runs.items[0].id); }, [runs, runId]);

  const start = () => run.mutate(suite, { onSuccess: (r) => { setRunId(r.run_id ?? r.id); toast.success('평가를 시작했습니다'); }, onError: (e) => toast.error(errorMessage(e)) });
  const running = data && ['QUEUED', 'RUNNING'].includes(data.status);
  const m = data?.metrics ?? null;
  const byField = m?.field_accuracy?.by_field ?? {};

  return (
    <div>
      <PageHeader title="평가 결과" description="정답셋 기반 항목 정확도 · bbox 매핑률 · Recall@5 · 환각률 (주간 자동 실행 + 수동 실행)"
        actions={<>
          <Select value={suite} onValueChange={(v) => setSuite(v as EvalSuite)}>
            <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">suite: all</SelectItem><SelectItem value="extraction">extraction</SelectItem><SelectItem value="retrieval">retrieval</SelectItem><SelectItem value="faithfulness">faithfulness</SelectItem></SelectContent>
          </Select>
          <Button onClick={start} loading={run.isPending} disabled={!!running}><Play /> 평가 실행</Button>
        </>} />

      <div className="mb-3 flex items-center gap-3 text-sm text-muted-foreground">
        {running && <span className="flex items-center gap-1 text-amber-700"><Loader2 className="h-4 w-4 animate-spin" /> 실행 중 ({data?.status})…</span>}
        {data && !running && <span>suite: {data.suite} · 마지막 실행 {formatDate(data.finished_at ?? data.started_at, { withTime: true })}</span>}
        {runs && runs.items.length > 1 && (
          <Select value={runId} onValueChange={setRunId}>
            <SelectTrigger className="ml-auto h-8 w-64 text-xs"><SelectValue placeholder="실행 이력" /></SelectTrigger>
            <SelectContent>{runs.items.map((r) => <SelectItem key={r.id} value={r.id}>{formatDate(r.finished_at ?? r.started_at, { withTime: true })} · {r.suite} · {r.status}</SelectItem>)}</SelectContent>
          </Select>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <section className="space-y-4 rounded-lg border bg-white p-5 shadow-sm">
          {METRICS.map((x) => <MetricBar key={x.key} label={x.label} value={m ? x.get(m) : undefined} target={x.target} lowerIsBetter={x.lowerIsBetter} />)}
          {!data && <div className="text-sm text-muted-foreground">아직 평가 실행 결과가 없습니다. [평가 실행]을 눌러주세요.</div>}
        </section>

        <section className="rounded-lg border bg-white p-5 shadow-sm">
          <div className="mb-3 text-sm font-semibold">항목별 정확도</div>
          <svg viewBox="0 0 520 220" className="w-full">
            <line x1="30" y1={200 - 0.9 * 170} x2="510" y2={200 - 0.9 * 170} stroke="#ef4444" strokeDasharray="4 3" />
            <text x="512" y={200 - 0.9 * 170 + 4} fontSize="9" fill="#ef4444" textAnchor="end">90%</text>
            {FIELD_CODES.map((code, i) => {
              const v = byField[code];
              const h = (v ?? 0) * 170;
              const x = 40 + i * 58;
              return (
                <g key={code}>
                  <rect x={x} y={200 - h} width="40" height={h} rx="3" fill={v === undefined ? '#e2e8f0' : v >= 0.9 ? '#7c3aed' : '#a78bfa'} />
                  <text x={x + 20} y={200 - h - 4} fontSize="10" textAnchor="middle" fill="#334155">{v === undefined ? '-' : pct(v)}</text>
                  <text x={x + 20} y="214" fontSize="9" textAnchor="middle" fill="#64748b">{FIELD_LABELS[code].length > 5 ? FIELD_LABELS[code].slice(0, 5) : FIELD_LABELS[code]}</text>
                </g>
              );
            })}
          </svg>
        </section>
      </div>

      <section className="mt-6 rounded-lg border bg-white shadow-sm">
        <div className="border-b px-4 py-2 font-semibold">실패 케이스 {data ? `(${data.failures.length})` : ''}</div>
        <Table>
          <TableHeader><TableRow><TableHead>문서</TableHead><TableHead className="w-40">항목</TableHead><TableHead>정답</TableHead><TableHead>추출값</TableHead><TableHead className="w-24" /></TableRow></TableHeader>
          <TableBody>
            {(data?.failures ?? []).map((f, i) => (
              <TableRow key={i}>
                <TableCell>{f.doc_name ?? f.doc_id}</TableCell>
                <TableCell>{FIELD_LABELS[f.field_code] ?? f.field_code}</TableCell>
                <TableCell className="font-mono text-xs">{f.expected}</TableCell>
                <TableCell className="font-mono text-xs text-red-700">{f.got ?? '(null)'}</TableCell>
                <TableCell><Link className="text-xs text-blue-700 hover:underline" to={`/documents/${f.doc_id}/viewer?field=${f.field_code}`}>Viewer →</Link></TableCell>
              </TableRow>
            ))}
            {data && data.failures.length === 0 && <TableRow><TableCell colSpan={5} className="text-muted-foreground">실패 케이스가 없습니다</TableCell></TableRow>}
          </TableBody>
        </Table>
      </section>
    </div>
  );
}
