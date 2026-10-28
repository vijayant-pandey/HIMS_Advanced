import {
  Alert,
  Box,
  Checkbox,
  FormControlLabel,
  FormGroup,
  MenuItem,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { PermissionsEnum, Role, RoleAssignment } from "../../api/types";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { useFacilities } from "../facilities/api";
import { useAllDepartments } from "../staff/api";
import {
  useCreateRole,
  useGrantRole,
  usePermissions,
  useRevokeAssignment,
  useRoles,
  useUpdateRole,
} from "./api";

function useIdempotencyKey() {
  return useState(() => crypto.randomUUID())[0];
}

type Scope = "organization" | "facility" | "department";

// --- Grant a role ---------------------------------------------------------------------------

export function GrantRoleDialog({
  userId,
  personName,
  onClose,
}: {
  userId: string;
  personName: string;
  onClose: () => void;
}) {
  const grant = useGrantRole(useIdempotencyKey());
  const roles = useRoles();
  const facilities = useFacilities();
  const departments = useAllDepartments();
  const [role, setRole] = useState("");
  const [scope, setScope] = useState<Scope>("facility");
  const [facility, setFacility] = useState("");
  const [department, setDepartment] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [reason, setReason] = useState("");

  const facilityDepartments = (departments.data?.results ?? []).filter(
    (d) => d.facility === facility,
  );
  const scopeComplete =
    scope === "organization" ||
    (scope === "facility" && !!facility) ||
    (scope === "department" && !!facility && !!department);

  return (
    <FormDialog
      title={`Give access · ${personName}`}
      error={grant.error}
      fields={["role", "facility", "department", "valid_until", "reason"]}
      submitLabel="Give access"
      submitDisabled={!role || !scopeComplete || !reason.trim()}
      pending={grant.isPending}
      onClose={onClose}
      onSubmit={() =>
        grant.mutate(
          {
            user: userId,
            role,
            facility: scope === "organization" ? null : facility,
            department: scope === "department" ? department : null,
            valid_until: validUntil ? new Date(`${validUntil}T23:59:59`).toISOString() : null,
            reason: reason.trim(),
          },
          { onSuccess: onClose },
        )
      }
    >
      <TextField
        select
        label="Role"
        required
        value={role}
        onChange={(e) => setRole(e.target.value)}
        helperText={roles.data?.results.find((r) => r.id === role)?.description}
      >
        {(roles.data?.results ?? []).map((r) => (
          <MenuItem key={r.id} value={r.id}>
            {r.name}
          </MenuItem>
        ))}
      </TextField>
      <Box>
        <Typography variant="body2" sx={{ mb: 0.5 }}>
          Where it applies
        </Typography>
        <RadioGroup row value={scope} onChange={(e) => setScope(e.target.value as Scope)}>
          <FormControlLabel value="organization" control={<Radio />} label="Whole hospital" />
          <FormControlLabel value="facility" control={<Radio />} label="One facility" />
          <FormControlLabel value="department" control={<Radio />} label="One department" />
        </RadioGroup>
      </Box>
      {scope !== "organization" && (
        <Stack direction="row" spacing={2}>
          <TextField
            select
            label="Facility"
            required
            fullWidth
            value={facility}
            onChange={(e) => {
              setFacility(e.target.value);
              setDepartment("");
            }}
          >
            {(facilities.data?.results ?? []).map((f) => (
              <MenuItem key={f.id} value={f.id}>
                {f.name}
              </MenuItem>
            ))}
          </TextField>
          {scope === "department" && (
            <TextField
              select
              label="Department"
              required
              fullWidth
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              disabled={!facility}
            >
              {facilityDepartments.map((d) => (
                <MenuItem key={d.id} value={d.id}>
                  {d.name}
                </MenuItem>
              ))}
            </TextField>
          )}
        </Stack>
      )}
      <TextField
        label="Ends on (optional)"
        type="date"
        value={validUntil}
        onChange={(e) => setValidUntil(e.target.value)}
        helperText="For temporary cover, e.g. a locum. Leave empty for no end date."
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <TextField
        label="Reason"
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        helperText="e.g. Joined as staff nurse in ICU. Kept in the audit log."
      />
      <Alert severity="info">
        You can only give access you hold yourself for that place. Roles that can change settings
        require the person to use two-factor sign-in.
      </Alert>
    </FormDialog>
  );
}

// --- Revoke ---------------------------------------------------------------------------------

export function RevokeDialog({
  assignment,
  onClose,
}: {
  assignment: RoleAssignment;
  onClose: () => void;
}) {
  const revoke = useRevokeAssignment(assignment.id);
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`Remove access · ${assignment.role_name}`}
      error={revoke.error}
      fields={["reason"]}
      submitLabel="Remove access"
      submitColor="error"
      submitDisabled={!reason.trim()}
      pending={revoke.isPending}
      onClose={onClose}
      onSubmit={() => revoke.mutate({ reason: reason.trim() }, { onSuccess: onClose })}
      maxWidth="xs"
    >
      <Typography variant="body2">
        {assignment.user_display_name} will lose this role immediately. The record stays in the
        history.
      </Typography>
      <TextField
        label="Reason"
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        helperText="e.g. Moved to another department."
      />
    </FormDialog>
  );
}

// --- Create or edit a custom role -----------------------------------------------------------

function area(codename: string) {
  const first = codename.split(".")[0] ?? codename;
  return first.charAt(0).toUpperCase() + first.slice(1);
}

export function RoleDialog({ role, onClose }: { role?: Role; onClose: () => void }) {
  const editing = role !== undefined;
  const permissions = usePermissions();
  const create = useCreateRole(useIdempotencyKey());
  const update = useUpdateRole(role?.id ?? "");
  const mutation = editing ? update : create;
  const [name, setName] = useState(role?.name ?? "");
  const [code, setCode] = useState(role?.code ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [chosen, setChosen] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const errors = fieldErrors(mutation.error);

  const groups = new Map<string, { codename: string; description: string }[]>();
  for (const permission of permissions.data ?? []) {
    const key = area(permission.codename);
    groups.set(key, [...(groups.get(key) ?? []), permission]);
  }
  const toggle = (codename: string) =>
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(codename)) next.delete(codename);
      else next.add(codename);
      return next;
    });
  const selected = [...chosen].sort() as PermissionsEnum[];

  return (
    <FormDialog
      title={editing ? `Edit role · ${role.name}` : "New custom role"}
      error={mutation.error}
      fields={["name", "code", "description", "permissions"]}
      submitDisabled={!name.trim() || (!editing && !code) || selected.length === 0}
      pending={mutation.isPending}
      onClose={onClose}
      maxWidth="md"
      onSubmit={() =>
        editing
          ? update.mutate(
              { version: role.version, name: name.trim(), description, permissions: selected },
              { onSuccess: onClose },
            )
          : create.mutate(
              { code, name: name.trim(), description, permissions: selected },
              { onSuccess: onClose },
            )
      }
    >
      <Stack direction="row" spacing={2}>
        <TextField
          label="Name"
          required
          fullWidth
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={!!errors.name}
          helperText={errors.name ?? "e.g. Ward clerk with staff view"}
        />
        {!editing && (
          <TextField
            label="Code"
            required
            fullWidth
            value={code}
            onChange={(e) =>
              setCode(e.target.value.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9_-]/g, ""))
            }
            error={!!errors.code}
            helperText={errors.code ?? "Short id, cannot change later, e.g. ward-clerk-plus"}
          />
        )}
      </Stack>
      <TextField
        label="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        multiline
        minRows={2}
      />
      {editing && role.active_assignments > 0 && (
        <Alert severity="warning">
          {role.active_assignments} person(s) hold this role; they get the new permissions at their
          next request.
        </Alert>
      )}
      {errors.permissions && <Alert severity="error">{errors.permissions}</Alert>}
      <Typography variant="subtitle2">What people with this role can do</Typography>
      {[...groups.entries()].map(([group, items]) => (
        <Box key={group}>
          <Typography variant="caption" sx={{ fontWeight: 600 }}>
            {group}
          </Typography>
          <FormGroup>
            {items.map((p) => (
              <FormControlLabel
                key={p.codename}
                control={
                  <Checkbox
                    size="small"
                    checked={chosen.has(p.codename)}
                    onChange={() => toggle(p.codename)}
                  />
                }
                label={
                  <span>
                    {p.description}{" "}
                    <Typography component="span" variant="caption">
                      ({p.codename})
                    </Typography>
                  </span>
                }
              />
            ))}
          </FormGroup>
        </Box>
      ))}
    </FormDialog>
  );
}
