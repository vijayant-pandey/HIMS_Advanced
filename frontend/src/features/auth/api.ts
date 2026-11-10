import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, isUnauthenticated } from "../../api/client";
import type {
  ConfirmIdentityStatus,
  CurrentUser,
  InvitationAcceptRequest,
  InvitationDetails,
  PasswordResetConfirmRequest,
  PasswordResetDetails,
  PasswordResetRequested,
  LoginRequest,
  MfaChallenge,
  MfaRecoveryCodes,
  MfaSetup,
  MySession,
  NoAccessReference,
  Passkey,
  PasskeyOptions,
  SessionsEnded,
} from "../../api/types";
import { answerWithPasskey, createPasskey } from "./webauthn";

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

/** True when the password was accepted but the authenticator code is still needed. */
export function isMfaChallenge(result: CurrentUser | MfaChallenge): result is MfaChallenge {
  return "mfa_required" in result && result.mfa_required === true;
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation<CurrentUser | MfaChallenge, ApiError, LoginRequest>({
    mutationFn: async (credentials) => {
      await api.get("/auth/csrf/"); // sets the CSRF cookie required for login
      return api.post<CurrentUser | MfaChallenge>("/auth/login/", credentials);
    },
    onSuccess: (result) => {
      if (isMfaChallenge(result)) return; // second step still to come
      queryClient.clear();
      queryClient.setQueryData(currentUserKey, result);
    },
  });
}

/** Second sign-in step: the 6-digit authenticator code or a backup code (HIMS-IAM-005). */
export function useVerifyLogin() {
  const queryClient = useQueryClient();
  return useMutation<CurrentUser, ApiError, { code: string }>({
    mutationFn: (body) => api.post<CurrentUser>("/auth/login/verify/", body),
    onSuccess: (user) => {
      queryClient.clear();
      queryClient.setQueryData(currentUserKey, user);
    },
  });
}

/** Second sign-in step with a passkey instead of the code (HIMS-IAM-014). */
export function usePasskeyLogin() {
  const queryClient = useQueryClient();
  return useMutation<CurrentUser, unknown, void>({
    mutationFn: async () => {
      const options = await api.post<PasskeyOptions>("/auth/login/passkey-options/");
      const credential = await answerWithPasskey(options.public_key as Record<string, unknown>);
      return api.post<CurrentUser>("/auth/login/passkey/", { credential });
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

/** Records an "access.none_assigned" audit event and returns its reference number (HIMS-UI-002). */
export function useReportNoAccess() {
  return useMutation<NoAccessReference, ApiError, { page: string }>({
    mutationFn: (body) => api.post<NoAccessReference>("/auth/no-access-report/", body),
  });
}


// --- Two-factor sign-in management (Security page) ------------------------------------------

function useRefreshCurrentUser() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: currentUserKey });
}

export function useStartMfaSetup() {
  return useMutation<MfaSetup, ApiError, void>({
    mutationFn: () => api.post<MfaSetup>("/auth/mfa/setup/"),
  });
}

export function useConfirmMfaSetup() {
  const refresh = useRefreshCurrentUser();
  return useMutation<MfaRecoveryCodes, ApiError, { code: string }>({
    mutationFn: (body) => api.post<MfaRecoveryCodes>("/auth/mfa/confirm/", body),
    // Not awaited: the caller must get the one-time backup codes before the page re-renders.
    onSuccess: () => {
      void refresh();
    },
  });
}

export function useRegenerateRecoveryCodes() {
  const refresh = useRefreshCurrentUser();
  return useMutation<MfaRecoveryCodes, ApiError, { code: string }>({
    mutationFn: (body) => api.post<MfaRecoveryCodes>("/auth/mfa/recovery-codes/", body),
    onSuccess: () => refresh(),
  });
}

export function useDisableMfa() {
  const refresh = useRefreshCurrentUser();
  return useMutation<void, ApiError, { code: string }>({
    mutationFn: (body) => api.post<void>("/auth/mfa/disable/", body),
    onSuccess: () => refresh(),
  });
}

const passkeysKey = ["auth", "passkeys"] as const;

/** Your passkeys (HIMS-IAM-014). */
export function usePasskeys() {
  return useQuery<Passkey[], ApiError>({
    queryKey: passkeysKey,
    queryFn: ({ signal }) => api.get<Passkey[]>("/auth/passkeys/", { signal }),
  });
}

/** Adding one is sensitive: the API client asks "confirm it's you" first if needed. */
export function useAddPasskey() {
  const queryClient = useQueryClient();
  return useMutation<Passkey, unknown, string>({
    mutationFn: async (name) => {
      const options = await api.post<PasskeyOptions>("/auth/passkeys/add-options/");
      const credential = await createPasskey(options.public_key as Record<string, unknown>);
      return api.post<Passkey>("/auth/passkeys/add/", { name, credential });
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: passkeysKey });
      void queryClient.invalidateQueries({ queryKey: currentUserKey });
    },
  });
}

export function useRemovePasskey() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.post<void>(`/auth/passkeys/${id}/remove/`),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: passkeysKey });
      void queryClient.invalidateQueries({ queryKey: currentUserKey });
    },
  });
}

const mySessionsKey = ["auth", "sessions"] as const;

/** "My sign-ins" (HIMS-IAM-016): this person's open sessions. */
export function useMySessions() {
  return useQuery<MySession[], ApiError>({
    queryKey: mySessionsKey,
    queryFn: ({ signal }) => api.get<MySession[]>("/auth/sessions/", { signal }),
  });
}

export function useSignOutDevice() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.post<void>(`/auth/sessions/${id}/sign-out/`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: mySessionsKey }),
  });
}

export function useSignOutOtherDevices() {
  const queryClient = useQueryClient();
  return useMutation<SessionsEnded, ApiError, void>({
    mutationFn: () => api.post<SessionsEnded>("/auth/sessions/sign-out-others/"),
    onSettled: () => queryClient.invalidateQueries({ queryKey: mySessionsKey }),
  });
}

export const confirmIdentityKey = ["auth", "confirm-identity"] as const;

/** Whether sensitive actions will ask right now (HIMS-IAM-007). */
export function useIdentityConfirmation() {
  return useQuery<ConfirmIdentityStatus, ApiError>({
    queryKey: confirmIdentityKey,
    queryFn: ({ signal }) => api.get<ConfirmIdentityStatus>("/auth/confirm-identity/", { signal }),
    refetchInterval: 60_000, // it runs out by itself
  });
}

export function useEndIdentityConfirmation() {
  const queryClient = useQueryClient();
  return useMutation<ConfirmIdentityStatus, ApiError, void>({
    mutationFn: () => api.post<ConfirmIdentityStatus>("/auth/confirm-identity/end/"),
    onSuccess: (result) => queryClient.setQueryData(confirmIdentityKey, result),
  });
}
