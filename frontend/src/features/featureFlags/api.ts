import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type { EffectiveFeatures, FeatureChangeRequest, FeatureState } from "../../api/types";

export const featuresKey = ["features"] as const;

export const FEATURE = {
  selfServicePasswordReset: "auth.self_service_password_reset",
  twoFactorForEveryone: "auth.two_factor_for_everyone",
  locations: "locations.module",
} as const;

export function useFeatureStates(facilityId: string | undefined) {
  return useQuery<FeatureState[], ApiError>({
    queryKey: [...featuresKey, "states", facilityId ?? "hospital"],
    queryFn: ({ signal }) =>
      api.get<FeatureState[]>("/features/", { query: { facility: facilityId }, signal }),
  });
}

/** What is on right now. Before sign-in it only contains public features. */
export function useEffectiveFeatures() {
  return useQuery<EffectiveFeatures, ApiError>({
    queryKey: [...featuresKey, "effective"],
    queryFn: ({ signal }) => api.get<EffectiveFeatures>("/features/effective/", { signal }),
  });
}

/**
 * Whether a feature is on (for the facility, if given). Unknown or still loading counts as on:
 * hiding things is only a convenience, the server enforces every feature itself.
 */
export function useFeatureOn(key: string, facilityId?: string): boolean {
  const { data } = useEffectiveFeatures();
  // Optional chaining throughout: a missing or unexpected answer must never break a page.
  const facilityValue = facilityId ? data?.facilities?.[facilityId]?.[key] : undefined;
  return facilityValue ?? data?.hospital?.[key] ?? true;
}

export function useChangeFeature(key: string, idempotencyKey: string) {
  const queryClient = useQueryClient();
  return useMutation<FeatureState, ApiError, FeatureChangeRequest>({
    mutationFn: (body) =>
      api.post<FeatureState>(`/features/${key}/change/`, body, { idempotencyKey }),
    // Refresh after a refusal too (e.g. someone else changed it first).
    onSettled: () => queryClient.invalidateQueries({ queryKey: featuresKey }),
  });
}
