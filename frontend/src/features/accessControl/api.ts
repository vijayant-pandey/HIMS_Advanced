import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  PaginatedRoleAssignmentList,
  PaginatedRoleList,
  Permission,
  Role,
  RoleAssignment,
  RoleAssignmentCreateRequest,
  RoleCreateRequest,
  RoleUpdateRequest,
} from "../../api/types";

export const accessKey = ["access"] as const;

export function useRoles() {
  return useQuery<PaginatedRoleList, ApiError>({
    queryKey: [...accessKey, "roles"],
    queryFn: ({ signal }) =>
      api.get<PaginatedRoleList>("/roles/", { query: { page_size: 100 }, signal }),
  });
}

export function usePermissions() {
  return useQuery<Permission[], ApiError>({
    queryKey: [...accessKey, "permissions"],
    queryFn: ({ signal }) => api.get<Permission[]>("/permissions/", { signal }),
    staleTime: Infinity,
  });
}

export function useRoleAssignments(filters: { user?: string; role?: string; active?: boolean }) {
  return useQuery<PaginatedRoleAssignmentList, ApiError>({
    queryKey: [...accessKey, "assignments", filters],
    queryFn: ({ signal }) =>
      api.get<PaginatedRoleAssignmentList>("/role-assignments/", {
        query: {
          user: filters.user,
          role: filters.role,
          active: filters.active ? "true" : undefined,
          page_size: 100,
        },
        signal,
      }),
  });
}

function useAccessMutation<TResult, TBody>(request: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation<TResult, ApiError, TBody>({
    mutationFn: request,
    // Refresh after a refusal too (e.g. someone else changed the role first).
    onSettled: () => queryClient.invalidateQueries({ queryKey: accessKey }),
  });
}

export function useGrantRole(idempotencyKey: string) {
  return useAccessMutation<RoleAssignment, RoleAssignmentCreateRequest>((body) =>
    api.post<RoleAssignment>("/role-assignments/", body, { idempotencyKey }),
  );
}

export function useRevokeAssignment(id: string) {
  return useAccessMutation<RoleAssignment, { reason: string }>((body) =>
    api.post<RoleAssignment>(`/role-assignments/${id}/revoke/`, body),
  );
}

export function useCreateRole(idempotencyKey: string) {
  return useAccessMutation<Role, RoleCreateRequest>((body) =>
    api.post<Role>("/roles/", body, { idempotencyKey }),
  );
}

export function useUpdateRole(id: string) {
  return useAccessMutation<Role, RoleUpdateRequest>((body) =>
    api.patch<Role>(`/roles/${id}/`, body),
  );
}
