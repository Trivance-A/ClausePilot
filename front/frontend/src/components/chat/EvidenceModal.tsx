import { useMemo } from 'react';
import { Download, MessageSquareReply } from 'lucide-react';
import { toast } from 'sonner';
import { useRegNode } from '@/api/regulations';
import { downloadFile, errorMessage } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { SinglePagePdf } from '@/components/viewer/SinglePagePdf';
import type { Citation } from '@/types/api';

interface Props { citation: Citation | null; onClose: () => void; onAskAgain: (c: Citation) => void; version?: string }

/** SC-08 근거 팝업: 규정 PDF 페이지 렌더 + bbox 하이라이트 + 조·항 원문 (quoted_span 강조) */
export function EvidenceModal({ citation, onClose, onAskAgain }: Props) {
  const { data: node, isLoading } = useRegNode(citation?.regulation_id, citation?.node_id);
  const pathParts = (node?.path ?? citation?.path ?? '').split('>').map((s) => s.trim()).filter(Boolean);
  const content = node?.content ?? citation?.quoted_span ?? '';
  const pageNo = node?.page_no ?? citation?.page_no ?? null;
  const bbox = node?.bbox ?? citation?.bbox ?? null;
  const pdfPath = citation ? `/regulations/${citation.regulation_id}/pdf` : '';

  const highlighted = useMemo(() => {
    const span = citation?.quoted_span;
    if (!span || !content.includes(span)) return [{ t: content, hl: false }];
    const i = content.indexOf(span);
    return [{ t: content.slice(0, i), hl: false }, { t: span, hl: true }, { t: content.slice(i + span.length), hl: false }];
  }, [content, citation]);

  return (
    <Dialog open={!!citation} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-1 text-base">
            <span className="text-primary">{citation?.regulation_title}</span>
            {pathParts.map((p, i) => <span key={i} className="flex items-center gap-1 text-slate-700"><span className="text-slate-400">›</span>{p}</span>)}
          </DialogTitle>
          <DialogDescription>{pageNo ? `규정 PDF p.${pageNo}` : '위치 정보 없음'} · 근거 [{citation?.ref}]</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-[440px_1fr] gap-4">
          <div className="max-h-[60vh] overflow-auto rounded-md bg-slate-100 p-3">
            {citation && pageNo ? <SinglePagePdf pdfPath={pdfPath} pageNo={pageNo} bbox={bbox} width={410} /> : <div className="p-6 text-xs text-muted-foreground">페이지 정보가 없어 원문 텍스트만 표시합니다.</div>}
          </div>
          <div className="max-h-[60vh] overflow-auto">
            <div className="mb-2 text-sm font-semibold">{pathParts[pathParts.length - 2] ?? pathParts[pathParts.length - 1] ?? '조항 원문'}</div>
            {isLoading ? <div className="text-sm text-muted-foreground">원문을 불러오는 중…</div> : (
              <p className="whitespace-pre-wrap text-sm leading-6">
                {highlighted.map((h, i) => h.hl ? <mark key={i} className="rounded bg-emerald-200 px-0.5">{h.t}</mark> : <span key={i}>{h.t}</span>)}
              </p>
            )}
            {!node && citation?.quoted_span && <div className="mt-2 text-xs text-muted-foreground">※ node_id가 없어 인용 구간(quoted_span)만 표시합니다.</div>}
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => citation && downloadFile(pdfPath, `${citation.regulation_title}.pdf`).catch((e) => toast.error(errorMessage(e)))}><Download /> 원문 PDF 열기</Button>
          <Button onClick={() => citation && onAskAgain(citation)}><MessageSquareReply /> 이 조항으로 다시 질문</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
