import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type { PerformanceCheck, PerformanceCheckDetail, PerformanceStatus } from "../../api/types";

const performanceKey = ["performance"] as const;

export function usePerformanceStatus() {
  return useQuery<PerformanceStatus, ApiError>({
    queryKey: [...performanceKey, "status"],
    queryFn: ({ signal }) => api.get<PerformanceStatus>("/performance-checks/status/", { signal }),
  });
}

export function usePerformanceChecks() {
  return useQuery<PerformanceCheck[], ApiError>({
    queryKey: [...performanceKey, "checks"],
    queryFn: ({ signal }) => api.get<PerformanceCheck[]>("/performance-checks/", { signal }),
  });
}

export function usePerformanceCheck(id: string) {
  return useQuery<PerformanceCheckDetail, ApiError>({
    queryKey: [...performanceKey, "checks", id],
    queryFn: ({ signal }) => api.get<PerformanceCheckDetail>(`/performance-checks/${id}/`, { signal }),
  });
}

/** Runs the index check on this hospital's database now (reads only). */
export function useRunIndexCheck() {
  const queryClient = useQueryClient();
  return useMutation<PerformanceCheckDetail, ApiError, void>({
    mutationFn: () => api.post<PerformanceCheckDetail>("/performance-checks/", {}),
    onSettled: () => queryClient.invalidateQueries({ queryKey: performanceKey }),
  });
}
