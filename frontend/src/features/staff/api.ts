import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { API_BASE, ApiError, api } from "../../api/client";
import type {
  CredentialVerificationRequest,
  Designation,
  EndAssignmentRequest,
  ExpiringCredential,
  InvitationSent,
  PaginatedDepartmentList,
  PaginatedStaffMemberList,
  QualificationType,
  Specialty,
  StaffCredential,
  StaffCredentialRequest,
  StaffDepartmentAssignment,
  StaffDepartmentAssignmentRequest,
  StaffDocument,
  StaffMember,
  StaffMemberCreateRequest,
  StaffMemberDetail,
  StaffMemberUpdateRequest,
  StaffQualification,
  StaffQualificationRequest,
} from "../../api/types";

export const staffKey = ["staff"] as const;

export function useStaff(search: string, employmentStatus = "", page = 1, department = "") {
  return useQuery<PaginatedStaffMemberList, ApiError>({
    queryKey: [...staffKey, "list", { search, employmentStatus, page, department }],
    queryFn: ({ signal }) =>
      api.get<PaginatedStaffMemberList>("/staff/", {
        query: { search, employment_status: employmentStatus, page, department },
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

export function useStaffMember(id: string | undefined) {
  return useQuery<StaffMemberDetail, ApiError>({
    queryKey: [...staffKey, "detail", id],
    queryFn: ({ signal }) => api.get<StaffMemberDetail>(`/staff/${id}/`, { signal }),
    enabled: !!id,
  });
}

// --- Catalogs (rarely change: cached for the session) ----------------------------------------

const CATALOG = { staleTime: Infinity } as const;

export function useDesignations(country: string | undefined) {
  return useQuery<Designation[], ApiError>({
    queryKey: ["catalog", "designations", country],
    queryFn: ({ signal }) =>
      api.get<Designation[]>("/designations/", { query: { country }, signal }),
    ...CATALOG,
  });
}

export function useSpecialties() {
  return useQuery<Specialty[], ApiError>({
    queryKey: ["catalog", "specialties"],
    queryFn: ({ signal }) => api.get<Specialty[]>("/specialties/", { signal }),
    ...CATALOG,
  });
}

export function useQualificationTypes() {
  return useQuery<QualificationType[], ApiError>({
    queryKey: ["catalog", "qualification-types"],
    queryFn: ({ signal }) => api.get<QualificationType[]>("/qualification-types/", { signal }),
    ...CATALOG,
  });
}

export function useAllDepartments() {
  return useQuery<PaginatedDepartmentList, ApiError>({
    queryKey: ["departments", "all"],
    queryFn: ({ signal }) =>
      api.get<PaginatedDepartmentList>("/departments/", { query: { page_size: 100 }, signal }),
  });
}

// --- Changes (every one refreshes the staff list and the person's page) ----------------------

function useStaffMutation<TResult, TBody>(
  request: (body: TBody) => Promise<TResult>,
  { refreshOnError = false } = {},
) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: staffKey });
  return useMutation<TResult, ApiError, TBody>({
    mutationFn: request,
    onSuccess: refresh,
    // After a refusal such as "changed by someone else", reload so the next try uses fresh data.
    onError: refreshOnError ? refresh : undefined,
  });
}

export function useCreateStaff(idempotencyKey: string) {
  return useStaffMutation<StaffMember, StaffMemberCreateRequest>((body) =>
    api.post<StaffMember>("/staff/", body, { idempotencyKey }),
  );
}

export function useUpdateStaff(id: string) {
  return useStaffMutation<StaffMember, StaffMemberUpdateRequest>(
    (body) => api.patch<StaffMember>(`/staff/${id}/`, body),
    { refreshOnError: true },
  );
}

export function useSendInvitation(id: string) {
  return useStaffMutation<InvitationSent, void>(() =>
    api.post<InvitationSent>(`/staff/${id}/invitation/`),
  );
}

export function useAddPosting(id: string, idempotencyKey: string) {
  return useStaffMutation<StaffDepartmentAssignment, StaffDepartmentAssignmentRequest>((body) =>
    api.post(`/staff/${id}/department-assignments/`, body, { idempotencyKey }),
  );
}

export function useEndPosting(id: string, assignmentId: string) {
  return useStaffMutation<StaffDepartmentAssignment, EndAssignmentRequest>(
    (body) => api.post(`/staff/${id}/department-assignments/${assignmentId}/end/`, body),
    { refreshOnError: true },
  );
}

export function useAddQualification(id: string, idempotencyKey: string) {
  return useStaffMutation<StaffQualification, StaffQualificationRequest>((body) =>
    api.post(`/staff/${id}/qualifications/`, body, { idempotencyKey }),
  );
}

export function useAddCredential(id: string, idempotencyKey: string) {
  return useStaffMutation<StaffCredential, StaffCredentialRequest>((body) =>
    api.post(`/staff/${id}/credentials/`, body, { idempotencyKey }),
  );
}

/** Verify or reject a qualification or credential (checked against the original document). */
export function useVerify(staffId: string, kind: "qualification" | "credential", itemId: string) {
  const path =
    kind === "qualification"
      ? `/staff/${staffId}/qualifications/${itemId}/verify/`
      : `/staff-credentials/${itemId}/verify/`;
  return useStaffMutation<unknown, CredentialVerificationRequest>(
    (body) => api.post(path, body),
    { refreshOnError: true },
  );
}

// --- Documents and licence expiry (HIMS-STAFF-005/006) ---------------------------------------

/** Where a document opens (in a new tab) or downloads; every use is audited by the server. */
export function documentUrl(id: string, inline: boolean): string {
  return `${API_BASE}/staff-documents/${id}/download/${inline ? "?inline=true" : ""}`;
}

export function useUploadDocument(staffId: string) {
  return useStaffMutation<StaffDocument, { file: File; credential?: string; qualification?: string }>(
    ({ file, credential, qualification }) => {
      const form = new FormData();
      form.append("file", file);
      if (credential) form.append("credential", credential);
      if (qualification) form.append("qualification", qualification);
      return api.post<StaffDocument>(`/staff/${staffId}/documents/`, form);
    },
  );
}

export function useArchiveDocument(id: string) {
  return useStaffMutation<StaffDocument, { reason: string }>(
    (body) => api.post<StaffDocument>(`/staff-documents/${id}/archive/`, body),
    { refreshOnError: true },
  );
}

export function useExpiringCredentials(within: number, includeExpired: boolean) {
  return useQuery<ExpiringCredential[], ApiError>({
    queryKey: [...staffKey, "expiring", { within, includeExpired }],
    queryFn: ({ signal }) =>
      api.get<ExpiringCredential[]>("/staff-credentials/expiring/", {
        query: { within, include_expired: includeExpired ? undefined : "false" },
        signal,
      }),
  });
}
