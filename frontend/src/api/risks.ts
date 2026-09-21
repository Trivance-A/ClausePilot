import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { RiskFinding, RiskStatus, RisksResponse } from '@/types/api';

export function useRisks(docId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['risks', docId],
    queryFn: () => api<RisksResponse>(`/documents/${docId}/risks`),
    enabled: !!docId && enabled,
  });
}

export function usePatchRisk(docId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ rid, status, note }: { rid: string; status: RiskStatus; note?: string }) =>
      api<RiskFinding>(`/risks/${rid}`, { method: 'PATCH', body: { status, note } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks', docId] }),
  });
}

export function useRerunRisks(docId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ job_id: string }>(`/documents/${docId}/risks/rerun`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['document-status', docId] }),
  });
}
