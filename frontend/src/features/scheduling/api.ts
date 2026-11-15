import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  AddExceptionRequest,
  AddSessionsRequest,
  AddedException,
  CancelExceptionRequest,
  ChangeSessionRequest,
  DepartmentWeek,
  DoctorDay,
  DoctorSchedule,
  EndSessionRequest,
  MyOpdWeek,
  ScheduleException,
} from "../../api/types";

// One key for everything here: a session or an exception changes every schedule screen.
export const scheduleKey = ["doctor-schedules"] as const;

export function useDepartmentWeek(department: string, start: string) {
  return useQuery<DepartmentWeek, ApiError>({
    queryKey: [...scheduleKey, "week", department, start],
    queryFn: ({ signal }) =>
      api.get<DepartmentWeek>("/doctor-schedules/week/", { query: { department, start }, signal }),
    enabled: !!department,
  });
}

export function useDoctorDay(doctor: string, date: string) {
  return useQuery<DoctorDay, ApiError>({
    queryKey: [...scheduleKey, "day", doctor, date],
    queryFn: ({ signal }) => api.get<DoctorDay>("/availability/", { query: { doctor, date }, signal }),
    enabled: !!doctor && !!date,
  });
}

export function useMyOpdWeek(start: string) {
  return useQuery<MyOpdWeek, ApiError>({
    queryKey: [...scheduleKey, "mine", start],
    queryFn: ({ signal }) => api.get<MyOpdWeek>("/my-opd-sessions/", { query: { start }, signal }),
  });
}

function useScheduleMutation<TResult, TBody>(send: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation<TResult, ApiError, TBody>({
    mutationFn: send,
    onSettled: () => queryClient.invalidateQueries({ queryKey: scheduleKey }),
  });
}

export const useAddSessions = (idempotencyKey: string) =>
  useScheduleMutation((body: AddSessionsRequest) =>
    api.post<DoctorSchedule[]>("/doctor-schedules/", body, { idempotencyKey }),
  );

export const useChangeSession = (id: string) =>
  useScheduleMutation((body: ChangeSessionRequest) => api.patch<DoctorSchedule>(`/doctor-schedules/${id}/`, body));

export const useEndSession = (id: string) =>
  useScheduleMutation((body: EndSessionRequest) => api.post<DoctorSchedule>(`/doctor-schedules/${id}/end/`, body));

export const useAddException = (idempotencyKey: string) =>
  useScheduleMutation((body: AddExceptionRequest) =>
    api.post<AddedException>("/schedule-exceptions/", body, { idempotencyKey }),
  );

export const useCancelException = (id: string) =>
  useScheduleMutation((body: CancelExceptionRequest) =>
    api.post<ScheduleException>(`/schedule-exceptions/${id}/cancel/`, body),
  );
