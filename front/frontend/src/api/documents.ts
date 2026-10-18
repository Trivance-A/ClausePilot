import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type {
  DocumentDetail, DocumentListItem, DocumentStatus, DocumentStatusResponse, LinesResponse, Paginated, UploadResponse,
} from '@/types/api';

export const IN_PROGRESS: DocumentStatus[] = ['UPLOADED', 'NORMALIZING', 'OCR', 'EXTRACTING', 'RISK'];
export const isInProgress = (s: DocumentStatus) => IN_PROGRESS.includes(s);

export interface DocumentListParams { q?: string; status?: string; from?: string; to?: string; page?: number; size?: number }

export function useDocuments(params: DocumentListParams) {
  return useQuery({
    queryKey: ['documents', params],
    queryFn: () => api<Paginated<DocumentListItem>>('/documents', { query: { ...params } }),
    // 진행 중 행이 있으면 5초 폴링
    refetchInterval: (q) => (q.state.data?.items.some((d) => isInProgress(d.status)) ? 5000 : false),
  });
}

export function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: ['document', id],
    queryFn: () => api<DocumentDetail>(`/documents/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && isInProgress(q.state.data.status) ? 5000 : false),
  });
}

export function useDocumentStatus(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['document-status', id],
    queryFn: () => api<DocumentStatusResponse>(`/documents/${id}/status`),
    enabled: !!id && enabled,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return !s || isInProgress(s) ? 5000 : false;
    },
  });
}

export function useDocumentLines(id: string | undefined, page: number | undefined) {
  return useQuery({
    queryKey: ['document-lines', id, page],
    queryFn: () => api<LinesResponse>(`/documents/${id}/lines`, { query: { page } }),
    enabled: !!id && !!page,
    staleTime: 60_000,
  });
}

export interface UploadOptions { ocr_engine: 'auto' | 'paddle' | 'tesseract'; skip_risk: boolean }

export function useUploadDocuments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ files, options }: { files: File[]; options: UploadOptions }) => {
      const form = new FormData();
      files.forEach((f) => form.append('files', f));
      form.append('ocr_engine', options.ocr_engine);
      form.append('skip_risk', String(options.skip_risk));
      return api<UploadResponse>('/documents', { method: 'POST', form });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
}

export function useReprocessDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, from_step, ocr_engine }: { id: string; from_step?: 'ocr' | 'extract' | 'risk'; ocr_engine?: string }) =>
      api<{ job_id: string }>(`/documents/${id}/reprocess`, { method: 'POST', body: { from_step, ocr_engine } }),
    onSuccess: (_r, v) => {
      qc.invalidateQueries({ queryKey: ['documents'] });
      qc.invalidateQueries({ queryKey: ['document', v.id] });
      qc.invalidateQueries({ queryKey: ['document-status', v.id] });
    },
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/documents/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
}
