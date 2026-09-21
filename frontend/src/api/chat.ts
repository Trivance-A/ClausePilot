import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { ChatMessage, ChatSession } from '@/types/api';

export function useChatSessions() {
  return useQuery({
    queryKey: ['chat-sessions'],
    queryFn: () => api<{ items: ChatSession[] }>('/chat/sessions'),
  });
}

export function useCreateChatSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { title?: string; regulation_ids: string[] }) => api<{ session_id: string }>('/chat/sessions', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['chat-sessions'] }),
  });
}

export function useChatMessages(sid: string | undefined) {
  return useQuery({
    queryKey: ['chat-messages', sid],
    queryFn: () => api<{ items: ChatMessage[] }>(`/chat/sessions/${sid}/messages`),
    enabled: !!sid,
  });
}

export function useMessageFeedback() {
  return useMutation({
    mutationFn: ({ mid, rating, comment }: { mid: string; rating: 1 | -1; comment?: string }) =>
      api(`/chat/messages/${mid}/feedback`, { method: 'POST', body: { rating, comment } }),
  });
}
