import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type { Backup, RecoveryStatus, RestoreDrill, RestoreDrillDetail } from "../../api/types";

const recoveryKey = ["recovery"] as const;

export function useRecoveryStatus() {
  return useQuery<RecoveryStatus, ApiError>({
    queryKey: [...recoveryKey, "status"],
    queryFn: ({ signal }) => api.get<RecoveryStatus>("/backups/status/", { signal }),
  });
}

export function useBackups() {
  return useQuery<Backup[], ApiError>({
    queryKey: [...recoveryKey, "backups"],
    queryFn: ({ signal }) => api.get<Backup[]>("/backups/", { signal }),
  });
}

export function useRestoreDrills() {
  return useQuery<RestoreDrill[], ApiError>({
    queryKey: [...recoveryKey, "drills"],
    queryFn: ({ signal }) => api.get<RestoreDrill[]>("/restore-drills/", { signal }),
  });
}

export function useRestoreDrill(id: string) {
  return useQuery<RestoreDrillDetail, ApiError>({
    queryKey: [...recoveryKey, "drills", id],
    queryFn: ({ signal }) => api.get<RestoreDrillDetail>(`/restore-drills/${id}/`, { signal }),
  });
}

/** Backs up the database and documents now (a sensitive action: "Confirm it's you" may open). */
export function useMakeBackup() {
  const queryClient = useQueryClient();
  return useMutation<Backup, ApiError, void>({
    mutationFn: () => api.post<Backup>("/backups/", {}),
    onSettled: () => queryClient.invalidateQueries({ queryKey: recoveryKey }),
  });
}

/** Restores a backup into a separate copy, checks it and removes the copy. */
export function useRunRestoreDrill() {
  const queryClient = useQueryClient();
  return useMutation<RestoreDrillDetail, ApiError, string>({
    mutationFn: (backup) => api.post<RestoreDrillDetail>("/restore-drills/", { backup }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: recoveryKey }),
  });
}
