import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  AddShiftsRequest,
  AddShiftsResult,
  CopyWeekRequest,
  DepartmentBalances,
  LeaveAdjustment,
  LeaveAdjustmentCreateRequest,
  LeaveCreateRequest,
  LeaveDecisionRequest,
  LeaveEntitlement,
  LeaveRequest,
  MySchedule,
  RotaNow,
  RotaWeek,
  Shift,
  ShiftType,
  ShiftTypeCreateRequest,
  ShiftTypeUpdateRequest,
  StaffingRequirement,
} from "../../api/types";

// One key for everything here: a shift or leave change can show up on every rota screen.
export const rotaKey = ["rota"] as const;

export function useShiftTypes(activeOnly = false) {
  return useQuery<ShiftType[], ApiError>({
    queryKey: [...rotaKey, "shift-types", activeOnly],
    queryFn: ({ signal }) =>
      api.get<ShiftType[]>("/shift-types/", { query: activeOnly ? { active: "true" } : {}, signal }),
  });
}

export function useRotaWeek(department: string, start: string) {
  return useQuery<RotaWeek, ApiError>({
    queryKey: [...rotaKey, "week", department, start],
    queryFn: ({ signal }) => api.get<RotaWeek>("/rota/", { query: { department, start }, signal }),
    enabled: !!department,
  });
}

export function useRotaNow() {
  const queryClient = useQueryClient();
  return useQuery<RotaNow, ApiError>({
    queryKey: [...rotaKey, "now"],
    queryFn: ({ queryKey, signal }) =>
      api.get<RotaNow>("/rota/now/", {
        signal,
        background: queryClient.getQueryData(queryKey) !== undefined, // a timed refresh
      }),
    refetchInterval: 5 * 60_000,
  });
}

export function useLeaveRequests(status: string) {
  return useQuery<LeaveRequest[], ApiError>({
    queryKey: [...rotaKey, "leave", status],
    queryFn: ({ signal }) => api.get<LeaveRequest[]>("/leave-requests/", { query: { status }, signal }),
  });
}

export function useMySchedule() {
  return useQuery<MySchedule, ApiError>({
    queryKey: [...rotaKey, "mine"],
    queryFn: ({ signal }) => api.get<MySchedule>("/my-schedule/", { signal }),
  });
}

function useRotaMutation<TResult, TBody>(send: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation<TResult, ApiError, TBody>({
    mutationFn: send,
    onSettled: () => queryClient.invalidateQueries({ queryKey: rotaKey }),
  });
}

export const useAddShifts = (idempotencyKey: string) =>
  useRotaMutation((body: AddShiftsRequest) => api.post<AddShiftsResult>("/shifts/", body, { idempotencyKey }));

export const useCopyWeek = (idempotencyKey: string) =>
  useRotaMutation((body: CopyWeekRequest) =>
    api.post<AddShiftsResult>("/shifts/copy-week/", body, { idempotencyKey }),
  );

export const useCancelShift = (id: string) =>
  useRotaMutation((body: { version: number; reason: string }) => api.post<Shift>(`/shifts/${id}/cancel/`, body));

export const useCreateShiftType = (idempotencyKey: string) =>
  useRotaMutation((body: ShiftTypeCreateRequest) => api.post<ShiftType>("/shift-types/", body, { idempotencyKey }));

export const useUpdateShiftType = (id: string) =>
  useRotaMutation((body: ShiftTypeUpdateRequest) => api.patch<ShiftType>(`/shift-types/${id}/`, body));

/** Your own leave (anyone with a staff record). */
export const useAskForLeave = (idempotencyKey: string) =>
  useRotaMutation((body: LeaveCreateRequest) =>
    api.post<LeaveRequest>("/my-leave-requests/", body, { idempotencyKey }),
  );

export const useWithdrawLeave = (id: string) =>
  useRotaMutation((body: { version: number; reason: string }) =>
    api.post<LeaveRequest>(`/my-leave-requests/${id}/cancel/`, body),
  );

/** Approvers: record leave for someone. */
export const useRecordLeave = (idempotencyKey: string) =>
  useRotaMutation((body: LeaveCreateRequest) => api.post<LeaveRequest>("/leave-requests/", body, { idempotencyKey }));

export function useStaffingRequirements(department: string) {
  return useQuery<StaffingRequirement[], ApiError>({
    queryKey: [...rotaKey, "minimums", department],
    queryFn: ({ signal }) =>
      api.get<StaffingRequirement[]>("/staffing-requirements/", { query: { department }, signal }),
  });
}

export const useSaveRequirement = (id: string | undefined, idempotencyKey: string) =>
  useRotaMutation((body: Record<string, unknown>) =>
    id
      ? api.patch<StaffingRequirement>(`/staffing-requirements/${id}/`, body)
      : api.post<StaffingRequirement>("/staffing-requirements/", body, { idempotencyKey }),
  );

export function useLeaveBalances(department: string) {
  return useQuery<DepartmentBalances, ApiError>({
    queryKey: [...rotaKey, "balances", department],
    queryFn: ({ signal }) => api.get<DepartmentBalances>("/leave-balances/", { query: { department }, signal }),
    enabled: !!department,
  });
}

export function useLeaveEntitlements() {
  return useQuery<LeaveEntitlement[], ApiError>({
    queryKey: [...rotaKey, "entitlements"],
    queryFn: ({ signal }) => api.get<LeaveEntitlement[]>("/leave-entitlements/", { signal }),
  });
}

export const useSaveEntitlement = (id: string | undefined, idempotencyKey: string) =>
  useRotaMutation((body: Record<string, unknown>) =>
    id
      ? api.patch<LeaveEntitlement>(`/leave-entitlements/${id}/`, body)
      : api.post<LeaveEntitlement>("/leave-entitlements/", body, { idempotencyKey }),
  );

export function useAdjustments(person: string) {
  return useQuery<LeaveAdjustment[], ApiError>({
    queryKey: [...rotaKey, "adjustments", person],
    queryFn: ({ signal }) => api.get<LeaveAdjustment[]>("/leave-adjustments/", { query: { person }, signal }),
  });
}

export const useAdjustBalance = (idempotencyKey: string) =>
  useRotaMutation((body: LeaveAdjustmentCreateRequest) =>
    api.post<LeaveAdjustment>("/leave-adjustments/", body, { idempotencyKey }),
  );

export type LeaveDecision = "approve" | "reject" | "cancel";

export const useDecideLeave = (id: string, decision: LeaveDecision) =>
  useRotaMutation((body: Pick<LeaveDecisionRequest, "version" | "note" | "cancel_shifts"> & { allow_over_balance?: boolean } | { version: number; reason: string }) =>
    api.post<LeaveRequest>(`/leave-requests/${id}/${decision}/`, body),
  );
