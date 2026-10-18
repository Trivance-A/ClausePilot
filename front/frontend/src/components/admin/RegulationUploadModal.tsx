import { useState } from 'react';
import { toast } from 'sonner';
import { useUploadRegulation } from '@/api/regulations';
import { errorMessage } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { RegDocType } from '@/types/api';

const TYPES: RegDocType[] = ['정관', '규정', '지침', '매뉴얼'];

export function RegulationUploadModal({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [docType, setDocType] = useState<RegDocType>('규정');
  const [date, setDate] = useState('');
  const upload = useUploadRegulation();

  const submit = () => {
    if (!file || !title.trim()) return;
    upload.mutate({ file, title: title.trim(), doc_type: docType, effective_date: date || undefined }, {
      onSuccess: (r) => { toast.success(`업로드 완료 (v${r.version}) · 파싱·색인을 시작합니다`); onOpenChange(false); setFile(null); setTitle(''); setDate(''); },
      onError: (e) => toast.error(errorMessage(e)),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>규정 업로드</DialogTitle>
          <DialogDescription>hwp · hwpx · pdf · docx — 같은 제목 재업로드 시 version+1, 이전 버전은 ARCHIVED</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1"><Label>파일</Label><Input type="file" accept=".hwp,.hwpx,.pdf,.docx" onChange={(e) => { const f = e.target.files?.[0] ?? null; setFile(f); if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, '')); }} /></div>
          <div className="space-y-1"><Label>제목</Label><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="계약사무규정" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label>유형</Label>
              <Select value={docType} onValueChange={(v) => setDocType(v as RegDocType)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1"><Label>시행일 (선택)</Label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>취소</Button>
          <Button onClick={submit} disabled={!file || !title.trim()} loading={upload.isPending}>업로드·색인</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
