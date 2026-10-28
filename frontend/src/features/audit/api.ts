import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { API_BASE, ApiError, api } from "../../api/client";
import type { AuditAction, PaginatedAuditEventList } from "../../api/types";

export interface AuditFilters {
  request_id: string;
  person: string;
  category: string;
  action: string;
  outcome: string;
  date_from: string;
  date_to: string;
}

export const EMPTY_FILTERS: AuditFilters = {
  request_id: "",
  person: "",
  category: "",
  action: "",
  outcome: "",
  date_from: "",
  date_to: "",
};

export const PAGE_SIZE = 50;

function query(filters: AuditFilters) {
  return Object.fromEntries(
    Object.entries(filters)
      .map(([key, value]) => [key, value.trim()])
      .filter(([, value]) => value !== ""),
  ) as Record<string, string>;
}

/**
 * Runs only when `filters` is set (after "Search"), because every search is itself written to
 * the audit log; searching on every keystroke would flood it.
 */
export function useAuditSearch(filters: AuditFilters | null, page: number) {
  return useQuery<PaginatedAuditEventList, ApiError>({
    queryKey: ["audit", filters, page],
    queryFn: ({ signal }) =>
      api.get<PaginatedAuditEventList>("/audit-events/", {
        query: { ...query(filters!), page, page_size: PAGE_SIZE },
        signal,
      }),
    enabled: filters !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity, // re-run only when the auditor asks
  });
}

export function useAuditActions() {
  return useQuery<AuditAction[], ApiError>({
    queryKey: ["audit", "actions"],
    queryFn: ({ signal }) => api.get<AuditAction[]>("/audit-events/actions/", { signal }),
    staleTime: Infinity,
  });
}

/** Link that downloads the matching events as CSV (signed-in session; recorded as an export). */
export function exportUrl(filters: AuditFilters): string {
  const params = new URLSearchParams(query(filters)).toString();
  return `${API_BASE}/audit-events/export/${params ? `?${params}` : ""}`;
}
