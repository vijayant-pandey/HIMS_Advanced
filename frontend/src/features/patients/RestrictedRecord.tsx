import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";

import type { PatientDetail, PatientRestrictionEnum } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasPermission } from "../auth/grants";
import { useEndEmergencyAccess, useOpenEmergencyAccess, useSetRestriction } from "./api";
import { RESTRICTION, dayTime } from "./labels";

const MIN_REASON = 10;

/**
 * Opening a restricted record without the right to (HIMS-PAT-006; D23, D14): say so and, for
 * doctors and nurses (`clinical.emergency_access`), offer emergency access: 4 hours, with a
 * reason; medical records are told at once and review it afterwards.
 */
export function RestrictedGate({ patientId }: { patientId: string }) {
  const { data: user } = useCurrentUser();
  const open = useOpenEmergencyAccess(patientId);
  const [reason, setReason] = useState("");
  // A hint only: the API checks the permission.
  const mayOpen = hasPermission(user, "clinical.emergency_access");
  const errors = fieldErrors(open.error);
  return (
    <Paper variant="outlined" component="section" aria-label="Restricted record" sx={{ p: 2, maxWidth: 720 }}>
      <Stack spacing={2}>
        <Typography variant="h5" component="h1">
          Restricted record
        </Typography>
        <Typography variant="body2">
          This record is restricted (for example a VIP or a member of staff). Medical records can open it.
          {mayOpen
            ? " In an emergency you can open it now for 4 hours: give the reason. Medical records are told at once and review every emergency access."
            : " If you need it for a patient's care, ask medical records, or a doctor or nurse with emergency access."}
        </Typography>
        {mayOpen && (
          <Stack
            spacing={2}
            component="form"
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              open.mutate({ reason });
            }}
          >
            <TextField
              label="Reason for emergency access"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              multiline
              minRows={2}
              required
              error={!!errors.reason}
              helperText={errors.reason ?? `At least ${MIN_REASON} characters, e.g. “Unconscious in the emergency room”.`}
            />
            {open.error && !errors.reason && <ErrorAlert error={open.error} />}
            <div>
              <Button
                type="submit"
                variant="contained"
                color="warning"
                disabled={open.isPending || reason.trim().length < MIN_REASON}
              >
                Open with emergency access
              </Button>
            </div>
          </Stack>
        )}
      </Stack>
    </Paper>
  );
}

/** Shown while the record is open with the reader's emergency access. */
export function EmergencyAccessBanner({ patient }: { patient: PatientDetail }) {
  const end = useEndEmergencyAccess(patient.id);
  if (!patient.emergency_access) return null;
  return (
    <Alert
      severity="warning"
      action={
        <Button color="inherit" size="small" disabled={end.isPending} onClick={() => end.mutate()}>
          End emergency access
        </Button>
      }
    >
      You opened this restricted record with emergency access until {dayTime(patient.emergency_access.expires_at)}.
      Medical records will review it. End it when you no longer need the record.
      {end.error && <ErrorAlert error={end.error} />}
    </Alert>
  );
}

/** Medical records restrict a record (VIP, staff, other) or lift the restriction, with a reason. */
export function RestrictionDialog({ patient, onClose }: { patient: PatientDetail; onClose: () => void }) {
  const save = useSetRestriction(patient.id);
  const lifting = patient.is_restricted;
  const [restriction, setRestriction] = useState<PatientRestrictionEnum>("staff");
  const [reason, setReason] = useState("");
  const errors = fieldErrors(save.error);
  return (
    <FormDialog
      title={lifting ? `Lift the restriction on ${patient.mrn}` : `Restrict ${patient.mrn}`}
      error={save.error}
      fields={["restriction", "reason"]}
      pending={save.isPending}
      submitLabel={lifting ? "Lift restriction" : "Restrict record"}
      submitDisabled={reason.trim().length < MIN_REASON}
      onClose={onClose}
      onSubmit={() =>
        save.mutate(
          { restricted: !lifting, restriction: lifting ? "" : restriction, reason, version: patient.version },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        {lifting
          ? "The record will be found by patient search again and opened by everyone who may open patients."
          : "The record will be hidden from patient search (its exact MRN shows only “Restricted record”). Only medical records open it, and doctors and nurses with emergency access. Every opening is recorded."}
      </Typography>
      {!lifting && (
        <TextField
          select
          label="Why"
          value={restriction}
          onChange={(event) => setRestriction(event.target.value as PatientRestrictionEnum)}
          error={!!errors.restriction}
          helperText={errors.restriction}
        >
          {Object.entries(RESTRICTION).map(([value, label]) => (
            <MenuItem key={value} value={value}>
              {label}
            </MenuItem>
          ))}
        </TextField>
      )}
      <TextField
        label="Reason"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        required
        error={!!errors.reason}
        helperText={errors.reason ?? `At least ${MIN_REASON} characters. Kept in the audit log.`}
      />
    </FormDialog>
  );
}
