import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { API_BASE, ApiError, api } from "../../api/client";
import type {
  AccessReview,
  AccessReviewDecideRequest,
  AccessReviewItem,
  AccessReviewSchedule,
  AccessReviewStartRequest,
} from "../../api/types";
import { accessKey } from "./api";

// Under the access key: removing access in a review also changes the Access page.
const reviewsKey = [...accessKey, "reviews"] as const;

export function useAccessReviews() {
  return useQuery<AccessReview[], ApiError>({
    queryKey: [...reviewsKey, "list"],
    queryFn: ({ signal }) => api.get<AccessReview[]>("/access-reviews/", { signal }),
  });
}

export function useAccessReviewSchedule() {
  return useQuery<AccessReviewSchedule, ApiError>({
    queryKey: [...reviewsKey, "schedule"],
    queryFn: ({ signal }) => api.get<AccessReviewSchedule>("/access-reviews/schedule/", { signal }),
  });
}

export function useAccessReview(id: string) {
  return useQuery<AccessReview, ApiError>({
    queryKey: [...reviewsKey, id],
    queryFn: ({ signal }) => api.get<AccessReview>(`/access-reviews/${id}/`, { signal }),
  });
}

export function useAccessReviewItems(id: string, filters: { decision: string; search: string }) {
  return useQuery<AccessReviewItem[], ApiError>({
    queryKey: [...reviewsKey, id, "items", filters],
    queryFn: ({ signal }) =>
      api.get<AccessReviewItem[]>(`/access-reviews/${id}/items/`, {
        query: { decision: filters.decision, search: filters.search },
        signal,
      }),
  });
}

function useReviewMutation<TResult, TBody>(request: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation<TResult, ApiError, TBody>({
    mutationFn: request,
    // Refresh after a refusal too (e.g. another reviewer decided first).
    onSettled: () => queryClient.invalidateQueries({ queryKey: accessKey }),
  });
}

export function useStartAccessReview(idempotencyKey: string) {
  return useReviewMutation<AccessReview, AccessReviewStartRequest>((body) =>
    api.post<AccessReview>("/access-reviews/", body, { idempotencyKey }),
  );
}

export function useDecideAccess(reviewId: string) {
  return useReviewMutation<AccessReviewItem[], AccessReviewDecideRequest>((body) =>
    api.post<AccessReviewItem[]>(`/access-reviews/${reviewId}/decide/`, body),
  );
}

export function useCompleteAccessReview(reviewId: string) {
  return useReviewMutation<AccessReview, { version: number; notes: string }>((body) =>
    api.post<AccessReview>(`/access-reviews/${reviewId}/complete/`, body),
  );
}

export function useCancelAccessReview(reviewId: string) {
  return useReviewMutation<AccessReview, { version: number; reason: string }>((body) =>
    api.post<AccessReview>(`/access-reviews/${reviewId}/cancel/`, body),
  );
}

/** Link that downloads the review as CSV (signed-in session; recorded in the audit log). */
export function reviewExportUrl(id: string): string {
  return `${API_BASE}/access-reviews/${id}/export/`;
}
