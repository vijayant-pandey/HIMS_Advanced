import { Alert, Checkbox, FormControlLabel, MenuItem, TextField, Typography } from "@mui/material";
import { useState } from "react";

import { FormDialog } from "../../components/FormDialog";
import { useReportIncident } from "./api";

export const SEVERITIES = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
] as const;

type Severity = (typeof SEVERITIES)[number]["value"];

/** Any signed-in person can report (HIPAA 164.308(a)(6), DPDP Rule 7, CERT-In; HIMS-COMP-004). */
export function ReportIncidentDialog({ onClose }: { onClose: () => void }) {
  const report = useReportIncident(useState(() => crypto.randomUUID())[0]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState<Severity>("medium");
  const [personalData, setPersonalData] = useState(false);

  return (
    <FormDialog
      title="Report a security incident"
      error={report.error}
      fields={["title", "description", "severity", "personal_data_affected"]}
      submitLabel={report.isSuccess ? "Close" : "Send report"}
      submitDisabled={!report.isSuccess && (!title.trim() || !description.trim())}
      pending={report.isPending}
      onClose={onClose}
      onSubmit={() =>
        report.isSuccess
          ? onClose()
          : report.mutate({
              title: title.trim(),
              description: description.trim(),
              severity,
              personal_data_affected: personalData,
            })
      }
    >
      {report.isSuccess ? (
        <Alert severity="success">
          Thank you. The compliance team has been told. Reference: {report.data.id}. Do not delete anything; they may
          contact you.
        </Alert>
      ) : (
        <>
          <Typography variant="body2">
            Report anything that may have exposed data or accounts: a lost laptop, a stolen password, a suspicious
            email, a wrong person seeing a record. Report at once, even if you are not sure: some legal deadlines are
            only hours long. Please do not write patient details here.
          </Typography>
          <TextField label="What happened, in a few words" required value={title} onChange={(e) => setTitle(e.target.value)} />
          <TextField
            label="Details"
            required
            multiline
            minRows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            helperText="When, where, which system or device. No patient details."
          />
          <TextField select label="How serious does it look?" value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
            {SEVERITIES.map((s) => (
              <MenuItem key={s.value} value={s.value}>
                {s.label}
              </MenuItem>
            ))}
          </TextField>
          <FormControlLabel
            control={<Checkbox checked={personalData} onChange={(e) => setPersonalData(e.target.checked)} />}
            label="Personal or patient data may be affected"
          />
        </>
      )}
    </FormDialog>
  );
}
