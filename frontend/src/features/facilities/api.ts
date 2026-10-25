import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type { Facility, FacilityCreateRequest, PaginatedFacilityList } from "../../api/types";

export const facilitiesKey = ["facilities"] as const;

export function useFacilities(page = 1) {
  return useQuery<PaginatedFacilityList, ApiError>({
    queryKey: [...facilitiesKey, { page }],
    queryFn: ({ signal }) =>
      api.get<PaginatedFacilityList>("/facilities/", { query: { page }, signal }),
  });
}

export function useCreateFacility(idempotencyKey: string) {
  const queryClient = useQueryClient();
  return useMutation<Facility, ApiError, FacilityCreateRequest>({
    mutationFn: (body) => api.post<Facility>("/facilities/", body, { idempotencyKey }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: facilitiesKey }),
  });
}
