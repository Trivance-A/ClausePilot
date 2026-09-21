import { useState } from 'react';
import { AlertCircle, BookOpen, ListTree, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useDeleteRegulation, useRegulations, useReindexRegulation } from '@/api/regulations';
import { errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tip } from '@/components/ui/tooltip';
import { Empty } from '@/components/ui/empty';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { PageHeader } from '@/components/layout/PageHeader';
import { RegStatusBadge } from '@/components/documents/StatusBadge';
import { RegulationUploadModal } from '@/components/admin/RegulationUploadModal';
import { StructureTreeDialog } from '@/components/admin/StructureTree';

export function AdminRegulationsPage() {
  const { data, isLoading } = useRegulations();
  const reindex = useReindexRegulation();
  const del = useDeleteRegulation();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [treeId, setTreeId] = useState<string | null>(null);
  const [errorOf, setErrorOf] = useState<{ title: string; error: string } | null>(null);
  const items = (data?.items ?? []).filter((r) => r.status !== 'ARCHIVED');

  return (
    <div>
      <PageHeader title="규정 지식베이스" description="규정 업로드 → 장·조·항·목 구조 파싱 → 조 단위 청킹 → 임베딩·BM25 색인. 재색인은 수동 트리거입니다." actions={<Button onClick={() => setUploadOpen(true)}><Plus /> 규정 업로드</Button>} />
      <div className="rounded-lg border bg-white shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>제목</TableHead><TableHead className="w-20">유형</TableHead><TableHead className="w-16">버전</TableHead>
              <TableHead className="w-28">시행일</TableHead><TableHead className="w-28">상태</TableHead><TableHead className="w-16 text-right">청크</TableHead><TableHead className="w-64">작업</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <TableRow><TableCell colSpan={7} className="text-muted-foreground">불러오는 중…</TableCell></TableRow>}
            {!isLoading && items.length === 0 && <TableRow><TableCell colSpan={7}><Empty icon={<BookOpen />} title="등록된 규정이 없습니다" /></TableCell></TableRow>}
            {items.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="font-medium">{r.title}</TableCell>
                <TableCell>{r.doc_type}</TableCell>
                <TableCell>v{r.version}</TableCell>
                <TableCell className="text-muted-foreground">{r.effective_date ? formatDate(r.effective_date) : '-'}</TableCell>
                <TableCell><RegStatusBadge status={r.status} /></TableCell>
                <TableCell className="text-right tabular-nums">{r.chunk_count ?? '-'}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    {r.status === 'INDEXED' && (
                      <>
                        <Button size="xs" variant="ghost" onClick={() => reindex.mutate({ id: r.id }, { onSuccess: () => toast.success('재색인을 시작했습니다'), onError: (e) => toast.error(errorMessage(e)) })}><RefreshCw /> 재색인</Button>
                        <Button size="xs" variant="ghost" onClick={() => setTreeId(r.id)}><ListTree /> 구조보기</Button>
                        <Button size="xs" variant="ghost" className="text-red-600" onClick={() => { if (confirm(`'${r.title}' 을 삭제(ARCHIVED)할까요?`)) del.mutate(r.id, { onError: (e) => toast.error(errorMessage(e)) }); }}><Trash2 /> 삭제</Button>
                      </>
                    )}
                    {r.status === 'FAILED' && (
                      <>
                        <Tip text={r.error ?? '상세 오류 없음'}><Button size="xs" variant="ghost" className="text-red-600" onClick={() => setErrorOf({ title: r.title, error: r.error ?? '상세 오류 없음' })}><AlertCircle /> 오류보기</Button></Tip>
                        <Button size="xs" variant="ghost" onClick={() => reindex.mutate({ id: r.id }, { onSuccess: () => toast.success('재시도를 시작했습니다'), onError: (e) => toast.error(errorMessage(e)) })}><RefreshCw /> 재시도</Button>
                        <Button size="xs" variant="ghost" className="text-red-600" onClick={() => { if (confirm('삭제할까요?')) del.mutate(r.id); }}><Trash2 /> 삭제</Button>
                      </>
                    )}
                    {(r.status === 'PARSING' || r.status === 'UPLOADED') && <span className="text-xs text-muted-foreground">— 처리 중 (5초 폴링)</span>}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">[구조보기] → 장·조·항 트리(파싱 검수용) · 재업로드 시 version+1, 이전 버전 ARCHIVED(검색 제외, 과거 인용 보존)</p>

      <RegulationUploadModal open={uploadOpen} onOpenChange={setUploadOpen} />
      <StructureTreeDialog regId={treeId} onClose={() => setTreeId(null)} />
      <Dialog open={!!errorOf} onOpenChange={(o) => !o && setErrorOf(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>색인 오류 — {errorOf?.title}</DialogTitle><DialogDescription>job.error</DialogDescription></DialogHeader>
          <pre className="max-h-80 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">{errorOf?.error}</pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}
