import { Alert, Box, Chip, Paper, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

import type { PatientDetail } from "../../api/types";
import { ALLERGY_STATUS, SEX } from "./labels";

/**
 * The chart header (HIMS-PAT-005; P0 part 01 section 7): name, MRN, age and sex, allergies and
 * the flags that change how staff act (restricted record: HIMS-PAT-006). It stays in view below
 * the menu bar on every tab. `actions` go on the right (e.g. Restrict record).
 */
export function ChartHeader({ patient, actions }: { patient: PatientDetail; actions?: ReactNode }) {
  return (
    <Paper
      variant="outlined"
      component="section"
      aria-label="Patient header"
      sx={{ p: 2, position: "sticky", top: "var(--hims-app-bar-height, 0px)", zIndex: 2 }}
    >
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
        <Typography variant="h5" component="h1" sx={{ mr: 1 }}>
          {patient.name}
        </Typography>
        <Chip label={patient.mrn} />
        <Chip label={`${patient.birth_date_estimated ? "~" : ""}${patient.age} · ${SEX[patient.sex]}`} variant="outlined" />
        <Chip color="warning" variant="outlined" label={ALLERGY_STATUS[patient.allergy_status] ?? patient.allergy_status} />
        {patient.is_restricted && <Chip color="error" label="Restricted record" />}
        {patient.is_unknown && <Chip color="warning" label="Unknown patient" />}
        {patient.status === "merged" && <Chip label={`Merged into ${patient.merged_into_mrn}`} />}
        {patient.preferred_name && (
          <Typography variant="body2" color="text.secondary">
            Prefers “{patient.preferred_name}”
          </Typography>
        )}
        {actions && <Box sx={{ ml: "auto" }}>{actions}</Box>}
      </Stack>
    </Paper>
  );
}

/** What staff must notice on opening the record (from the server, most important first). */
export function ChartAlerts({ patient }: { patient: PatientDetail }) {
  if (patient.alerts.length === 0) return null;
  return (
    <Stack spacing={1}>
      {patient.alerts.map((alert) => (
        <Alert key={alert.code} severity={alert.severity}>
          {alert.message}
        </Alert>
      ))}
    </Stack>
  );
}
