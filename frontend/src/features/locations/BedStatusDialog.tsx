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
import { useState } from "react";

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
  bed: TreeBed;
  wardName: string;
  onClose: () => void;
  /** Shown to people who may change the bed itself (type, active): opens the edit form. */
  onEditDetails?: () => void;
}

export function BedStatusDialog({ bed, wardName, onClose, onEditDetails }: Props) {
  // One key per dialog session: a double-click or network retry cannot apply the change twice.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const change = useChangeBedStatus(bed.id, idempotencyKey);
  const [status, setStatus] = useState<SettableStatus>(
    isSettable(bed.status) ? (bed.status as SettableStatus) : "available",
  );
  const [reason, setReason] = useState(bed.status_reason);
  const reasonNeeded = status !== "available";
  const managedByAdmissions = !isSettable(bed.status);

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
            {managedByAdmissions ? (
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
          </Stack>
        </DialogContent>
        <DialogActions>
          {onEditDetails && (
            <Button onClick={onEditDetails} sx={{ mr: "auto" }}>
              Edit bed details
            </Button>
          )}
          <Button onClick={onClose}>
            {managedByAdmissions ? "Close" : "Cancel"}
          </Button>
          {!managedByAdmissions && (
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
