import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  ScanResult,
  ScanningStatus,
  BrowserSecurityReport,
  ComplianceRequirement,
  ComplianceSummary,
  ConsoleAccess,
  ConsoleAccessBlock,
  DatabaseAccess,
  IncidentReceipt,
  IncidentReportRequest,
  LegalHold,
  LegalHoldPlaceRequest,
  RetentionPurgeRun,
  RetentionStatus,
  RiskEntry,
  SecurityIncident,
  HostingReadiness,
  SecurityReview,
  SecurityStatus,
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

/** How the app's database user is limited (HIMS-OPS-007); read from the database itself. */
/** The Phase 1 security review and the encryption key status (HIMS-SEC-011). */
export function useSecurityReview() {
  return useQuery<SecurityReview, ApiError>({
    queryKey: [...key, "security-review"],
    queryFn: ({ signal }) => api.get<SecurityReview>("/security/review/", { signal }),
  });
}

/** What this server still needs before it hosts HIMS (HIMS-OPS-020). */
export function useHostingReadiness() {
  return useQuery<HostingReadiness, ApiError>({
    queryKey: [...key, "hosting"],
    queryFn: ({ signal }) => api.get<HostingReadiness>("/security/hosting/", { signal }),
  });
}

export function useDatabaseAccess() {
  return useQuery<DatabaseAccess, ApiError>({
    queryKey: [...key, "database-access"],
    queryFn: ({ signal }) => api.get<DatabaseAccess>("/security/database-access/", { signal }),
  });
}

export function useScanningStatus() {
  return useQuery<ScanningStatus, ApiError>({
    queryKey: [...key, "upload-scanning"],
    queryFn: ({ signal }) => api.get<ScanningStatus>("/security/upload-scanning/", { signal }),
  });
}

export function useScanDocuments() {
  const queryClient = useQueryClient();
  return useMutation<ScanResult, ApiError, void>({
    mutationFn: () => api.post<ScanResult>("/security/upload-scanning/scan/"),
    onSettled: () => queryClient.invalidateQueries({ queryKey: [...key, "upload-scanning"] }),
  });
}

export function useSecurityStatus() {
  return useQuery<SecurityStatus, ApiError>({
    queryKey: [...key, "security-status"],
    queryFn: ({ signal }) => api.get<SecurityStatus>("/security/status/", { signal }),
  });
}

export function useConsoleAccess() {
  return useQuery<ConsoleAccess, ApiError>({
    queryKey: [...key, "console-access"],
    queryFn: ({ signal }) => api.get<ConsoleAccess>("/security/console-access/", { signal }),
  });
}

export function useConsoleRefusals() {
  return useQuery<ConsoleAccessBlock[], ApiError>({
    queryKey: [...key, "console-refusals"],
    queryFn: ({ signal }) => api.get<ConsoleAccessBlock[]>("/console-access-blocks/", { signal }),
  });
}

export function useBrowserReports() {
  return useQuery<BrowserSecurityReport[], ApiError>({
    queryKey: [...key, "browser-reports"],
    queryFn: ({ signal }) => api.get<BrowserSecurityReport[]>("/browser-security-reports/", { signal }),
  });
}

function useChange<TResult, TBody>(request: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation<TResult, ApiError, TBody>({
    mutationFn: request,
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}

export function useReviewBrowserReport(id: string) {
  return useChange((body: { version: number; note?: string }) =>
    api.post<BrowserSecurityReport>(`/browser-security-reports/${id}/review/`, body),
  );
}

export function useReviewConsoleRefusal(id: string) {
  return useChange((body: { version: number; note?: string }) =>
    api.post<ConsoleAccessBlock>(`/console-access-blocks/${id}/review/`, body),
  );
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

// --- Retention and legal hold (HIMS-COMP-006). Changes ask "confirm it's you" through the API client. ---

export function useRetention() {
  return useQuery<RetentionStatus, ApiError>({
    queryKey: [...key, "retention"],
    queryFn: ({ signal }) => api.get<RetentionStatus>("/retention/", { signal }),
  });
}

export function useRetentionRuns() {
  return useQuery<RetentionPurgeRun[], ApiError>({
    queryKey: [...key, "retention-runs"],
    queryFn: ({ signal }) => api.get<RetentionPurgeRun[]>("/retention-runs/", { signal }),
  });
}

export function useLegalHolds() {
  return useQuery<LegalHold[], ApiError>({
    queryKey: [...key, "legal-holds"],
    queryFn: ({ signal }) => api.get<LegalHold[]>("/legal-holds/", { signal }),
  });
}

export function useSetRetentionPeriod(category: string) {
  return useChange((body: { keep_days: number | null; version: number }) =>
    api.post<RetentionStatus>(`/retention/periods/${category}/`, body),
  );
}

export function useRunPurge() {
  return useChange((_: void) => api.post<RetentionPurgeRun>("/retention/run/"));
}

export function usePlaceLegalHold(idempotencyKey: string) {
  return useChange((body: LegalHoldPlaceRequest) => api.post<LegalHold>("/legal-holds/", body, { idempotencyKey }));
}

export function useReleaseLegalHold(id: string) {
  return useChange((body: { version: number; reason: string }) =>
    api.post<LegalHold>(`/legal-holds/${id}/release/`, body),
  );
}
