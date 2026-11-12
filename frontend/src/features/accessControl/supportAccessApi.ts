import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type { SupportAccess, SupportAccessOptions, SupportAccessRequestRequest } from "../../api/types";
import { accessKey } from "./api";

// Under the access key: giving or ending support access changes who can do what.
const supportKey = [...accessKey, "support"] as const;

export type SupportFilter = "current" | "past";

/** The hospital's side: every request from the software supplier (HIMS-IAM-021). */
export function useSupportRequests(status: SupportFilter, enabled = true) {
  return useQuery<SupportAccess[], ApiError>({
    queryKey: [...supportKey, "hospital", status],
    queryFn: ({ signal }) => api.get<SupportAccess[]>("/support-access/", { query: { status }, signal }),
    enabled,
  });
}

/** The supplier's side: its own requests. */
export function useMySupportRequests(enabled = true) {
  return useQuery<SupportAccess[], ApiError>({
    queryKey: [...supportKey, "mine"],
    queryFn: ({ signal }) => api.get<SupportAccess[]>("/my-support-access/", { signal }),
    enabled,
  });
}

export function useSupportOptions(enabled = true) {
  return useQuery<SupportAccessOptions, ApiError>({
    queryKey: [...supportKey, "options"],
    queryFn: ({ signal }) => api.get<SupportAccessOptions>("/my-support-access/options/", { signal }),
    enabled,
  });
}

export function useAskForSupportAccess(idempotencyKey: string) {
  const queryClient = useQueryClient();
  return useMutation<SupportAccess, ApiError, SupportAccessRequestRequest>({
    mutationFn: (body) => api.post<SupportAccess>("/my-support-access/", body, { idempotencyKey }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: accessKey }),
  });
}

type Decision = "approve" | "refuse" | "end" | "cancel";

/** Approve, refuse or end (hospital), or cancel or end (supplier: ``mine``). */
export function useSupportDecision(id: string, decision: Decision, mine: boolean) {
  const queryClient = useQueryClient();
  const base = mine ? "/my-support-access/" : "/support-access/";
  return useMutation<SupportAccess, ApiError, { version: number; note?: string; reason?: string }>({
    mutationFn: (body) => api.post<SupportAccess>(`${base}${id}/${decision}/`, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: accessKey }),
  });
}
