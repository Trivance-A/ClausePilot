import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useAdminJobs, useAdminStats, useChatLogs } from '@/api/admin';
import { useReprocessDocument } from '@/api/documents';
import { useReindexRegulation } from '@/api/regulations';
import { downloadFile, errorMessage } from '@/lib/api';
import { formatDate, pct } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tip } from '@/components/ui/tooltip';
import { PageHeader } from '@/components/layout/PageHeader';

function Stat({ title, value, sub }: { title: string; value: string; sub?: string }) {
  return (
    <Card><CardHeader className="pb-1"><CardTitle className="text-xs font-medium text-muted-foreground">{title}</CardTitle></CardHeader>
      <CardContent><div className="text-2xl font-bold tabular-nums">{value}</div>{sub && <div className="text-xs text-muted-foreground">{sub}</div>}</CardContent></Card>
  );
}

export function AdminDashboardPage() {
  const { data: stats } = useAdminStats();
  const [status, setStatus] = useState('ALL');
  const { data: logs } = useChatLogs({ answer_status: status === 'ALL' ? undefined : status, size: 20 });
  const { data: jobs } = useAdminJobs('FAILED');
  const reprocess = useReprocessDocument();
  const reindex = useReindexRegulation();

  const retry = (j: { job_type: string; target_id: string }) => {
    const opts = { onSuccess: () => toast.success('재시도를 시작했습니다'), onError: (e: unknown) => toast.error(errorMessage(e)) };
    if (j.job_type === 'process_document') reprocess.mutate({ id: j.target_id }, opts);
    else if (j.job_type === 'index_regulation') reindex.mutate({ id: j.target_id }, opts);
    else toast.info('이 작업 유형은 화면에서 재시도할 수 없습니다');
  };

  return (
    <div>
      <PageHeader title="작업·로그 대시보드" description="문서 처리 현황, 규정 색인, 최근 7일 질의 통계, 실패 작업 재시도" />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat title="문서 처리" value={stats ? `${stats.documents.done} / ${stats.documents.total}` : '-'} sub={stats ? `실패 ${stats.documents.failed}` : undefined} />
        <Stat title="규정 색인" value={stats ? `${stats.regulations.indexed}종` : '-'} sub={stats ? `${stats.regulations.chunks.toLocaleString()} 청크` : undefined} />
        <Stat title="7일 질의" value={stats ? String(stats.chat.messages_7d) : '-'} sub={stats ? `NOT_FOUND ${pct(stats.chat.not_found_rate)}` : undefined} />
        <Stat title="👍 비율" value={stats ? pct(stats.chat.thumbs_up_rate) : '-'} sub={stats ? `첫 토큰 ${(stats.avg_latency_ms.chat_first_token / 1000).toFixed(1)}s` : undefined} />
        <Stat title="평균 추출 시간" value={stats ? `${(stats.avg_latency_ms.extract / 1000).toFixed(0)}s` : '-'} sub="1문서 업로드→추출" />
      </div>

      <section className="mb-6 rounded-lg border bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b px-4 py-2">
          <div className="font-semibold">최근 질의 로그</div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-8 w-40 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="ALL">전체</SelectItem><SelectItem value="ANSWERED">ANSWERED</SelectItem><SelectItem value="NOT_FOUND">NOT_FOUND</SelectItem><SelectItem value="ERROR">ERROR</SelectItem></SelectContent>
          </Select>
          <Button size="sm" variant="outline" className="ml-auto" onClick={() => downloadFile('/admin/logs/chat', 'chat_logs.csv', { format: 'csv', answer_status: status === 'ALL' ? undefined : status }).catch((e) => toast.error(errorMessage(e)))}><Download /> CSV 다운로드</Button>
        </div>
        <Table>
          <TableHeader><TableRow><TableHead>질문</TableHead><TableHead className="w-28">답변상태</TableHead><TableHead className="w-56">인용 조항</TableHead><TableHead className="w-16">피드백</TableHead><TableHead className="w-20">지연</TableHead><TableHead className="w-32">일시</TableHead></TableRow></TableHeader>
          <TableBody>
            {(logs?.items ?? []).map((l) => (
              <TableRow key={l.id}>
                <TableCell><Tip text={l.answer || '(답변 없음)'}><span className="cursor-help">{l.question}</span></Tip></TableCell>
                <TableCell><Badge variant={l.answer_status === 'ANSWERED' ? 'success' : l.answer_status === 'NOT_FOUND' ? 'warning' : 'danger'}>{l.answer_status}</Badge></TableCell>
                <TableCell className="text-xs text-muted-foreground">{l.citations.length ? l.citations.map((c) => c.path.split('>').pop()).join(', ') : '—'}</TableCell>
                <TableCell className="text-center">{l.feedback === 1 ? '+1' : l.feedback === -1 ? '-1' : '—'}</TableCell>
                <TableCell className="tabular-nums text-xs">{(l.latency_ms / 1000).toFixed(1)}s</TableCell>
                <TableCell className="text-xs text-muted-foreground">{formatDate(l.created_at, { withTime: true })}</TableCell>
              </TableRow>
            ))}
            {logs && logs.items.length === 0 && <TableRow><TableCell colSpan={6} className="text-muted-foreground">로그가 없습니다</TableCell></TableRow>}
          </TableBody>
        </Table>
      </section>

      <section className="rounded-lg border bg-white shadow-sm">
        <div className="border-b px-4 py-2 font-semibold">실패 작업 (jobs)</div>
        <Table>
          <TableHeader><TableRow><TableHead className="w-40">유형</TableHead><TableHead>대상</TableHead><TableHead className="w-24">단계</TableHead><TableHead>오류</TableHead><TableHead className="w-16">시도</TableHead><TableHead className="w-24" /></TableRow></TableHeader>
          <TableBody>
            {(jobs?.items ?? []).map((j) => (
              <TableRow key={j.id}>
                <TableCell className="font-mono text-xs">{j.job_type}</TableCell>
                <TableCell>{j.job_type === 'process_document' ? <Link className="text-blue-700 hover:underline" to={`/documents/${j.target_id}/viewer`}>{j.target_name ?? j.target_id}</Link> : j.target_name ?? j.target_id}</TableCell>
                <TableCell className="text-xs">{j.current_step ?? '-'}</TableCell>
                <TableCell className="max-w-md truncate text-xs text-red-700" title={j.error ?? ''}>{j.error ?? '-'}</TableCell>
                <TableCell className="text-center">{j.attempts}</TableCell>
                <TableCell><Button size="xs" variant="outline" onClick={() => retry(j)}><RefreshCw /> 재시도</Button></TableCell>
              </TableRow>
            ))}
            {jobs && jobs.items.length === 0 && <TableRow><TableCell colSpan={6} className="text-muted-foreground">실패한 작업이 없습니다</TableCell></TableRow>}
          </TableBody>
        </Table>
      </section>
    </div>
  );
}
