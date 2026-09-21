import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { BBox, ExtractionField, ExtractionResponse, FieldCode, FieldPatch, Highlight } from '@/types/api';

export function useExtractions(docId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['extractions', docId],
    queryFn: () => api<ExtractionResponse>(`/documents/${docId}/extractions`),
    enabled: !!docId && enabled,
  });
}

export function usePatchField(docId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ field_code, patch }: { field_code: FieldCode; patch: FieldPatch }) =>
      api<ExtractionField>(`/documents/${docId}/extractions/fields/${field_code}`, { method: 'PATCH', body: patch }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['extractions', docId] }),
  });
}

/** V-11 [확정]: 전체 필드 is_confirmed=true */
export function useConfirmAll(docId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (fields: ExtractionField[]) => {
      for (const f of fields) {
        if (!f.is_confirmed) await api(`/documents/${docId}/extractions/fields/${f.field_code}`, { method: 'PATCH', body: { is_confirmed: true } });
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['extractions', docId] });
      qc.invalidateQueries({ queryKey: ['document', docId] });
    },
  });
}

export type CreateHighlightBody =
  | { field_code: FieldCode; page_no: number; bbox: BBox }
  | { risk_finding_id: string; page_no: number; bbox: BBox };

export function useCreateHighlight(docId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateHighlightBody) => api<Highlight>(`/documents/${docId}/highlights`, { method: 'POST', body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['extractions', docId] });
      qc.invalidateQueries({ queryKey: ['risks', docId] });
    },
  });
}

export function usePatchHighlight(docId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ hid, bbox, page_no }: { hid: string; bbox: BBox; page_no: number }) =>
      api<Highlight>(`/highlights/${hid}`, { method: 'PATCH', body: { bbox, page_no } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['extractions', docId] });
      qc.invalidateQueries({ queryKey: ['risks', docId] });
    },
  });
}

export function useDeleteHighlight(docId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (hid: string) => api<void>(`/highlights/${hid}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['extractions', docId] });
      qc.invalidateQueries({ queryKey: ['risks', docId] });
    },
  });
}
