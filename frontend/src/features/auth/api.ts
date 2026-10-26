import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, isUnauthenticated } from "../../api/client";
import type {
  CurrentUser,
  InvitationAcceptRequest,
  InvitationDetails,
  PasswordResetConfirmRequest,
  PasswordResetDetails,
  PasswordResetRequested,
  LoginRequest,
} from "../../api/types";

export const currentUserKey = ["auth", "me"] as const;

export function useCurrentUser() {
  return useQuery<CurrentUser | null, ApiError>({
    queryKey: currentUserKey,
    queryFn: async () => {
      try {
        return await api.get<CurrentUser>("/auth/me/");
      } catch (error) {
        if (isUnauthenticated(error)) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation<CurrentUser, ApiError, LoginRequest>({
    mutationFn: async (credentials) => {
      await api.get("/auth/csrf/"); // sets the CSRF cookie required for login
      return api.post<CurrentUser>("/auth/login/", credentials);
    },
    onSuccess: (user) => {
      queryClient.clear();
      queryClient.setQueryData(currentUserKey, user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError>({
    mutationFn: () => api.post<void>("/auth/logout/"),
    onSettled: () => {
      // Drop every cached clinical/administrative response with the session.
      queryClient.clear();
      queryClient.setQueryData(currentUserKey, null);
    },
  });
}

/** Checks an activation link so the page can greet the person. Changes nothing. */
export function useInvitationDetails(token: string | null) {
  return useQuery<InvitationDetails, ApiError>({
    queryKey: ["auth", "invitation", token],
    queryFn: async () => {
      await api.get("/auth/csrf/");
      return api.post<InvitationDetails>("/auth/invitations/inspect/", { token });
    },
    enabled: !!token,
    retry: false,
    staleTime: Infinity,
  });
}

/** Sets the password, activates the account and signs the person in. */
export function useAcceptInvitation() {
  const queryClient = useQueryClient();
  return useMutation<CurrentUser, ApiError, InvitationAcceptRequest>({
    mutationFn: (body) => api.post<CurrentUser>("/auth/invitations/accept/", body),
    onSuccess: (user) => {
      queryClient.clear();
      queryClient.setQueryData(currentUserKey, user);
    },
  });
}

/** "Forgot password": always answers the same way, whether or not the account exists. */
export function useRequestPasswordReset() {
  return useMutation<PasswordResetRequested, ApiError, { email: string }>({
    mutationFn: async (body) => {
      await api.get("/auth/csrf/");
      return api.post<PasswordResetRequested>("/auth/password-reset/request/", body);
    },
  });
}

export function usePasswordResetDetails(token: string | null) {
  return useQuery<PasswordResetDetails, ApiError>({
    queryKey: ["auth", "password-reset", token],
    queryFn: async () => {
      await api.get("/auth/csrf/");
      return api.post<PasswordResetDetails>("/auth/password-reset/inspect/", { token });
    },
    enabled: !!token,
    retry: false,
    staleTime: Infinity,
  });
}

/** Sets the new password. Every existing session ends, so the person signs in again. */
export function useConfirmPasswordReset() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, PasswordResetConfirmRequest>({
    mutationFn: (body) => api.post<void>("/auth/password-reset/confirm/", body),
    onSuccess: () => {
      queryClient.clear();
      queryClient.setQueryData(currentUserKey, null);
    },
  });
}
