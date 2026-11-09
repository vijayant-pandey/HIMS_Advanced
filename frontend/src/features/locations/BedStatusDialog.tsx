import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from "@mui/material";
import { type ReactNode, useState } from "react";

import type { TreeBed } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useChangeBedStatus } from "./api";
import {
  SETTABLE_STATUSES,
  type SettableStatus,
  isSettable,
  statusInfo,
} from "./bedStatus";

interface Props {
  /** A bed from the Locations tree or the bed board: only these fields are needed. */
  bed: Pick<TreeBed, "id" | "code" | "status" | "status_reason" | "version">;
  wardName: string;
  onClose: () => void;
  /** Shown to people who may change the bed itself (type, active): opens the edit form. */
  onEditDetails?: () => void;
  /** People who may not change the status only see it (the bed board, HIMS-FAC-008). */
  readOnly?: boolean;
  /** Extra content under the form, e.g. the bed's status history on the bed board. */
  children?: ReactNode;
}

export function BedStatusDialog({ bed, wardName, onClose, onEditDetails, readOnly = false, children }: Props) {
  // One key per dialog session: a double-click or network retry cannot apply the change twice.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const change = useChangeBedStatus(bed.id, idempotencyKey);
  const [status, setStatus] = useState<SettableStatus>(
    isSettable(bed.status) ? (bed.status as SettableStatus) : "available",
  );
  const [reason, setReason] = useState(bed.status_reason);
  const reasonNeeded = status !== "available";
  const managedByAdmissions = !isSettable(bed.status);
  const canSave = !managedByAdmissions && !readOnly;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    change.mutate(
      {
        version: bed.version,
        status,
        reason: reasonNeeded ? reason.trim() : "",
      },
      { onSuccess: onClose },
    );
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <form onSubmit={submit} noValidate>
        <DialogTitle>
          Bed {bed.code.toUpperCase()} · {wardName}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {readOnly && !managedByAdmissions ? (
              <Alert severity="info">
                {statusInfo(bed.status).label}
                {bed.status_reason ? `: ${bed.status_reason}` : ""}. Only people who manage
                this ward's beds can change it.
              </Alert>
            ) : managedByAdmissions ? (
              <Alert severity="info">
                This bed is {statusInfo(bed.status).label.toLowerCase()}. Its
                status changes through admission, transfer, discharge and
                cleaning.
              </Alert>
            ) : (
              <>
                {change.error && <ErrorAlert error={change.error} />}
                <TextField
                  select
                  label="Status"
                  value={status}
                  onChange={(event) =>
                    setStatus(event.target.value as SettableStatus)
                  }
                >
                  {SETTABLE_STATUSES.map((value) => (
                    <MenuItem key={value} value={value}>
                      {statusInfo(value).label}
                    </MenuItem>
                  ))}
                </TextField>
                {reasonNeeded && (
                  <TextField
                    label="Reason"
                    required
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    helperText="e.g. Broken side rail. Do not enter patient details."
                    slotProps={{ htmlInput: { maxLength: 255 } }}
                  />
                )}
              </>
            )}
            {children}
          </Stack>
        </DialogContent>
        <DialogActions>
          {onEditDetails && (
            <Button onClick={onEditDetails} sx={{ mr: "auto" }}>
              Edit bed details
            </Button>
          )}
          <Button onClick={onClose}>{canSave ? "Cancel" : "Close"}</Button>
          {canSave && (
            <Button
              type="submit"
              variant="contained"
              disabled={change.isPending || (reasonNeeded && !reason.trim())}
            >
              Save
            </Button>
          )}
        </DialogActions>
      </form>
    </Dialog>
  );
}
