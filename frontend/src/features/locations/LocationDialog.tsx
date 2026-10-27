import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
} from "@mui/material";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { ErrorAlert } from "../../components/ErrorAlert";
import { type LocationKind, useCreateLocation, useDepartments, useUpdateLocation } from "./api";
import {
  AGE_GROUPS,
  BED_TYPES,
  GENDER_RESTRICTIONS,
  ROOM_TYPES,
  WARD_TYPES,
  options,
} from "./choices";

type Value = string | number | boolean | null;
type Values = Record<string, Value>;

interface Field {
  name: string;
  label: string;
  kind: "text" | "code" | "number" | "select" | "switch" | "department";
  choices?: { value: string; label: string }[];
  helper?: string;
  /** Codes are set once (printed on labels and records); they cannot change later. */
  createOnly?: boolean;
  initial: Value;
}

const CODE_HELP = "Short code, e.g. main or block-a. It cannot be changed later.";

const FIELDS: Record<LocationKind, Field[]> = {
  building: [
    { name: "code", label: "Code", kind: "code", createOnly: true, helper: CODE_HELP, initial: "" },
    { name: "name", label: "Name", kind: "text", helper: "e.g. Main Block", initial: "" },
  ],
  floor: [
    {
      name: "level",
      label: "Level",
      kind: "number",
      helper: "0 = ground, 1 = first, -1 = basement",
      initial: 0,
    },
    { name: "name", label: "Name", kind: "text", helper: "e.g. Ground floor", initial: "" },
  ],
  ward: [
    { name: "code", label: "Code", kind: "code", createOnly: true, helper: CODE_HELP, initial: "" },
    { name: "name", label: "Name", kind: "text", helper: "e.g. Medical ICU", initial: "" },
    { name: "ward_type", label: "Type", kind: "select", choices: options(WARD_TYPES), initial: "general" },
    { name: "department", label: "Department (optional)", kind: "department", initial: null },
    {
      name: "gender_restriction",
      label: "Patients",
      kind: "select",
      choices: options(GENDER_RESTRICTIONS),
      initial: "any",
    },
    { name: "age_group", label: "Age group", kind: "select", choices: options(AGE_GROUPS), initial: "any" },
  ],
  room: [
    { name: "code", label: "Code", kind: "code", createOnly: true, helper: CODE_HELP, initial: "" },
    { name: "name", label: "Name", kind: "text", helper: "e.g. Room 101", initial: "" },
    { name: "room_type", label: "Type", kind: "select", choices: options(ROOM_TYPES), initial: "general" },
    {
      name: "is_isolation_capable",
      label: "Isolation-capable (e.g. negative pressure)",
      kind: "switch",
      initial: false,
    },
  ],
  bed: [
    {
      name: "code",
      label: "Bed code",
      kind: "code",
      createOnly: true,
      helper: "e.g. b12. Unique in the ward; cannot be changed later.",
      initial: "",
    },
    { name: "bed_type", label: "Bed type", kind: "select", choices: options(BED_TYPES), initial: "general" },
  ],
};

const PARENT_FIELD: Record<LocationKind, string> = {
  building: "facility",
  floor: "building",
  ward: "floor",
  room: "ward",
  bed: "room",
};

export const KIND_LABEL: Record<LocationKind, string> = {
  building: "building",
  floor: "floor",
  ward: "ward",
  room: "room",
  bed: "bed",
};

/** What the dialog edits: the item's current values from the location tree. */
export interface ExistingLocation {
  id: string;
  version: number;
  is_active: boolean;
  [field: string]: unknown;
}

interface Props {
  kind: LocationKind;
  facilityId: string;
  /** Create: the parent's id. */
  parentId?: string;
  /** Edit: the item as shown in the tree. */
  existing?: ExistingLocation;
  /** Shown in the title, e.g. "in Main Block". */
  context?: string;
  onClose: () => void;
}

function slug(text: string) {
  return text.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9_-]/g, "");
}

export function LocationDialog({ kind, facilityId, parentId, existing, context, onClose }: Props) {
  const editing = existing !== undefined;
  const fields = FIELDS[kind].filter((field) => !(editing && field.createOnly));
  const [values, setValues] = useState<Values>(() => {
    const initial: Values = {};
    for (const field of fields) {
      initial[field.name] = editing ? ((existing[field.name] as Value) ?? null) : field.initial;
    }
    if (editing) initial.is_active = existing.is_active;
    return initial;
  });
  // One key per dialog session: a double-click cannot create the same item twice.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const create = useCreateLocation(kind, idempotencyKey);
  const update = useUpdateLocation(kind, existing?.id ?? "");
  const mutation = editing ? update : create;
  const departments = useDepartments(fields.some((f) => f.kind === "department") ? facilityId : undefined);

  const fieldErrors: Record<string, string> = {};
  const shown = new Set([...fields.map((f) => f.name), "is_active"]);
  let otherError = false;
  if (mutation.error instanceof ApiError) {
    for (const error of mutation.error.problem.errors ?? []) {
      if (error.field && shown.has(error.field)) fieldErrors[error.field] = error.message;
      else otherError = true;
    }
    if (!mutation.error.problem.errors?.length) otherError = true;
  } else if (mutation.error) {
    otherError = true;
  }

  const set = (name: string, value: Value) => setValues((current) => ({ ...current, [name]: value }));
  const missing = fields.some(
    (f) => (f.kind === "text" || f.kind === "code") && !String(values[f.name] ?? "").trim(),
  );

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const body: Record<string, unknown> = { ...values };
    if ("department" in body && !body.department) body.department = null;
    if (editing) {
      update.mutate({ version: existing.version, ...body }, { onSuccess: onClose });
    } else {
      create.mutate({ [PARENT_FIELD[kind]]: parentId, ...body }, { onSuccess: onClose });
    }
  };

  const title = `${editing ? "Edit" : "Add"} ${KIND_LABEL[kind]}${context ? ` ${context}` : ""}`;

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <form onSubmit={submit} noValidate>
        <DialogTitle>{title}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {otherError && <ErrorAlert error={mutation.error} />}
            {fields.map((field) => {
              const error = fieldErrors[field.name];
              const common = {
                label: field.label,
                error: !!error,
                helperText: error ?? field.helper,
                fullWidth: true,
              };
              if (field.kind === "switch") {
                return (
                  <FormControlLabel
                    key={field.name}
                    label={field.label}
                    control={
                      <Switch
                        checked={!!values[field.name]}
                        onChange={(e) => set(field.name, e.target.checked)}
                      />
                    }
                  />
                );
              }
              if (field.kind === "select" || field.kind === "department") {
                const choices =
                  field.kind === "department"
                    ? [
                        { value: "", label: "— None —" },
                        ...(departments.data?.results ?? []).map((d) => ({
                          value: d.id,
                          label: d.name,
                        })),
                      ]
                    : (field.choices ?? []);
                return (
                  <TextField
                    key={field.name}
                    select
                    {...common}
                    value={values[field.name] ?? ""}
                    onChange={(e) => set(field.name, e.target.value)}
                  >
                    {choices.map((choice) => (
                      <MenuItem key={choice.value} value={choice.value}>
                        {choice.label}
                      </MenuItem>
                    ))}
                  </TextField>
                );
              }
              return (
                <TextField
                  key={field.name}
                  {...common}
                  required={field.kind !== "number"}
                  type={field.kind === "number" ? "number" : "text"}
                  value={values[field.name] ?? ""}
                  onChange={(e) =>
                    set(
                      field.name,
                      field.kind === "number"
                        ? Number(e.target.value)
                        : field.kind === "code"
                          ? slug(e.target.value)
                          : e.target.value,
                    )
                  }
                  slotProps={{ htmlInput: { maxLength: field.kind === "code" ? 32 : 255 } }}
                />
              );
            })}
            {editing && (
              <FormControlLabel
                label="Active"
                control={
                  <Switch
                    checked={!!values.is_active}
                    onChange={(e) => set("is_active", e.target.checked)}
                  />
                }
              />
            )}
            {fieldErrors.is_active && <Alert severity="error">{fieldErrors.is_active}</Alert>}
            {editing && existing.is_active && !values.is_active && (
              <Alert severity="warning">
                {kind === "bed"
                  ? "An inactive bed is marked out of service and cannot be used."
                  : "Everything inside it must be deactivated first. Nothing is deleted; it stays in the history."}
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={mutation.isPending || missing}>
            Save
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
