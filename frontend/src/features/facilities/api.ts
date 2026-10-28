import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  Department,
  DepartmentCreateRequest,
  DepartmentUpdateRequest,
  Facility,
  FacilityCreateRequest,
  FacilityUpdateRequest,
  PaginatedDepartmentList,
  PaginatedFacilityList,
} from "../../api/types";

export const facilitiesKey = ["facilities"] as const;
export const departmentsKey = ["departments"] as const;

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

/** Departments, optionally for one facility and/or status ("active" / "inactive"). */
export function useDepartmentList(facilityId?: string, status?: string) {
  return useQuery<PaginatedDepartmentList, ApiError>({
    queryKey: [...departmentsKey, "list", { facilityId, status }],
    queryFn: ({ signal }) =>
      api.get<PaginatedDepartmentList>("/departments/", {
        query: { facility: facilityId, status, page_size: 100 },
        signal,
      }),
  });
}

/** Facilities and departments change together (counts, status), so refresh both. */
function useRefreshSetup() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: facilitiesKey });
    void queryClient.invalidateQueries({ queryKey: departmentsKey });
  };
}

export function useUpdateFacility(id: string) {
  const refresh = useRefreshSetup();
  return useMutation<Facility, ApiError, FacilityUpdateRequest>({
    mutationFn: (body) => api.patch<Facility>(`/facilities/${id}/`, body),
    // Refresh after a refusal too (e.g. someone else changed it first).
    onSettled: refresh,
  });
}

export function useCreateDepartment(idempotencyKey: string) {
  const refresh = useRefreshSetup();
  return useMutation<Department, ApiError, DepartmentCreateRequest>({
    mutationFn: (body) => api.post<Department>("/departments/", body, { idempotencyKey }),
    onSuccess: refresh,
  });
}

export function useUpdateDepartment(id: string) {
  const refresh = useRefreshSetup();
  return useMutation<Department, ApiError, DepartmentUpdateRequest>({
    mutationFn: (body) => api.patch<Department>(`/departments/${id}/`, body),
    onSettled: refresh,
  });
}
