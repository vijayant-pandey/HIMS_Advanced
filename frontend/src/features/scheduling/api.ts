import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  AddExceptionRequest,
  AddSessionsRequest,
  AddedException,
  Appointment,
  BookRequest,
  CancelAppointmentRequest,
  CancelExceptionRequest,
  ChangeSessionRequest,
  DepartmentDay,
  DepartmentWeek,
  DoctorDay,
  DoctorSchedule,
  EndSessionRequest,
  MyOpdWeek,
  PaginatedPatientList,
  RescheduleRequest,
  ScheduleException,
  ToRebook,
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
    onSettled: () => {
      // A session change can put booked patients on the "To move" list, and a booking fills a slot.
      void queryClient.invalidateQueries({ queryKey: scheduleKey });
      void queryClient.invalidateQueries({ queryKey: appointmentsKey });
    },
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

// --- Appointments (HIMS-OPD-002) ----------------------------------------------------------------

export const appointmentsKey = ["appointments"] as const;

/** One department's doctors on one day: their sessions' slots, free or booked, and the appointments. */
export function useDepartmentDay(department: string, date: string) {
  return useQuery<DepartmentDay, ApiError>({
    queryKey: [...appointmentsKey, "day", department, date],
    queryFn: ({ signal }) => api.get<DepartmentDay>("/appointments/day/", { query: { department, date }, signal }),
    enabled: !!department && !!date,
  });
}

/** Booked patients whose doctor is now away or whose session is off. */
export function useToRebook(department: string) {
  return useQuery<ToRebook[], ApiError>({
    queryKey: [...appointmentsKey, "to-rebook", department],
    queryFn: ({ signal }) => api.get<ToRebook[]>("/appointments/to-rebook/", { query: { department }, signal }),
    enabled: !!department,
  });
}

/** A patient's booked appointments still to come (the chart's Overview). */
export function usePatientAppointments(patient: string, enabled = true) {
  return useQuery<Appointment[], ApiError>({
    queryKey: [...appointmentsKey, "patient", patient],
    queryFn: ({ signal }) =>
      api.get<Appointment[]>("/appointments/", { query: { patient_id: patient, upcoming: "true" }, signal }),
    enabled: enabled && !!patient,
  });
}

export const useBook = (idempotencyKey: string) =>
  useScheduleMutation((body: BookRequest) => api.post<Appointment>("/appointments/", body, { idempotencyKey }));

export const useReschedule = (id: string) =>
  useScheduleMutation((body: RescheduleRequest) => api.post<Appointment>(`/appointments/${id}/reschedule/`, body));

export const useCancelAppointment = (id: string) =>
  useScheduleMutation((body: CancelAppointmentRequest) =>
    api.post<Appointment>(`/appointments/${id}/cancel/`, body),
  );

/** The patient search (HIMS-PAT-002) for whom to book: only when asked (each search is audited). */
export function usePatientSearch(search: string) {
  return useQuery<PaginatedPatientList, ApiError>({
    queryKey: ["patients", "list", { search, for: "booking" }],
    queryFn: ({ signal }) => api.get<PaginatedPatientList>("/patients/", { query: { search }, signal }),
    enabled: search.trim() !== "",
    refetchOnWindowFocus: false,
  });
}
