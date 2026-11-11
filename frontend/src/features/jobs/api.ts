import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type { OutboxEvent, OutboxHealth } from "../../api/types";

const key = ["background-jobs"] as const;

export type Show = "attention" | "failed" | "waiting" | "dismissed";

export function useJobHealth() {
  const queryClient = useQueryClient();
  return useQuery<OutboxHealth, ApiError>({
    queryKey: [...key, "health"],
    queryFn: ({ queryKey, signal }) =>
      api.get<OutboxHealth>("/background-jobs/health/", {
        signal,
        background: queryClient.getQueryData(queryKey) !== undefined, // a timed refresh
      }),
    refetchInterval: 30_000,
  });
}

export function useJobEvents(show: Show) {
  return useQuery<OutboxEvent[], ApiError>({
    queryKey: [...key, "events", show],
    queryFn: ({ signal }) => api.get<OutboxEvent[]>(`/background-jobs/?show=${show}`, { signal }),
  });
}

/** "send-again" puts a failed event back in the queue; "dismiss" closes it for good. Both need a reason. */
export function useDecideEvent(id: string, decision: "send-again" | "dismiss") {
  const queryClient = useQueryClient();
  return useMutation<OutboxEvent, ApiError, { reason: string }>({
    mutationFn: (body) => api.post<OutboxEvent>(`/background-jobs/${id}/${decision}/`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}
