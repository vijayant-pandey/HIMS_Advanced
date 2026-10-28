import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type { Account, AccountCreateRequest, PaginatedAccountList } from "../../api/types";

export const accountsKey = ["accounts"] as const;

export function useAccounts(filters: { search: string; kind: string; status: string }, page = 1) {
  return useQuery<PaginatedAccountList, ApiError>({
    queryKey: [...accountsKey, "list", filters, page],
    queryFn: ({ signal }) =>
      api.get<PaginatedAccountList>("/accounts/", { query: { ...filters, page }, signal }),
    placeholderData: keepPreviousData,
  });
}

export function useAccount(id: string | undefined) {
  return useQuery<Account, ApiError>({
    queryKey: [...accountsKey, "detail", id],
    queryFn: ({ signal }) => api.get<Account>(`/accounts/${id}/`, { signal }),
    enabled: !!id,
  });
}

export function useCreateAccount(idempotencyKey: string) {
  const queryClient = useQueryClient();
  return useMutation<Account, ApiError, AccountCreateRequest>({
    mutationFn: (body) => api.post<Account>("/accounts/", body, { idempotencyKey }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: accountsKey }),
  });
}

/** Actions on one account: switch off/on (with a reason), invite, reset two-factor, sign out. */
export type AccountAction =
  | "deactivate"
  | "reactivate"
  | "invitation"
  | "reset-two-factor"
  | "sign-out-everywhere";

export function useAccountAction(id: string, action: AccountAction) {
  const queryClient = useQueryClient();
  return useMutation<Account, ApiError, { reason?: string }>({
    mutationFn: (body) => api.post<Account>(`/accounts/${id}/${action}/`, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: accountsKey }),
  });
}
