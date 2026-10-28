import { Alert, FormControlLabel, MenuItem, Stack, Switch, TextField } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type {
  CredentialType,
  EmploymentStatus,
  StaffMemberDetail,
  StaffType,
} from "../../api/types";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import {
  useAddCredential,
  useAddPosting,
  useAddQualification,
  useAllDepartments,
  useCreateStaff,
  useDesignations,
  useEndPosting,
  useQualificationTypes,
  useSpecialties,
  useUpdateStaff,
  useVerify,
} from "./api";
import { CREDENTIAL_TYPES, EMPLOYMENT_STATUSES, STAFF_TYPES, options } from "./labels";

const today = () => new Date().toISOString().slice(0, 10);

/** A key per dialog session: a double-click or retry can never create the same thing twice. */
function useIdempotencyKey() {
  return useState(() => crypto.randomUUID())[0];
}

// --- Add staff ------------------------------------------------------------------------------

export function AddStaffDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const create = useCreateStaff(useIdempotencyKey());
  const [values, setValues] = useState({
    given_name: "",
    family_name: "",
    employee_number: "",
    staff_type: "doctor" as StaffType,
    joined_on: today(),
    email: "",
  });
  const errors = fieldErrors(create.error);
  const set = (name: keyof typeof values, value: string) =>
    setValues((current) => ({ ...current, [name]: value }));
  const missing = !values.given_name.trim() || !values.family_name.trim() || !values.employee_number.trim();

  return (
    <FormDialog
      title="Add staff member"
      error={create.error}
      fields={Object.keys(values)}
      submitLabel="Add"
      submitDisabled={missing}
      pending={create.isPending}
      onClose={onClose}
      onSubmit={() =>
        create.mutate(
          { ...values, email: values.email.trim() || null },
          { onSuccess: (staff) => navigate(`/staff/${staff.id}`) },
        )
      }
    >
      <Stack direction="row" spacing={2}>
        <TextField
          label="First name"
          required
          fullWidth
          value={values.given_name}
          onChange={(e) => set("given_name", e.target.value)}
          error={!!errors.given_name}
          helperText={errors.given_name}
        />
        <TextField
          label="Last name"
          required
          fullWidth
          value={values.family_name}
          onChange={(e) => set("family_name", e.target.value)}
          error={!!errors.family_name}
          helperText={errors.family_name}
        />
      </Stack>
      <Stack direction="row" spacing={2}>
        <TextField
          label="Employee number"
          required
          fullWidth
          value={values.employee_number}
          onChange={(e) => set("employee_number", e.target.value)}
          error={!!errors.employee_number}
          helperText={errors.employee_number}
        />
        <TextField
          select
          label="Staff type"
          fullWidth
          value={values.staff_type}
          onChange={(e) => set("staff_type", e.target.value)}
        >
          {options(STAFF_TYPES).map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      <Stack direction="row" spacing={2}>
        <TextField
          label="Joined on"
          type="date"
          fullWidth
          value={values.joined_on}
          onChange={(e) => set("joined_on", e.target.value)}
          error={!!errors.joined_on}
          helperText={errors.joined_on}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          label="Work email (optional)"
          type="email"
          fullWidth
          value={values.email}
          onChange={(e) => set("email", e.target.value)}
          error={!!errors.email}
          helperText={errors.email ?? "Needed to sign in. You can send the invitation next."}
        />
      </Stack>
    </FormDialog>
  );
}

// --- Edit staff -----------------------------------------------------------------------------

export function EditStaffDialog({
  staff,
  onClose,
}: {
  staff: StaffMemberDetail;
  onClose: () => void;
}) {
  const update = useUpdateStaff(staff.id);
  const [values, setValues] = useState({
    given_name: staff.given_name,
    family_name: staff.family_name,
    staff_type: staff.staff_type,
    employment_status: staff.employment_status,
    left_on: staff.left_on ?? "",
  });
  const errors = fieldErrors(update.error);
  const losingAccess =
    values.employment_status !== staff.employment_status &&
    (values.employment_status === "suspended" || values.employment_status === "terminated");

  return (
    <FormDialog
      title={`Edit ${staff.given_name} ${staff.family_name}`}
      error={update.error}
      fields={Object.keys(values)}
      pending={update.isPending}
      onClose={onClose}
      onSubmit={() =>
        update.mutate(
          { version: staff.version, ...values, left_on: values.left_on || null },
          { onSuccess: onClose },
        )
      }
    >
      <Stack direction="row" spacing={2}>
        <TextField
          label="First name"
          fullWidth
          value={values.given_name}
          onChange={(e) => setValues({ ...values, given_name: e.target.value })}
        />
        <TextField
          label="Last name"
          fullWidth
          value={values.family_name}
          onChange={(e) => setValues({ ...values, family_name: e.target.value })}
        />
      </Stack>
      <Stack direction="row" spacing={2}>
        <TextField
          select
          label="Staff type"
          fullWidth
          value={values.staff_type}
          onChange={(e) => setValues({ ...values, staff_type: e.target.value as StaffType })}
        >
          {options(STAFF_TYPES).map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Employment status"
          fullWidth
          value={values.employment_status}
          onChange={(e) =>
            setValues({ ...values, employment_status: e.target.value as EmploymentStatus })
          }
        >
          {options(EMPLOYMENT_STATUSES).map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      <TextField
        label="Last working day (if leaving)"
        type="date"
        value={values.left_on}
        onChange={(e) => setValues({ ...values, left_on: e.target.value })}
        error={!!errors.left_on}
        helperText={errors.left_on}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      {losingAccess && (
        <Alert severity="warning">
          {values.given_name} will be signed out everywhere and cannot sign in until the status is
          Active again.
        </Alert>
      )}
    </FormDialog>
  );
}

// --- Department posting ---------------------------------------------------------------------

export function AddPostingDialog({ staffId, onClose }: { staffId: string; onClose: () => void }) {
  const { data: user } = useCurrentUser();
  const add = useAddPosting(staffId, useIdempotencyKey());
  const departments = useAllDepartments();
  const designations = useDesignations(user?.organization?.country);
  const specialties = useSpecialties();
  const [values, setValues] = useState({
    department: "",
    designation: "",
    specialty: "",
    is_primary: true,
    valid_from: today(),
  });
  const errors = fieldErrors(add.error);
  const activeDepartments = (departments.data?.results ?? []).filter((d) => d.status === "active");

  return (
    <FormDialog
      title="Add department posting"
      error={add.error}
      fields={["department", "designation", "specialty", "valid_from"]}
      submitLabel="Add"
      submitDisabled={!values.department || !values.designation}
      pending={add.isPending}
      onClose={onClose}
      onSubmit={() =>
        add.mutate({ ...values, specialty: values.specialty || null }, { onSuccess: onClose })
      }
    >
      <TextField
        select
        label="Department"
        required
        value={values.department}
        onChange={(e) => setValues({ ...values, department: e.target.value })}
        error={!!errors.department}
        helperText={
          errors.department ??
          (activeDepartments.length === 0 ? "No active departments yet." : undefined)
        }
      >
        {activeDepartments.map((d) => (
          <MenuItem key={d.id} value={d.id}>
            {d.name} ({d.code})
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Designation (job title)"
        required
        value={values.designation}
        onChange={(e) => setValues({ ...values, designation: e.target.value })}
        error={!!errors.designation}
        helperText={errors.designation ?? "Junior to senior; titles for this hospital's country"}
      >
        {(designations.data ?? []).map((d) => (
          <MenuItem key={d.id} value={d.id}>
            {d.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Specialty (optional)"
        value={values.specialty}
        onChange={(e) => setValues({ ...values, specialty: e.target.value })}
      >
        <MenuItem value="">— None —</MenuItem>
        {(specialties.data ?? []).map((s) => (
          <MenuItem key={s.id} value={s.id}>
            {s.name}
          </MenuItem>
        ))}
      </TextField>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
        <TextField
          label="Starts on"
          type="date"
          value={values.valid_from}
          onChange={(e) => setValues({ ...values, valid_from: e.target.value })}
          error={!!errors.valid_from}
          helperText={errors.valid_from}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <FormControlLabel
          label="Main department"
          control={
            <Switch
              checked={values.is_primary}
              onChange={(e) => setValues({ ...values, is_primary: e.target.checked })}
            />
          }
        />
      </Stack>
    </FormDialog>
  );
}

export function EndPostingDialog({
  staffId,
  assignmentId,
  label,
  onClose,
}: {
  staffId: string;
  assignmentId: string;
  label: string;
  onClose: () => void;
}) {
  const end = useEndPosting(staffId, assignmentId);
  const [validUntil, setValidUntil] = useState(today());
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`End posting · ${label}`}
      error={end.error}
      fields={["reason"]}
      submitLabel="End posting"
      submitDisabled={!reason.trim()}
      pending={end.isPending}
      onClose={onClose}
      onSubmit={() =>
        end.mutate({ valid_until: validUntil, reason: reason.trim() }, { onSuccess: onClose })
      }
    >
      <TextField
        label="Last day"
        type="date"
        value={validUntil}
        onChange={(e) => setValidUntil(e.target.value)}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <TextField
        label="Reason"
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        helperText="e.g. Transferred to Neurology. Kept in the audit log."
      />
    </FormDialog>
  );
}

// --- Qualifications and credentials ---------------------------------------------------------

export function AddQualificationDialog({
  staffId,
  onClose,
}: {
  staffId: string;
  onClose: () => void;
}) {
  const { data: user } = useCurrentUser();
  const add = useAddQualification(staffId, useIdempotencyKey());
  const types = useQualificationTypes();
  const specialties = useSpecialties();
  const country = user?.organization?.country;
  const [values, setValues] = useState({
    qualification_type: "",
    specialty: "",
    institution: "",
    year_awarded: new Date().getFullYear(),
  });
  const errors = fieldErrors(add.error);
  const available = (types.data ?? []).filter((t) => !country || !t.country || t.country === country);

  return (
    <FormDialog
      title="Add qualification"
      error={add.error}
      fields={Object.keys(values)}
      submitLabel="Add"
      submitDisabled={!values.qualification_type || !values.institution.trim()}
      pending={add.isPending}
      onClose={onClose}
      onSubmit={() =>
        add.mutate({ ...values, specialty: values.specialty || null }, { onSuccess: onClose })
      }
    >
      <TextField
        select
        label="Qualification"
        required
        value={values.qualification_type}
        onChange={(e) => setValues({ ...values, qualification_type: e.target.value })}
        error={!!errors.qualification_type}
        helperText={errors.qualification_type}
      >
        {available.map((t) => (
          <MenuItem key={t.id} value={t.id}>
            {t.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Specialty (optional)"
        value={values.specialty}
        onChange={(e) => setValues({ ...values, specialty: e.target.value })}
      >
        <MenuItem value="">— None —</MenuItem>
        {(specialties.data ?? []).map((s) => (
          <MenuItem key={s.id} value={s.id}>
            {s.name}
          </MenuItem>
        ))}
      </TextField>
      <Stack direction="row" spacing={2}>
        <TextField
          label="Institution"
          required
          fullWidth
          value={values.institution}
          onChange={(e) => setValues({ ...values, institution: e.target.value })}
          error={!!errors.institution}
          helperText={errors.institution}
        />
        <TextField
          label="Year"
          type="number"
          value={values.year_awarded}
          onChange={(e) => setValues({ ...values, year_awarded: Number(e.target.value) })}
          error={!!errors.year_awarded}
          helperText={errors.year_awarded}
          sx={{ width: 140 }}
        />
      </Stack>
    </FormDialog>
  );
}

export function AddCredentialDialog({
  staffId,
  onClose,
}: {
  staffId: string;
  onClose: () => void;
}) {
  const add = useAddCredential(staffId, useIdempotencyKey());
  const [values, setValues] = useState({
    credential_type: "medical_registration" as CredentialType,
    registration_number: "",
    issuing_authority: "",
    jurisdiction: "",
    valid_from: "",
    expires_at: "",
  });
  const errors = fieldErrors(add.error);
  const set = (name: keyof typeof values, value: string) =>
    setValues((current) => ({ ...current, [name]: value }));

  return (
    <FormDialog
      title="Add licence / registration"
      error={add.error}
      fields={Object.keys(values)}
      submitLabel="Add"
      submitDisabled={
        !values.registration_number.trim() ||
        !values.issuing_authority.trim() ||
        !values.jurisdiction.trim()
      }
      pending={add.isPending}
      onClose={onClose}
      onSubmit={() =>
        add.mutate(
          {
            ...values,
            jurisdiction: values.jurisdiction.trim().toUpperCase(),
            valid_from: values.valid_from || null,
            expires_at: values.expires_at || null,
          },
          { onSuccess: onClose },
        )
      }
    >
      <TextField
        select
        label="Type"
        value={values.credential_type}
        onChange={(e) => set("credential_type", e.target.value)}
      >
        {options(CREDENTIAL_TYPES).map((o) => (
          <MenuItem key={o.value} value={o.value}>
            {o.label}
          </MenuItem>
        ))}
      </TextField>
      <Stack direction="row" spacing={2}>
        <TextField
          label="Registration number"
          required
          fullWidth
          value={values.registration_number}
          onChange={(e) => set("registration_number", e.target.value)}
          error={!!errors.registration_number}
          helperText={errors.registration_number}
        />
        <TextField
          label="Region"
          required
          value={values.jurisdiction}
          onChange={(e) => set("jurisdiction", e.target.value)}
          error={!!errors.jurisdiction}
          helperText={errors.jurisdiction ?? "e.g. IN-KA, US-CA"}
          sx={{ width: 160 }}
        />
      </Stack>
      <TextField
        label="Issued by"
        required
        value={values.issuing_authority}
        onChange={(e) => set("issuing_authority", e.target.value)}
        error={!!errors.issuing_authority}
        helperText={errors.issuing_authority ?? "e.g. Karnataka Medical Council"}
      />
      <Stack direction="row" spacing={2}>
        <TextField
          label="Valid from"
          type="date"
          fullWidth
          value={values.valid_from}
          onChange={(e) => set("valid_from", e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          label="Expires on"
          type="date"
          fullWidth
          value={values.expires_at}
          onChange={(e) => set("expires_at", e.target.value)}
          error={!!errors.expires_at}
          helperText={errors.expires_at ?? "Leave empty if it never expires"}
          slotProps={{ inputLabel: { shrink: true } }}
        />
      </Stack>
    </FormDialog>
  );
}

export function VerifyDialog({
  staffId,
  kind,
  itemId,
  label,
  onClose,
}: {
  staffId: string;
  kind: "qualification" | "credential";
  itemId: string;
  label: string;
  onClose: () => void;
}) {
  const verify = useVerify(staffId, kind, itemId);
  const [verified, setVerified] = useState(true);
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`Verify · ${label}`}
      error={verify.error}
      submitLabel={verified ? "Mark verified" : "Reject"}
      submitColor={verified ? "primary" : "error"}
      submitDisabled={!verified && !reason.trim()}
      pending={verify.isPending}
      onClose={onClose}
      onSubmit={() => verify.mutate({ verified, reason: reason.trim() }, { onSuccess: onClose })}
    >
      <TextField
        select
        label="Result"
        value={verified ? "yes" : "no"}
        onChange={(e) => setVerified(e.target.value === "yes")}
      >
        <MenuItem value="yes">Verified against the original document</MenuItem>
        <MenuItem value="no">Rejected (could not be confirmed)</MenuItem>
      </TextField>
      <TextField
        label={verified ? "Note (optional)" : "Reason"}
        required={!verified}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        helperText="e.g. Checked the council register online on 28 Oct. Kept in the audit log."
      />
    </FormDialog>
  );
}
