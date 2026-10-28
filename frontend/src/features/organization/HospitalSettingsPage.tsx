import { Alert, Box, Button, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, api } from "../../api/client";
import type { Organization, OrganizationUpdateRequest } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { currentUserKey, useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";

const organizationKey = ["organization"] as const;

const COUNTRY: Record<string, string> = { IN: "India", US: "United States" };
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

function useOrganization() {
  return useQuery<Organization, ApiError>({
    queryKey: organizationKey,
    queryFn: ({ signal }) => api.get<Organization>("/organization/", { signal }),
  });
}

function EditDialog({ organization, onClose }: { organization: Organization; onClose: () => void }) {
  const queryClient = useQueryClient();
  const update = useMutation<Organization, ApiError, OrganizationUpdateRequest>({
    mutationFn: (body) => api.patch<Organization>("/organization/", body),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: organizationKey });
      void queryClient.invalidateQueries({ queryKey: currentUserKey }); // name shown in the app
    },
  });
  const [values, setValues] = useState({
    display_name: organization.display_name,
    legal_name: organization.legal_name,
    default_timezone: organization.default_timezone,
  });
  const errors = fieldErrors(update.error);
  const zones = [...new Set([...(TIME_ZONES[organization.country] ?? []), organization.default_timezone])];

  return (
    <FormDialog
      title="Edit hospital details"
      error={update.error}
      fields={Object.keys(values)}
      submitDisabled={!values.display_name.trim() || !values.legal_name.trim()}
      pending={update.isPending}
      onClose={onClose}
      onSubmit={() => update.mutate({ version: organization.version, ...values }, { onSuccess: onClose })}
    >
      <TextField
        label="Name shown in HIMS"
        required
        value={values.display_name}
        onChange={(e) => setValues({ ...values, display_name: e.target.value })}
        error={!!errors.display_name}
        helperText={errors.display_name ?? "e.g. Sunrise Hospitals"}
      />
      <TextField
        label="Legal name"
        required
        value={values.legal_name}
        onChange={(e) => setValues({ ...values, legal_name: e.target.value })}
        error={!!errors.legal_name}
        helperText={errors.legal_name ?? "As registered, e.g. for invoices: Sunrise Healthcare Pvt Ltd"}
      />
      <TextField
        select
        label="Default time zone"
        value={values.default_timezone}
        onChange={(e) => setValues({ ...values, default_timezone: e.target.value })}
        error={!!errors.default_timezone}
        helperText={errors.default_timezone ?? "Used where a facility has no time zone of its own"}
      >
        {zones.map((zone) => (
          <MenuItem key={zone} value={zone}>
            {zone}
          </MenuItem>
        ))}
      </TextField>
      <Alert severity="info">
        Country and currency are fixed when the hospital is set up and cannot be changed here.
      </Alert>
    </FormDialog>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", gap: 2, py: 0.5 }}>
      <Typography variant="body2" sx={{ minWidth: 200, color: "text.secondary" }}>
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Box>
  );
}

/** HIMS-ORG-005: the hospital's own details (one hospital per deployment). */
export function HospitalSettingsPage() {
  const { data: user } = useCurrentUser();
  const { data: organization, isPending, error } = useOrganization();
  const [editing, setEditing] = useState(false);
  const canEdit = hasOrganizationWidePermission(user, "organization.manage");

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="h5" component="h1">
          Hospital settings
        </Typography>
        {canEdit && organization && (
          <Button variant="contained" onClick={() => setEditing(true)}>
            Edit
          </Button>
        )}
      </Box>
      {isPending && <LinearProgress />}
      {error && <ErrorAlert error={error} />}
      {organization && (
        <Paper sx={{ p: 2 }}>
          <Row label="Name shown in HIMS" value={organization.display_name} />
          <Row label="Legal name" value={organization.legal_name} />
          <Row label="Country" value={COUNTRY[organization.country] ?? organization.country} />
          <Row label="Currency" value={organization.default_currency} />
          <Row label="Default time zone" value={organization.default_timezone} />
          <Row label="Status" value={organization.status === "active" ? "Active" : "Suspended"} />
          <Typography variant="caption" component="p" sx={{ mt: 1 }}>
            Branch details are on the Facilities page; numbering and features have their own pages.
          </Typography>
        </Paper>
      )}
      {editing && organization && <EditDialog organization={organization} onClose={() => setEditing(false)} />}
    </Stack>
  );
}
