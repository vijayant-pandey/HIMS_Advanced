import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  AccessDelegation,
  AccessDelegationCreated,
  AccessDelegationCreateRequest,
  DelegableAccess,
} from "../../api/types";
import { accessKey } from "./api";

// Under the access key: arranging or ending cover changes people's access everywhere.
const coverKey = [...accessKey, "cover"] as const;

export type CoverFilter = "current" | "past";

export function useCoverArrangements(status: CoverFilter) {
  return useQuery<AccessDelegation[], ApiError>({
    queryKey: [...coverKey, "list", status],
    queryFn: ({ signal }) => api.get<AccessDelegation[]>("/access-delegations/", { query: { status }, signal }),
  });
}

/** Cover the signed-in person is part of (covering or covered). */
export function useMyCover() {
  return useQuery<AccessDelegation[], ApiError>({
    queryKey: [...coverKey, "mine"],
    queryFn: ({ signal }) => api.get<AccessDelegation[]>("/my-delegations/", { signal }),
  });
}

/** What a person can lend (their own current access) and why some cannot be lent. */
export function useDelegableAccess(userId: string) {
  return useQuery<DelegableAccess[], ApiError>({
    queryKey: [...coverKey, "delegable", userId],
    queryFn: ({ signal }) =>
      api.get<DelegableAccess[]>("/access-delegations/delegable/", { query: { user: userId }, signal }),
    enabled: !!userId,
  });
}

export function useArrangeCover(idempotencyKey: string) {
  const queryClient = useQueryClient();
  return useMutation<AccessDelegationCreated, ApiError, AccessDelegationCreateRequest>({
    mutationFn: (body) => api.post<AccessDelegationCreated>("/access-delegations/", body, { idempotencyKey }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: accessKey }),
  });
}

export function useEndCover(id: string) {
  const queryClient = useQueryClient();
  return useMutation<AccessDelegation, ApiError, { version: number; reason: string }>({
    mutationFn: (body) => api.post<AccessDelegation>(`/access-delegations/${id}/end/`, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: accessKey }),
  });
}
