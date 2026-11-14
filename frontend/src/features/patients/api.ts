import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  EmergencyAccess,
  EmergencyAccessReviewRequest,
  EmergencyAccessStateEnum,
  OwnEmergencyAccess,
  PaginatedEmergencyAccess,
  PaginatedPatientHistory,
  PaginatedRestrictedOpenings,
  PaginatedPatientList,
  PatientConsent,
  PatientConsentRequest,
  PatientContact,
  PatientContactCreateRequest,
  PatientContactUpdateRequest,
  PatientDetail,
  PatientIdentifier,
  PatientIdentifierEndRequest,
  PatientIdentifierRequest,
  PatientRegisterRequest,
  PatientRegistrationOptions,
  PatientRelationship,
  PatientRelationshipCreateRequest,
  PatientRelationshipUpdateRequest,
  PatientRestrictionRequest,
  PatientUpdateRequest,
} from "../../api/types";

export const patientsKey = ["patients"] as const;
export const PAGE_SIZE = 50;

export interface PatientFilters {
  facility: string;
  /** MRN, phone, ID number or name (HIMS-PAT-002); empty: newest registrations. */
  search: string;
  sex: string;
  age: string;
}

/**
 * Newest registrations first, or a patient search (HIMS-PAT-002): at most 50 results, best match
 * first; `count` above 50 means "add more detail". Every search is audited on the server.
 */
export function usePatients(filters: PatientFilters, page: number) {
  const searching = filters.search.trim() !== "";
  const query = searching
    ? { search: filters.search.trim(), sex: filters.sex, age: filters.age, facility: filters.facility }
    : { facility: filters.facility, page, page_size: PAGE_SIZE };
  return useQuery<PaginatedPatientList, ApiError>({
    queryKey: [...patientsKey, "list", query],
    queryFn: ({ signal }) => api.get<PaginatedPatientList>("/patients/", { query, signal }),
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: !searching, // each search is an audited event; repeat it on purpose only
  });
}

/** Opening a record is audited on the server (spec 13.4). */
export function usePatient(id: string | undefined) {
  return useQuery<PatientDetail, ApiError>({
    queryKey: [...patientsKey, "detail", id],
    queryFn: ({ signal }) => api.get<PatientDetail>(`/patients/${id}/`, { signal }),
    enabled: !!id,
    refetchOnWindowFocus: false, // each load is an audited opening; refresh after changes only
  });
}

/** The record's history (HIMS-PAT-005): who opened and changed it. Viewing it is audited. */
export function usePatientHistory(id: string, page: number) {
  return useQuery<PaginatedPatientHistory, ApiError>({
    queryKey: [...patientsKey, "history", id, page],
    queryFn: ({ signal }) =>
      api.get<PaginatedPatientHistory>(`/patients/${id}/history/`, { query: { page, page_size: PAGE_SIZE }, signal }),
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false, // each load is an audited event
  });
}

export function useRegistrationOptions() {
  return useQuery<PatientRegistrationOptions, ApiError>({
    queryKey: [...patientsKey, "registration-options"],
    queryFn: ({ signal }) => api.get<PatientRegistrationOptions>("/patients/registration-options/", { signal }),
    staleTime: Infinity,
  });
}

function usePatientMutation<Body, Result>(send: (body: Body) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation<Result, ApiError, Body>({
    mutationFn: send,
    onSettled: () => queryClient.invalidateQueries({ queryKey: patientsKey }),
  });
}

export function useRegisterPatient(idempotencyKey: string) {
  return usePatientMutation<PatientRegisterRequest, PatientDetail>((body) =>
    api.post<PatientDetail>("/patients/", body, { idempotencyKey }),
  );
}

export function useUpdatePatient(id: string) {
  return usePatientMutation<PatientUpdateRequest, PatientDetail>((body) =>
    api.patch<PatientDetail>(`/patients/${id}/`, body),
  );
}

export function useAddContact(id: string, idempotencyKey: string) {
  return usePatientMutation<PatientContactCreateRequest, PatientContact>((body) =>
    api.post<PatientContact>(`/patients/${id}/contacts/`, body, { idempotencyKey }),
  );
}

export function useUpdateContact(id: string, contactId: string) {
  return usePatientMutation<PatientContactUpdateRequest, PatientContact>((body) =>
    api.patch<PatientContact>(`/patients/${id}/contacts/${contactId}/`, body),
  );
}

export function useAddRelationship(id: string, idempotencyKey: string) {
  return usePatientMutation<PatientRelationshipCreateRequest, PatientRelationship>((body) =>
    api.post<PatientRelationship>(`/patients/${id}/relationships/`, body, { idempotencyKey }),
  );
}

export function useUpdateRelationship(id: string, relationshipId: string) {
  return usePatientMutation<PatientRelationshipUpdateRequest, PatientRelationship>((body) =>
    api.patch<PatientRelationship>(`/patients/${id}/relationships/${relationshipId}/`, body),
  );
}

export function useAddIdentifier(id: string, idempotencyKey: string) {
  return usePatientMutation<PatientIdentifierRequest, PatientIdentifier>((body) =>
    api.post<PatientIdentifier>(`/patients/${id}/identifiers/`, body, { idempotencyKey }),
  );
}

export function useEndIdentifier(id: string, identifierId: string) {
  return usePatientMutation<PatientIdentifierEndRequest, PatientIdentifier>((body) =>
    api.post<PatientIdentifier>(`/patients/${id}/identifiers/${identifierId}/end/`, body),
  );
}

export function useRecordConsent(id: string, idempotencyKey: string) {
  return usePatientMutation<PatientConsentRequest, PatientConsent>((body) =>
    api.post<PatientConsent>(`/patients/${id}/consents/`, body, { idempotencyKey }),
  );
}

// --- Restricted records and emergency access (HIMS-PAT-006) ----------------------------------

/** Medical records restrict a record (VIP, staff, other) or lift it, with a reason. */
export function useSetRestriction(id: string) {
  return usePatientMutation<PatientRestrictionRequest, PatientDetail>((body) =>
    api.post<PatientDetail>(`/patients/${id}/restriction/`, body),
  );
}

/** Emergency access (D14): 4 hours, with a reason; medical records are told and review it. */
export function useOpenEmergencyAccess(id: string) {
  return usePatientMutation<{ reason: string }, OwnEmergencyAccess>((body) =>
    api.post<OwnEmergencyAccess>(`/patients/${id}/emergency-access/`, body),
  );
}

export function useEndEmergencyAccess(id: string) {
  return usePatientMutation<void, OwnEmergencyAccess>(() =>
    api.post<OwnEmergencyAccess>(`/patients/${id}/emergency-access/end/`, {}),
  );
}

export const emergencyAccessKey = ["patient-emergency-access"] as const;

export function useEmergencyAccessList(state: EmergencyAccessStateEnum, page: number) {
  return useQuery<PaginatedEmergencyAccess, ApiError>({
    queryKey: [...emergencyAccessKey, state, page],
    queryFn: ({ signal }) =>
      api.get<PaginatedEmergencyAccess>("/patient-emergency-access/", {
        query: { state, page, page_size: PAGE_SIZE },
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

export function useReviewEmergencyAccess(accessId: string) {
  const queryClient = useQueryClient();
  return useMutation<EmergencyAccess, ApiError, EmergencyAccessReviewRequest>({
    mutationFn: (body) => api.post<EmergencyAccess>(`/patient-emergency-access/${accessId}/review/`, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: emergencyAccessKey }),
  });
}

/** Who opened restricted records (D23). Viewing the list is audited. */
export function useRestrictedOpenings(days: number, page: number) {
  return useQuery<PaginatedRestrictedOpenings, ApiError>({
    queryKey: [...emergencyAccessKey, "openings", days, page],
    queryFn: ({ signal }) =>
      api.get<PaginatedRestrictedOpenings>("/patients/restricted-openings/", {
        query: { days, page, page_size: PAGE_SIZE },
        signal,
      }),
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false, // each load is an audited event
  });
}
