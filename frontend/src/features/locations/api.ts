import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  Bed,
  BedStatusChangeRequest,
  FacilityLocations,
} from "../../api/types";

export const locationsKey = ["locations"] as const;

export function useFacilityLocations(facilityId: string | undefined) {
  return useQuery<FacilityLocations, ApiError>({
    queryKey: [...locationsKey, facilityId],
    queryFn: ({ signal }) =>
      api.get<FacilityLocations>(`/facilities/${facilityId}/locations/`, {
        signal,
      }),
    enabled: !!facilityId,
  });
}

export function useChangeBedStatus(bedId: string, idempotencyKey: string) {
  const queryClient = useQueryClient();
  return useMutation<Bed, ApiError, BedStatusChangeRequest>({
    mutationFn: (body) =>
      api.post<Bed>(`/beds/${bedId}/status/`, body, { idempotencyKey }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: locationsKey }),
  });
}
