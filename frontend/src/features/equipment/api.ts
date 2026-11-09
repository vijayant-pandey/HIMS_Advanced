import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  Equipment,
  EquipmentCreateRequest,
  EquipmentServiceRecord,
  EquipmentStatusRequest,
  PaginatedEquipmentList,
  PatchedEquipmentUpdateRequest,
  ServiceRecordCreateRequest,
} from "../../api/types";

export const equipmentKey = ["equipment"] as const;
export const PAGE_SIZE = 100;

export interface EquipmentFilters {
  facility: string;
  status: string;
  category: string;
  due: string;
  search: string;
}

export function useEquipmentList(filters: EquipmentFilters, page: number) {
  return useQuery<PaginatedEquipmentList, ApiError>({
    queryKey: [...equipmentKey, filters, page],
    queryFn: ({ signal }) =>
      api.get<PaginatedEquipmentList>("/equipment/", {
        query: { ...filters, page, page_size: PAGE_SIZE },
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

export function useEquipmentHistory(id: string) {
  return useQuery<EquipmentServiceRecord[], ApiError>({
    queryKey: [...equipmentKey, id, "history"],
    queryFn: ({ signal }) => api.get<EquipmentServiceRecord[]>(`/equipment/${id}/history/`, { signal }),
  });
}

function useEquipmentMutation<Body, Result = Equipment>(send: (body: Body) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation<Result, ApiError, Body>({
    mutationFn: send,
    onSettled: () => queryClient.invalidateQueries({ queryKey: equipmentKey }),
  });
}

export function useCreateEquipment(idempotencyKey: string) {
  return useEquipmentMutation<EquipmentCreateRequest>((body) =>
    api.post<Equipment>("/equipment/", body, { idempotencyKey }),
  );
}

export function useUpdateEquipment(id: string) {
  return useEquipmentMutation<PatchedEquipmentUpdateRequest>((body) =>
    api.patch<Equipment>(`/equipment/${id}/`, body),
  );
}

export function useChangeEquipmentStatus(id: string, idempotencyKey: string) {
  return useEquipmentMutation<EquipmentStatusRequest>((body) =>
    api.post<Equipment>(`/equipment/${id}/status/`, body, { idempotencyKey }),
  );
}

export function useRecordVisit(id: string, idempotencyKey: string) {
  return useEquipmentMutation<ServiceRecordCreateRequest, EquipmentServiceRecord>((body) =>
    api.post<EquipmentServiceRecord>(`/equipment/${id}/service-records/`, body, { idempotencyKey }),
  );
}
