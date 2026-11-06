import { MenuItem, Stack, TextField } from "@mui/material";

import { LEAVE_TYPES } from "./labels";

/** Kind, first and last day, and note: shared with "Ask for leave" on My schedule. */
export function LeaveFields({
  values,
  set,
}: {
  values: { leave_type: string; start_date: string; end_date: string; reason: string };
  set: (field: string, value: string) => void;
}) {
  return (
    <>
      <TextField select label="Kind of leave" required value={values.leave_type} onChange={(e) => set("leave_type", e.target.value)}>
        {LEAVE_TYPES.map((t) => (
          <MenuItem key={t.value} value={t.value}>
            {t.label}
          </MenuItem>
        ))}
      </TextField>
      <Stack direction="row" spacing={2}>
        <TextField
          type="date"
          label="First day"
          required
          value={values.start_date}
          onChange={(e) => set("start_date", e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          fullWidth
        />
        <TextField
          type="date"
          label="Last day"
          required
          value={values.end_date}
          onChange={(e) => set("end_date", e.target.value)}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: values.start_date } }}
          fullWidth
        />
      </Stack>
      <TextField
        label="Note (optional)"
        value={values.reason}
        onChange={(e) => set("reason", e.target.value)}
        helperText="No medical details: the kind of leave is enough."
      />
    </>
  );
}
