import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { GuaranteeApplication, GuaranteeFormValues, GuaranteeType } from '@/types/api';

export function useCreateGuaranteeApplication() {
  return useMutation({
    mutationFn: (body: { document_id: string; guarantee_type: GuaranteeType }) =>
      api<GuaranteeApplication>('/guarantee-applications', { method: 'POST', body }),
  });
}

export function useGuaranteeApplication(id: string | undefined) {
  return useQuery({
    queryKey: ['guarantee-application', id],
    queryFn: () => api<GuaranteeApplication>(`/guarantee-applications/${id}`),
    enabled: !!id,
  });
}

export function usePatchGuaranteeApplication() {
  return useMutation({
    mutationFn: ({ id, form_values, status }: { id: string; form_values: GuaranteeFormValues; status?: 'DRAFT' | 'SUBMITTED' }) =>
      api<GuaranteeApplication>(`/guarantee-applications/${id}`, { method: 'PATCH', body: { form_values, status } }),
  });
}
