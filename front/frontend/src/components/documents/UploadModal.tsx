import { useCallback, useRef, useState } from 'react';
import { CloudUpload, FileText, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useUploadDocuments, type UploadOptions } from '@/api/documents';
import { errorMessage, ApiError } from '@/lib/api';
import { cn, extOf, formatBytes } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import type { UploadItem } from '@/types/api';

const ALLOWED = ['hwp', 'hwpx', 'pdf', 'docx', 'xlsx', 'jpg', 'jpeg', 'png'];
const MAX_FILES = 10;
const MAX_SIZE = 50 * 1024 * 1024;

interface Props { open: boolean; onOpenChange: (o: boolean) => void; onUploaded: (items: UploadItem[]) => void }

export function UploadModal({ open, onOpenChange, onUploaded }: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [engine, setEngine] = useState<UploadOptions['ocr_engine']>('auto');
  const [skipRisk, setSkipRisk] = useState(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDocuments();

  const addFiles = useCallback((list: FileList | File[]) => {
    const next = [...files];
    for (const f of Array.from(list)) {
      const ext = extOf(f.name);
      if (!ALLOWED.includes(ext)) { toast.error(`지원하지 않는 형식: ${f.name}`); continue; }
      if (f.size > MAX_SIZE) { toast.error(`50MB 초과: ${f.name}`); continue; }
      if (next.some((x) => x.name === f.name && x.size === f.size)) continue;
      if (next.length >= MAX_FILES) { toast.error(`최대 ${MAX_FILES}개까지 업로드할 수 있습니다`); break; }
      next.push(f);
    }
    setFiles(next);
  }, [files]);

  const reset = () => { setFiles([]); setEngine('auto'); setSkipRisk(false); };

  const start = () => {
    upload.mutate({ files, options: { ocr_engine: engine, skip_risk: skipRisk } }, {
      onSuccess: (res) => {
        toast.success(`${res.items.length}개 파일 업로드 완료, 분석을 시작합니다`);
        onUploaded(res.items);
        reset();
        onOpenChange(false);
      },
      onError: (e) => {
        if (e instanceof ApiError && e.code === 'DUPLICATE_DOCUMENT') {
          toast.warning(`이미 업로드된 문서입니다 (${e.message})`);
          const existing = e.detail?.document_id as string | undefined;
          if (existing) onUploaded([{ document_id: existing, job_id: '', original_name: files[0]?.name ?? '', status: 'DONE' }]);
          onOpenChange(false);
          return;
        }
        toast.error(errorMessage(e));
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!upload.isPending) { onOpenChange(o); if (!o) reset(); } }}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>계약서 업로드</DialogTitle>
          <DialogDescription>hwp · hwpx · pdf · docx · xlsx · jpg/png · 최대 10개, 파일당 50MB</DialogDescription>
        </DialogHeader>

        <div
          className={cn('flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors', dragging ? 'border-primary bg-blue-50' : 'border-slate-300 hover:bg-slate-50')}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
        >
          <CloudUpload className="h-8 w-8 text-slate-400" />
          <div className="text-sm font-medium">파일을 드래그하거나 클릭하여 선택</div>
          <div className="text-xs text-muted-foreground">{ALLOWED.join(' · ')}</div>
          <input ref={inputRef} type="file" multiple hidden accept={ALLOWED.map((e) => `.${e}`).join(',')} onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ''; }} />
        </div>

        {files.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-muted-foreground">선택된 파일 ({files.length})</div>
            <ul className="max-h-40 space-y-1 overflow-auto">
              {files.map((f) => (
                <li key={`${f.name}-${f.size}`} className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm">
                  <FileText className="h-4 w-4 text-slate-400" />
                  <span className="truncate">{f.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{formatBytes(f.size)}</span>
                  <button className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600" onClick={() => setFiles(files.filter((x) => x !== f))} aria-label="삭제"><Trash2 className="h-3.5 w-3.5" /></button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-3 text-sm">
          <Label>OCR 엔진</Label>
          <RadioGroup value={engine} onValueChange={(v) => setEngine(v as UploadOptions['ocr_engine'])} className="flex gap-5">
            {(['auto', 'paddle', 'tesseract'] as const).map((v) => (
              <label key={v} className="flex items-center gap-1.5">
                <RadioGroupItem value={v} id={`eng-${v}`} /> {v === 'auto' ? '자동' : v === 'paddle' ? 'PaddleOCR' : 'Tesseract'}
              </label>
            ))}
          </RadioGroup>
          <span />
          <label className="flex items-center gap-2"><Checkbox checked={skipRisk} onCheckedChange={(c) => setSkipRisk(c === true)} /> 위험조항 탐지 생략</label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={upload.isPending}>취소</Button>
          <Button onClick={start} disabled={!files.length} loading={upload.isPending}>업로드 시작</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
