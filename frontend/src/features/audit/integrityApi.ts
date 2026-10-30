import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type { AuditIntegrityCheck, AuditIntegrityCheckDetail, AuditIntegrityStatus } from "../../api/types";

const integrityKey = ["audit", "integrity"] as const;

export function useIntegrityStatus() {
  return useQuery<AuditIntegrityStatus, ApiError>({
    queryKey: [...integrityKey, "status"],
    queryFn: ({ signal }) => api.get<AuditIntegrityStatus>("/audit-integrity-checks/status/", { signal }),
  });
}

export function useIntegrityChecks() {
  return useQuery<AuditIntegrityCheck[], ApiError>({
    queryKey: [...integrityKey, "list"],
    queryFn: ({ signal }) => api.get<AuditIntegrityCheck[]>("/audit-integrity-checks/", { signal }),
  });
}

export function useIntegrityCheck(id: string) {
  return useQuery<AuditIntegrityCheckDetail, ApiError>({
    queryKey: [...integrityKey, id],
    queryFn: ({ signal }) => api.get<AuditIntegrityCheckDetail>(`/audit-integrity-checks/${id}/`, { signal }),
  });
}

/** Seals new events and checks the whole chain now (recorded in the audit log). */
export function useRunIntegrityCheck() {
  const queryClient = useQueryClient();
  return useMutation<AuditIntegrityCheckDetail, ApiError, void>({
    mutationFn: () => api.post<AuditIntegrityCheckDetail>("/audit-integrity-checks/", {}),
    onSettled: () => queryClient.invalidateQueries({ queryKey: integrityKey }),
  });
}
