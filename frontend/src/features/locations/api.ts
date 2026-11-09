import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  Bed,
  BedBoard,
  BedHistory,
  BedStatusChangeRequest,
  BulkBedsRequest,
  FacilityLocations,
  PaginatedDepartmentList,
} from "../../api/types";

export const locationsKey = ["locations"] as const;

/** The five location levels and their API collections. */
export type LocationKind = "building" | "floor" | "ward" | "room" | "bed";

const COLLECTION: Record<LocationKind, string> = {
  building: "buildings",
  floor: "floors",
  ward: "wards",
  room: "rooms",
  bed: "beds",
};

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

export function useDepartments(facilityId: string | undefined) {
  return useQuery<PaginatedDepartmentList, ApiError>({
    queryKey: ["departments", facilityId],
    queryFn: ({ signal }) =>
      api.get<PaginatedDepartmentList>("/departments/", {
        query: { facility: facilityId, page_size: 100 },
        signal,
      }),
    enabled: !!facilityId,
  });
}

/** How often the bed board asks again (HIMS-FAC-008); also on returning to the tab. */
export const BOARD_REFRESH_MS = 30_000;

/** The bed board for one facility (default: the first one the person can see). */
export function useBedBoard(facilityId: string | undefined) {
  return useQuery<BedBoard, ApiError>({
    queryKey: [...locationsKey, "board", facilityId ?? "first"],
    queryFn: ({ signal }) =>
      api.get<BedBoard>("/bed-board/", {
        query: facilityId ? { facility: facilityId } : undefined,
        signal,
      }),
    refetchInterval: BOARD_REFRESH_MS,
    refetchOnWindowFocus: true,
  });
}

/** A bed's last status changes: from, to, why, who and when. */
export function useBedHistory(bedId: string) {
  return useQuery<BedHistory[], ApiError>({
    queryKey: [...locationsKey, "history", bedId],
    queryFn: ({ signal }) => api.get<BedHistory[]>(`/beds/${bedId}/history/`, { signal }),
  });
}

function useInvalidateLocations() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: locationsKey });
}

export function useChangeBedStatus(bedId: string, idempotencyKey: string) {
  const invalidate = useInvalidateLocations();
  return useMutation<Bed, ApiError, BedStatusChangeRequest>({
    mutationFn: (body) =>
      api.post<Bed>(`/beds/${bedId}/status/`, body, { idempotencyKey }),
    onSuccess: invalidate,
  });
}

/** Create one building, floor, ward, room or bed. */
export function useCreateLocation(kind: LocationKind, idempotencyKey: string) {
  const invalidate = useInvalidateLocations();
  return useMutation<unknown, ApiError, Record<string, unknown>>({
    mutationFn: (body) => api.post(`/${COLLECTION[kind]}/`, body, { idempotencyKey }),
    onSuccess: invalidate,
  });
}

/** Change one building, floor, ward, room or bed (send its current `version`). */
export function useUpdateLocation(kind: LocationKind, id: string) {
  const invalidate = useInvalidateLocations();
  return useMutation<unknown, ApiError, Record<string, unknown>>({
    mutationFn: (body) => api.patch(`/${COLLECTION[kind]}/${id}/`, body),
    // Refresh after a refusal too (e.g. someone else changed it): reopening shows the latest copy.
    onSettled: invalidate,
  });
}

export function useBulkBeds(idempotencyKey: string) {
  const invalidate = useInvalidateLocations();
  return useMutation<Bed[], ApiError, BulkBedsRequest>({
    mutationFn: (body) => api.post<Bed[]>("/beds/bulk/", body, { idempotencyKey }),
    onSuccess: invalidate,
  });
}
