import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, FileText, Info, MoreHorizontal, Plus, RefreshCw, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { isInProgress, useDeleteDocument, useDocumentStatus, useDocuments, useReprocessDocument } from '@/api/documents';
import { errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Tip } from '@/components/ui/tooltip';
import { Empty } from '@/components/ui/empty';
import { Skeleton } from '@/components/ui/skeleton';
import { Checkbox } from '@/components/ui/checkbox';
import { PageHeader } from '@/components/layout/PageHeader';
import { DocStatusBadge } from '@/components/documents/StatusBadge';
import { RiskSummaryDots } from '@/components/documents/RiskSummaryDots';
import { UploadModal } from '@/components/documents/UploadModal';
import { ProgressCard } from '@/components/documents/ProgressCard';
import type { DocumentListItem, UploadItem } from '@/types/api';

const STATUS_OPTIONS = [
  { v: 'ALL', l: '전체' }, { v: 'DONE', l: '완료' }, { v: 'IN_PROGRESS', l: '진행 중' }, { v: 'FAILED', l: '실패' },
];
const SOURCE_LABEL: Record<string, string> = { native: '네이티브', scan: '스캔', mixed: '혼합' };

export function DocumentsPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('ALL');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [recent, setRecent] = useState<UploadItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const params = useMemo(() => ({
    q: q || undefined,
    status: status === 'ALL' ? undefined : status === 'IN_PROGRESS' ? 'UPLOADED,NORMALIZING,OCR,EXTRACTING,RISK' : status,
    from: from || undefined, to: to || undefined, page, size,
  }), [q, status, from, to, page, size]);
  const { data, isLoading, isError, error } = useDocuments(params);
  const reprocess = useReprocessDocument();
  const del = useDeleteDocument();

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const items = data?.items ?? [];

  return (
    <div>
      <PageHeader title="계약서 검증" description="계약서를 업로드하면 정규화 → OCR → 항목 추출 → 위험조항 탐지가 자동 수행됩니다." actions={<Button onClick={() => setUploadOpen(true)}><Plus /> 업로드</Button>} />

      {recent.length > 0 && (
        <div className="mb-4 space-y-2">
          {recent.map((r) => (
            <ProgressCard key={r.document_id} documentId={r.document_id} name={r.original_name} />
          ))}
          <div className="text-right"><Button variant="link" size="sm" onClick={() => setRecent([])}>진행 카드 닫기</Button></div>
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="w-64 pl-8" placeholder="파일명 검색" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        <Select value={status} onValueChange={(v) => { setStatus(v); setPage(1); }}>
          <SelectTrigger className="w-36"><SelectValue placeholder="상태" /></SelectTrigger>
          <SelectContent>{STATUS_OPTIONS.map((o) => <SelectItem key={o.v} value={o.v}>상태: {o.l}</SelectItem>)}</SelectContent>
        </Select>
        <div className="flex items-center gap-1 text-sm text-muted-foreground">
          기간 <Input type="date" className="w-36" value={from} onChange={(e) => setFrom(e.target.value)} /> ~ <Input type="date" className="w-36" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        {selected.size > 0 && (
          <Button variant="outline" size="sm" className="ml-auto text-red-600" onClick={async () => {
            if (!confirm(`${selected.size}개 문서를 삭제할까요?`)) return;
            for (const id of selected) await del.mutateAsync(id).catch((e) => toast.error(errorMessage(e)));
            setSelected(new Set());
          }}><Trash2 /> 선택 삭제 ({selected.size})</Button>
        )}
      </div>

      <div className="rounded-lg border bg-white shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8"><Checkbox checked={items.length > 0 && selected.size === items.length} onCheckedChange={(c) => setSelected(c ? new Set(items.map((i) => i.id)) : new Set())} /></TableHead>
              <TableHead>파일명</TableHead>
              <TableHead className="w-16">포맷</TableHead>
              <TableHead className="w-20">유형</TableHead>
              <TableHead className="w-36">상태</TableHead>
              <TableHead className="w-28">위험</TableHead>
              <TableHead className="w-24">업로드</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && Array.from({ length: 4 }).map((_, i) => (
              <TableRow key={i}><TableCell colSpan={8}><Skeleton className="h-6 w-full" /></TableCell></TableRow>
            ))}
            {isError && <TableRow><TableCell colSpan={8} className="text-red-600">{errorMessage(error)}</TableCell></TableRow>}
            {!isLoading && !isError && items.length === 0 && (
              <TableRow><TableCell colSpan={8}><Empty icon={<FileText />} title="계약서가 없습니다" description="우측 상단 [업로드] 버튼으로 계약서를 추가하세요." /></TableCell></TableRow>
            )}
            {items.map((d) => (
              <DocumentRow
                key={d.id}
                doc={d}
                checked={selected.has(d.id)}
                onCheck={(c) => setSelected((s) => { const n = new Set(s); c ? n.add(d.id) : n.delete(d.id); return n; })}
                onOpen={() => d.status !== 'FAILED' && navigate(`/documents/${d.id}/viewer`)}
                onReprocess={() => reprocess.mutate({ id: d.id }, { onSuccess: () => toast.success('재처리를 시작했습니다'), onError: (e) => toast.error(errorMessage(e)) })}
                onDelete={() => { if (confirm(`'${d.original_name}' 을 삭제할까요?`)) del.mutate(d.id, { onError: (e) => toast.error(errorMessage(e)) }); }}
              />
            ))}
          </TableBody>
        </Table>
        <div className="flex items-center justify-end gap-2 border-t px-3 py-2 text-sm">
          <span className="mr-auto text-xs text-muted-foreground">총 {data?.total ?? 0}건 · 행 클릭 시 Viewer로 이동</span>
          <Button variant="ghost" size="icon-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft /></Button>
          <span className="tabular-nums">{page} / {totalPages}</span>
          <Button variant="ghost" size="icon-sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}><ChevronRight /></Button>
          <Select value={String(size)} onValueChange={(v) => { setSize(Number(v)); setPage(1); }}>
            <SelectTrigger className="h-8 w-24"><SelectValue /></SelectTrigger>
            <SelectContent>{[10, 20, 50].map((n) => <SelectItem key={n} value={String(n)}>{n}개씩</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>

      <UploadModal open={uploadOpen} onOpenChange={setUploadOpen} onUploaded={(items) => setRecent((r) => [...items, ...r])} />
    </div>
  );
}

function DocumentRow({ doc, checked, onCheck, onOpen, onReprocess, onDelete }: {
  doc: DocumentListItem; checked: boolean; onCheck: (c: boolean) => void; onOpen: () => void; onReprocess: () => void; onDelete: () => void;
}) {
  const inProgress = isInProgress(doc.status);
  // 진행 중/실패 행만 /status 로 진행률·오류 조회 (5초 폴링)
  const { data: st } = useDocumentStatus(doc.id, inProgress || doc.status === 'FAILED');
  const liveStatus = st?.status ?? doc.status;
  return (
    <TableRow className={doc.status === 'FAILED' ? 'cursor-default' : 'cursor-pointer'} onClick={onOpen}>
      <TableCell onClick={(e) => e.stopPropagation()}><Checkbox checked={checked} onCheckedChange={(c) => onCheck(c === true)} /></TableCell>
      <TableCell className="font-medium">{doc.original_name}</TableCell>
      <TableCell className="text-muted-foreground">{doc.original_format}</TableCell>
      <TableCell className="text-muted-foreground">{doc.source_type ? SOURCE_LABEL[doc.source_type] ?? doc.source_type : '-'}</TableCell>
      <TableCell>
        <span className="inline-flex items-center gap-1.5">
          <DocStatusBadge status={liveStatus} progress={st?.job?.progress} step={st?.job?.current_step} />
          {liveStatus === 'FAILED' && (
            <Tip text={<span>오류: {st?.job?.error ?? '상세 정보 없음'}</span>}><Info className="h-4 w-4 text-red-500" /></Tip>
          )}
        </span>
      </TableCell>
      <TableCell><RiskSummaryDots summary={doc.risk_summary} /></TableCell>
      <TableCell className="text-muted-foreground">{formatDate(doc.created_at, { short: true })}</TableCell>
      <TableCell onClick={(e) => e.stopPropagation()}>
        <DropdownMenu>
          <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm"><MoreHorizontal /></Button></DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={onOpen} disabled={doc.status === 'FAILED'}><FileText /> Viewer 열기</DropdownMenuItem>
            <DropdownMenuItem onSelect={onReprocess} disabled={inProgress}><RefreshCw /> 재처리</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={onDelete} destructive><Trash2 /> 삭제</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
    </TableRow>
  );
}
