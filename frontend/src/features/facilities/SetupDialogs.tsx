import { Alert, MenuItem, Stack, TextField } from "@mui/material";
import { useState } from "react";

import type {
  Department,
  DepartmentType,
  Facility,
  FacilityType,
} from "../../api/types";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { useCreateDepartment, useUpdateDepartment, useUpdateFacility } from "./api";

export const DEPARTMENT_TYPES: Record<DepartmentType, string> = {
  clinical: "Clinical",
  diagnostic: "Diagnostic",
  pharmacy: "Pharmacy",
  support: "Support",
  administrative: "Administrative",
};

export const FACILITY_TYPES: Record<FacilityType, string> = {
  hospital: "Hospital",
  clinic: "Clinic",
  diagnostic_center: "Diagnostic center",
  day_care: "Day-care center",
};

/** Common time zones per country; the current value is always kept as an option. */
const TIME_ZONES: Record<string, string[]> = {
  IN: ["Asia/Kolkata"],
  US: [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Phoenix",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
  ],
};

function entries<T extends string>(labels: Record<T, string>) {
  return Object.entries(labels) as [T, string][];
}

// --- Facility -------------------------------------------------------------------------------

export function EditFacilityDialog({ facility, onClose }: { facility: Facility; onClose: () => void }) {
  const update = useUpdateFacility(facility.id);
  const [values, setValues] = useState({
    name: facility.name,
    facility_type: facility.facility_type,
    state_region: facility.state_region,
    city: facility.city,
    address_line1: facility.address_line1,
    address_line2: facility.address_line2,
    postal_code: facility.postal_code,
    timezone: facility.timezone,
    phone: facility.phone,
    status: facility.status,
  });
  const errors = fieldErrors(update.error);
  const set = (name: keyof typeof values, value: string) =>
    setValues((current) => ({ ...current, [name]: value }));
  const zones = [...new Set([...(TIME_ZONES[facility.country] ?? []), facility.timezone])];
  const field = (name: keyof typeof values, label: string, required = true) => (
    <TextField
      label={label}
      required={required}
      fullWidth
      value={values[name]}
      onChange={(e) => set(name, e.target.value)}
      error={!!errors[name]}
      helperText={errors[name]}
    />
  );
  const closing = facility.status === "active" && values.status === "inactive";

  return (
    <FormDialog
      title={`Edit facility · ${facility.name} (${facility.code})`}
      error={update.error}
      fields={Object.keys(values)}
      pending={update.isPending}
      onClose={onClose}
      onSubmit={() => update.mutate({ version: facility.version, ...values }, { onSuccess: onClose })}
    >
      <Stack direction="row" spacing={2}>
        {field("name", "Name")}
        <TextField
          select
          label="Type"
          fullWidth
          value={values.facility_type}
          onChange={(e) => set("facility_type", e.target.value)}
        >
          {entries(FACILITY_TYPES).map(([value, label]) => (
            <MenuItem key={value} value={value}>
              {label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {field("address_line1", "Address line 1")}
      {field("address_line2", "Address line 2", false)}
      <Stack direction="row" spacing={2}>
        {field("city", "City")}
        {field("state_region", "State / region")}
        {field("postal_code", "Postal code")}
      </Stack>
      <Stack direction="row" spacing={2}>
        <TextField
          select
          label="Time zone"
          fullWidth
          value={values.timezone}
          onChange={(e) => set("timezone", e.target.value)}
          error={!!errors.timezone}
          helperText={errors.timezone ?? "Used for dates on records, e.g. which financial year an invoice belongs to"}
        >
          {zones.map((zone) => (
            <MenuItem key={zone} value={zone}>
              {zone}
            </MenuItem>
          ))}
        </TextField>
        {field("phone", "Phone", false)}
      </Stack>
      <TextField
        select
        label="Status"
        value={values.status}
        onChange={(e) => set("status", e.target.value)}
        error={!!errors.status}
        helperText={errors.status}
      >
        <MenuItem value="active">Active</MenuItem>
        <MenuItem value="inactive">Inactive</MenuItem>
      </TextField>
      {closing && !errors.status && (
        <Alert severity="warning">
          Deactivate its departments and buildings and remove access given at this facility first;
          the facility can then be closed. Nothing is deleted.
        </Alert>
      )}
    </FormDialog>
  );
}

// --- Department -----------------------------------------------------------------------------

function slug(text: string) {
  return text.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9_-]/g, "");
}

export function AddDepartmentDialog({
  facilities,
  initialFacility,
  onClose,
}: {
  facilities: Facility[];
  initialFacility?: string;
  onClose: () => void;
}) {
  const create = useCreateDepartment(useState(() => crypto.randomUUID())[0]);
  const [values, setValues] = useState({
    facility: initialFacility ?? facilities[0]?.id ?? "",
    code: "",
    name: "",
    department_type: "clinical" as DepartmentType,
  });
  const errors = fieldErrors(create.error);

  return (
    <FormDialog
      title="Add department"
      error={create.error}
      fields={Object.keys(values)}
      submitLabel="Add"
      submitDisabled={!values.facility || !values.code || !values.name.trim()}
      pending={create.isPending}
      onClose={onClose}
      onSubmit={() => create.mutate({ ...values, name: values.name.trim() }, { onSuccess: onClose })}
    >
      <TextField
        select
        label="Facility"
        required
        value={values.facility}
        onChange={(e) => setValues({ ...values, facility: e.target.value })}
        error={!!errors.facility}
        helperText={errors.facility}
      >
        {facilities.map((f) => (
          <MenuItem key={f.id} value={f.id}>
            {f.name}
          </MenuItem>
        ))}
      </TextField>
      <Stack direction="row" spacing={2}>
        <TextField
          label="Name"
          required
          fullWidth
          value={values.name}
          onChange={(e) => setValues({ ...values, name: e.target.value })}
          error={!!errors.name}
          helperText={errors.name ?? "e.g. Cardiology"}
        />
        <TextField
          label="Code"
          required
          fullWidth
          value={values.code}
          onChange={(e) => setValues({ ...values, code: slug(e.target.value) })}
          error={!!errors.code}
          helperText={errors.code ?? "Short code, e.g. cardio. Cannot be changed later."}
          slotProps={{ htmlInput: { maxLength: 32 } }}
        />
      </Stack>
      <TextField
        select
        label="Type"
        value={values.department_type}
        onChange={(e) => setValues({ ...values, department_type: e.target.value as DepartmentType })}
      >
        {entries(DEPARTMENT_TYPES).map(([value, label]) => (
          <MenuItem key={value} value={value}>
            {label}
          </MenuItem>
        ))}
      </TextField>
    </FormDialog>
  );
}

export function EditDepartmentDialog({
  department,
  onClose,
}: {
  department: Department;
  onClose: () => void;
}) {
  const update = useUpdateDepartment(department.id);
  const [values, setValues] = useState({
    name: department.name,
    department_type: department.department_type,
    status: department.status,
  });
  const errors = fieldErrors(update.error);
  const closing = department.status === "active" && values.status === "inactive";
  const inUse = department.current_staff > 0 || department.active_wards > 0;

  return (
    <FormDialog
      title={`Edit department · ${department.name} (${department.code})`}
      error={update.error}
      fields={Object.keys(values)}
      pending={update.isPending}
      onClose={onClose}
      onSubmit={() =>
        update.mutate({ version: department.version, ...values }, { onSuccess: onClose })
      }
    >
      <Stack direction="row" spacing={2}>
        <TextField
          label="Name"
          fullWidth
          value={values.name}
          onChange={(e) => setValues({ ...values, name: e.target.value })}
          error={!!errors.name}
          helperText={errors.name}
        />
        <TextField
          select
          label="Type"
          fullWidth
          value={values.department_type}
          onChange={(e) =>
            setValues({ ...values, department_type: e.target.value as DepartmentType })
          }
        >
          {entries(DEPARTMENT_TYPES).map(([value, label]) => (
            <MenuItem key={value} value={value}>
              {label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      <TextField
        select
        label="Status"
        value={values.status}
        onChange={(e) => setValues({ ...values, status: e.target.value as Department["status"] })}
        error={!!errors.status}
        helperText={errors.status}
      >
        <MenuItem value="active">Active</MenuItem>
        <MenuItem value="inactive">Inactive</MenuItem>
      </TextField>
      {closing && !errors.status && (
        <Alert severity={inUse ? "warning" : "info"}>
          {inUse
            ? `Still in use: ${department.current_staff} staff posted, ${department.active_wards} active ward(s). End those first; access limited to this department must also be removed.`
            : "Nothing is deleted; you can reactivate it later."}
        </Alert>
      )}
    </FormDialog>
  );
}
