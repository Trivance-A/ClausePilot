import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import type { LoginResponse, User } from '@/types/api';

export function useLogin() {
  const login = useAuthStore((s) => s.login);
  return useMutation({
    mutationFn: (body: { email: string; password: string }) => api<LoginResponse>('/auth/login', { method: 'POST', body }),
    onSuccess: (res) => login(res.access_token, res.user),
  });
}

export function useMe(enabled: boolean) {
  const setUser = useAuthStore((s) => s.setUser);
  return useQuery({
    queryKey: ['me'],
    queryFn: async () => { const u = await api<User>('/auth/me'); setUser(u); return u; },
    enabled,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}
