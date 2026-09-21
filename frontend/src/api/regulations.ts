import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { RegDocType, RegNodeContent, RegulationDetail, RegulationListItem } from '@/types/api';

const PARSING = ['UPLOADED', 'PARSING'];

export function useRegulations() {
  return useQuery({
    queryKey: ['regulations'],
    queryFn: () => api<{ items: RegulationListItem[] }>('/regulations'),
    refetchInterval: (q) => (q.state.data?.items.some((r) => PARSING.includes(r.status)) ? 5000 : false),
  });
}

export function useRegulation(id: string | undefined) {
  return useQuery({
    queryKey: ['regulation', id],
    queryFn: () => api<RegulationDetail>(`/regulations/${id}`),
    enabled: !!id,
  });
}

export function useRegNode(regId: string | undefined | null, nodeId: string | undefined | null) {
  return useQuery({
    queryKey: ['reg-node', regId, nodeId],
    queryFn: () => api<RegNodeContent>(`/regulations/${regId}/nodes/${nodeId}`),
    enabled: !!regId && !!nodeId,
    staleTime: 5 * 60_000,
  });
}

export function useUploadRegulation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, title, doc_type, effective_date }: { file: File; title: string; doc_type: RegDocType; effective_date?: string }) => {
      const form = new FormData();
      form.append('file', file);
      form.append('title', title);
      form.append('doc_type', doc_type);
      if (effective_date) form.append('effective_date', effective_date);
      return api<{ regulation_id: string; job_id: string; version: number; status: string }>('/regulations', { method: 'POST', form });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['regulations'] }),
  });
}

export function useReindexRegulation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, chunk_strategy }: { id: string; chunk_strategy?: 'article' | 'paragraph' }) =>
      api<{ job_id: string }>(`/regulations/${id}/reindex`, { method: 'POST', body: chunk_strategy ? { chunk_strategy } : undefined }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['regulations'] }),
  });
}

export function useDeleteRegulation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/regulations/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['regulations'] }),
  });
}
