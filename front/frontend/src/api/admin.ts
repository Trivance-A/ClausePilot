import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { AdminJob, AdminStats, ChatLogItem, EvalRun, EvalSuite, Paginated } from '@/types/api';

export function useAdminStats() {
  return useQuery({ queryKey: ['admin-stats'], queryFn: () => api<AdminStats>('/admin/stats'), refetchInterval: 30_000 });
}

export function useAdminJobs(status?: string) {
  return useQuery({
    queryKey: ['admin-jobs', status],
    queryFn: () => api<{ items: AdminJob[] }>('/admin/jobs', { query: { status } }),
    refetchInterval: 15_000,
  });
}

export function useChatLogs(params: { from?: string; to?: string; answer_status?: string; page?: number; size?: number }) {
  return useQuery({
    queryKey: ['admin-chat-logs', params],
    queryFn: () => api<Paginated<ChatLogItem>>('/admin/logs/chat', { query: { ...params } }),
  });
}

export function useRunEval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (suite: EvalSuite) => api<{ run_id: string; id?: string }>('/eval/run', { method: 'POST', body: { suite } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['eval-runs'] }),
  });
}

export function useEvalRun(id: string | undefined) {
  return useQuery({
    queryKey: ['eval-run', id],
    queryFn: () => api<EvalRun>(`/eval/runs/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && ['QUEUED', 'RUNNING'].includes(q.state.data.status) ? 3000 : false),
  });
}

/** 최근 평가 실행 목록 (명세 외 보조 엔드포인트; 없으면 빈 목록) */
export function useEvalRuns() {
  return useQuery({
    queryKey: ['eval-runs'],
    queryFn: async () => {
      try { return await api<{ items: EvalRun[] }>('/eval/runs'); } catch { return { items: [] as EvalRun[] }; }
    },
  });
}
