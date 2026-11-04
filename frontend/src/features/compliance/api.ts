import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  ComplianceRequirement,
  ComplianceSummary,
  IncidentReceipt,
  IncidentReportRequest,
  RiskEntry,
  SecurityIncident,
} from "../../api/types";

const key = ["compliance"] as const;

export function useComplianceSummary() {
  return useQuery<ComplianceSummary, ApiError>({
    queryKey: [...key, "summary"],
    queryFn: ({ signal }) => api.get<ComplianceSummary>("/compliance-summary/", { signal }),
  });
}

export function useRequirements(filters: { status: string; search: string }) {
  return useQuery<ComplianceRequirement[], ApiError>({
    queryKey: [...key, "requirements", filters],
    queryFn: ({ signal }) => api.get<ComplianceRequirement[]>("/compliance-requirements/", { query: filters, signal }),
  });
}

export function useRisks() {
  return useQuery<RiskEntry[], ApiError>({
    queryKey: [...key, "risks"],
    queryFn: ({ signal }) => api.get<RiskEntry[]>("/compliance-risks/", { signal }),
  });
}

export function useIncidents() {
  return useQuery<SecurityIncident[], ApiError>({
    queryKey: [...key, "incidents"],
    queryFn: ({ signal }) => api.get<SecurityIncident[]>("/security-incidents/", { signal }),
  });
}

function useChange<TResult, TBody>(request: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation<TResult, ApiError, TBody>({
    mutationFn: request,
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}

export function useUpdateRequirement(id: string) {
  return useChange((body: Record<string, unknown>) =>
    api.patch<ComplianceRequirement>(`/compliance-requirements/${id}/`, body),
  );
}

export function useCreateRisk(idempotencyKey: string) {
  return useChange((body: Record<string, unknown>) =>
    api.post<RiskEntry>("/compliance-risks/", body, { idempotencyKey }),
  );
}

export function useUpdateRisk(id: string) {
  return useChange((body: Record<string, unknown>) => api.patch<RiskEntry>(`/compliance-risks/${id}/`, body));
}

export function useReportIncident(idempotencyKey: string) {
  return useChange((body: IncidentReportRequest) =>
    api.post<IncidentReceipt>("/security-incidents/", body, { idempotencyKey }),
  );
}

export function useUpdateIncident(id: string) {
  return useChange((body: Record<string, unknown>) => api.patch<SecurityIncident>(`/security-incidents/${id}/`, body));
}

export function useRecordNotification(incidentId: string) {
  return useChange(({ id, ...body }: { id: string; status: "done" | "not_required"; reference: string; note: string }) =>
    api.post<SecurityIncident>(`/security-incidents/${incidentId}/notifications/${id}/`, body),
  );
}
