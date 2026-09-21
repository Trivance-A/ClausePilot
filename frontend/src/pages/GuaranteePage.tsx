import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, FileText, Paperclip, Sparkles, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { useDocumentStatus, useDocuments } from '@/api/documents';
import { useCreateGuaranteeApplication, usePatchGuaranteeApplication } from '@/api/guarantee';
import { useRisks } from '@/api/risks';
import { errorMessage } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { PageHeader } from '@/components/layout/PageHeader';
import { UploadModal } from '@/components/documents/UploadModal';
import { ProgressCard } from '@/components/documents/ProgressCard';
import { AutofillForm } from '@/components/guarantee/AutofillForm';
import { GUARANTEE_TYPE_LABELS, FIELD_CODES, type GuaranteeApplication, type GuaranteeFormValues, type GuaranteeType, type UploadItem } from '@/types/api';

const TYPES: GuaranteeType[] = ['contract', 'bid', 'defect', 'payment', 'other'];

export function GuaranteePage() {
  const [params, setParams] = useSearchParams();
  const [type, setType] = useState<GuaranteeType>('contract');
  const [docId, setDocId] = useState<string>(params.get('document_id') ?? '');
  const [uploading, setUploading] = useState<UploadItem | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [app, setApp] = useState<GuaranteeApplication | null>(null);
  const [values, setValues] = useState<GuaranteeFormValues | null>(null);
  const [showErrors, setShowErrors] = useState(false);

  const { data: docs } = useDocuments({ status: 'DONE', size: 50 });
  const { data: upStatus } = useDocumentStatus(uploading?.document_id, !!uploading);
  const create = useCreateGuaranteeApplication();
  const patch = usePatchGuaranteeApplication();
  const { data: risks } = useRisks(app?.document_id, !!app);

  // 업로드한 문서 분석 완료 → 자동 선택
  useEffect(() => {
    if (uploading && upStatus?.status === 'DONE') { setDocId(uploading.document_id); setUploading(null); toast.success('분석 완료, 항목을 자동 입력합니다'); }
    if (uploading && upStatus?.status === 'FAILED') { toast.error(`분석 실패: ${upStatus.job?.error ?? ''}`); setUploading(null); }
  }, [upStatus, uploading]);

  // 문서·보증종류 변경 시 신청서 생성(자동입력) → 폼 재구성
  useEffect(() => {
    if (!docId) { setApp(null); setValues(null); return; }
    create.mutate({ document_id: docId, guarantee_type: type }, {
      onSuccess: (a) => { setApp(a); setValues(a.form_values); setShowErrors(false); setParams({ document_id: docId }, { replace: true }); },
      onError: (e) => toast.error(errorMessage(e)),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId, type]);

  const selectedDoc = useMemo(() => docs?.items.find((d) => d.id === docId), [docs, docId]);
  const filled = useMemo(() => {
    if (!app || !values) return 0;
    const req = app.required_fields?.length ? app.required_fields : FIELD_CODES;
    return req.filter((c) => app.field_sources?.[c] && values[c] !== null && values[c] !== undefined).length;
  }, [app, values]);
  const reqCount = app ? (app.required_fields?.length ? app.required_fields.length : FIELD_CODES.length) : 0;
  const highCount = risks?.summary?.HIGH ?? app?.risk_summary?.HIGH ?? 0;

  const save = (status: 'DRAFT' | 'SUBMITTED') => {
    if (!app || !values) return;
    if (status === 'SUBMITTED') {
      const req = app.required_fields?.length ? app.required_fields : FIELD_CODES;
      const missing = req.filter((c) => { const v = values[c]; return v === null || v === undefined || v === '' || (c === 'guarantee_period' && !(v as { start?: string | null })?.start); });
      if (missing.length) { setShowErrors(true); toast.error(`필수 항목 ${missing.length}개를 입력해 주세요`); return; }
    }
    patch.mutate({ id: app.id, form_values: values, status }, {
      onSuccess: (a) => { setApp({ ...app, status: a.status ?? status }); toast.success(status === 'SUBMITTED' ? '신청(Demo)이 접수되었습니다. 실제 EBIZ 연동은 범위 외입니다.' : '임시저장했습니다'); },
      onError: (e) => toast.error(errorMessage(e)),
    });
  };

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="보증발급 신청 (Demo)" description="계약서를 첨부하면 8개 항목을 자동 입력합니다. 🔗 배지를 누르면 검증 화면(Viewer)의 근거 위치로 이동합니다. (RFP SFR-004 시연)" />

      <section className="mb-4 rounded-lg border bg-white p-4">
        <div className="mb-2 text-sm font-semibold">보증종류</div>
        <RadioGroup value={type} onValueChange={(v) => setType(v as GuaranteeType)} className="flex flex-wrap gap-5">
          {TYPES.map((t) => (
            <label key={t} className="flex items-center gap-1.5 text-sm"><RadioGroupItem value={t} /> {GUARANTEE_TYPE_LABELS[t]}</label>
          ))}
        </RadioGroup>
        <div className="mt-1 text-xs text-muted-foreground">보증종류별 필수 필드 세트(required_fields)가 달라 라디오 변경 시 폼이 재구성됩니다.</div>
      </section>

      <section className="mb-4 rounded-lg border bg-white p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold"><Paperclip className="h-4 w-4" /> 계약서 첨부</div>
        {uploading ? (
          <ProgressCard documentId={uploading.document_id} name={uploading.original_name} />
        ) : (
          <div className="flex items-center gap-2">
            <Select value={docId} onValueChange={setDocId}>
              <SelectTrigger className="w-96"><SelectValue placeholder="분석 완료된 계약서 선택" /></SelectTrigger>
              <SelectContent>
                {(docs?.items ?? []).map((d) => <SelectItem key={d.id} value={d.id}>{d.original_name} ({d.original_format}, {d.page_count ?? '?'}p)</SelectItem>)}
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={() => setUploadOpen(true)}><Upload /> {docId ? '다른 파일 선택' : '새 파일 업로드'}</Button>
            {selectedDoc && <Badge variant="success"><CheckCircle2 className="h-3 w-3" /> 분석 완료</Badge>}
            {selectedDoc && <Button variant="link" size="sm" asChild><Link to={`/documents/${selectedDoc.id}/viewer`} target="_blank"><FileText /> Viewer</Link></Button>}
          </div>
        )}
      </section>

      {create.isPending && <div className="mb-4 rounded-lg border bg-white p-4 text-sm text-muted-foreground">자동 입력 중…</div>}

      {app && values && (
        <>
          <div className="mb-3 flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            <Sparkles className="h-4 w-4" /> 계약서에서 <b>{filled}/{reqCount}</b>개 항목을 자동 입력했습니다. 값을 확인하세요.
            <span className="ml-auto text-xs">{app.status === 'SUBMITTED' ? '신청 완료 (Demo)' : '임시 저장 상태'}</span>
          </div>
          <AutofillForm app={app} values={values} onChange={setValues} showErrors={showErrors} />
          {highCount > 0 && (
            <div className="mt-3 flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              <AlertTriangle className="h-4 w-4" /> 위험조항 HIGH {highCount}건이 탐지되었습니다.
              <Link to={`/documents/${app.document_id}/viewer`} target="_blank" className="ml-1 font-semibold underline">검증 화면에서 확인</Link>
            </div>
          )}
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => save('DRAFT')} loading={patch.isPending}>임시저장</Button>
            <Button onClick={() => save('SUBMITTED')} loading={patch.isPending} disabled={app.status === 'SUBMITTED'}>신청(Demo)</Button>
          </div>
        </>
      )}

      <UploadModal open={uploadOpen} onOpenChange={setUploadOpen} onUploaded={(items) => { const first = items[0]; if (first) { first.status === 'DONE' ? setDocId(first.document_id) : setUploading(first); } }} />
    </div>
  );
}
