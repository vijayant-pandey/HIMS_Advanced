import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, isUnauthenticated } from "../../api/client";
import type { CurrentUser, LoginRequest } from "../../api/types";

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
