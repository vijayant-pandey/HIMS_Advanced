import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { AppliesOn, RotaWeek, StaffingRequirement, StaffType } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { fieldErrors } from "../../components/FormDialog";
import { useSaveRequirement, useShiftTypes, useStaffingRequirements } from "./api";
import { clock, formatDay } from "./labels";

const STAFF_TYPES: Record<StaffType, string> = {
  doctor: "Doctors",
  nurse: "Nurses",
  pharmacist: "Pharmacists",
  lab_technician: "Laboratory technicians",
  radiologist: "Radiologists",
  dietitian: "Dietitians",
  administrator: "Administrators",
  support: "Support staff",
};

const APPLIES_ON: Record<AppliesOn, string> = {
  every_day: "Every day",
  weekdays: "Monday to Friday",
  weekends: "Saturday and Sunday",
};

/** Shifts this week below the hospital's minimum (HIMS-STAFF-015). A warning: planning still works. */
export function StaffingGaps({ week }: { week: RotaWeek }) {
  if (week.staffing_gaps.length === 0) return null;
  return (
    <Alert severity="warning" role="region" aria-label="Staffing gaps">
      {week.staffing_gaps.length} shift(s) this week below the minimum:
      <Box component="ul" sx={{ m: 0, pl: 2 }}>
        {week.staffing_gaps.map((gap) => (
          <li key={`${gap.on_date}-${gap.shift_type_id}-${gap.staff_type}`}>
            {formatDay(gap.on_date)}, {gap.shift_type_name}: {gap.planned} of {gap.minimum} planned
            {gap.staff_type ? ` (${gap.staff_type_label.toLowerCase()})` : ""}
          </li>
        ))}
      </Box>
    </Alert>
  );
}

function ActiveSwitch({ row }: { row: StaffingRequirement }) {
  const save = useSaveRequirement(row.id, useState(() => crypto.randomUUID())[0]);
  return (
    <>
      <Switch
        checked={row.is_active}
        disabled={save.isPending}
        slotProps={{ input: { "aria-label": `${row.shift_type_name}, ${row.applies_on_label}: in use` } }}
        onChange={(event) => save.mutate({ version: row.version, is_active: event.target.checked })}
      />
      {save.error && <ErrorAlert error={save.error} />}
    </>
  );
}

function MinimumCell({ row, canManage }: { row: StaffingRequirement; canManage: boolean }) {
  const save = useSaveRequirement(row.id, useState(() => crypto.randomUUID())[0]);
  const [value, setValue] = useState(String(row.minimum));
  if (!canManage) return <>{row.minimum}</>;
  const changed = Number(value) !== row.minimum && Number(value) >= 1;
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
      <TextField
        type="number"
        size="small"
        label="Minimum"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        slotProps={{ htmlInput: { min: 1, max: 999 } }}
        sx={{ width: 96 }}
      />
      {changed && (
        <Button
          size="small"
          disabled={save.isPending}
          onClick={() => save.mutate({ version: row.version, minimum: Number(value) })}
        >
          Save
        </Button>
      )}
      {save.error && <ErrorAlert error={save.error} />}
    </Stack>
  );
}

/** The hospital's own numbers for one department (HIMS-STAFF-015; spec 4.3). */
export function MinimumStaffingDialog({ week, onClose }: { week: RotaWeek; onClose: () => void }) {
  const rows = useStaffingRequirements(week.department_id);
  const types = useShiftTypes(true);
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const add = useSaveRequirement(undefined, idempotencyKey);
  const [shiftType, setShiftType] = useState("");
  const [staffType, setStaffType] = useState("");
  const [appliesOn, setAppliesOn] = useState<AppliesOn>("every_day");
  const [minimum, setMinimum] = useState("1");
  const errors = fieldErrors(add.error);
  const submit = () =>
    add.mutate(
      {
        department: week.department_id,
        shift_type: shiftType,
        staff_type: staffType,
        applies_on: appliesOn,
        minimum: Number(minimum),
      },
      {
        onSuccess: () => {
          setShiftType("");
          setIdempotencyKey(crypto.randomUUID());
        },
      },
    );
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Minimum staffing · {week.department_name}</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography variant="body2">
            The fewest people your hospital wants on each shift. HIMS has no numbers of its own. A shift below its
            minimum shows a warning here and emails planners; planning is never blocked.
          </Typography>
          {rows.error && <ErrorAlert error={rows.error} />}
          {rows.isPending && <LinearProgress aria-label="Loading minimum staffing" />}
          <Table size="small" aria-label="Minimum staffing">
            <TableHead>
              <TableRow>
                <TableCell>Shift</TableCell>
                <TableCell>Who counts</TableCell>
                <TableCell>Days</TableCell>
                <TableCell>Minimum</TableCell>
                <TableCell>In use</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.data?.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.shift_type_name}</TableCell>
                  <TableCell>{row.staff_type_label}</TableCell>
                  <TableCell>{row.applies_on_label}</TableCell>
                  <TableCell>
                    <MinimumCell key={row.version} row={row} canManage={week.can_manage} />
                  </TableCell>
                  <TableCell>
                    {week.can_manage ? <ActiveSwitch row={row} /> : row.is_active ? "Yes" : "No"}
                  </TableCell>
                </TableRow>
              ))}
              {rows.data?.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5}>No minimums set for this department.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          {week.can_manage && (
            <Stack
              component="section"
              aria-label="Add a minimum"
              direction="row"
              spacing={1}
              useFlexGap
              sx={{ flexWrap: "wrap", alignItems: "flex-start" }}
            >
              <TextField
                select
                size="small"
                label="Shift"
                value={shiftType}
                onChange={(event) => setShiftType(event.target.value)}
                error={!!errors.shift_type}
                helperText={errors.shift_type}
                sx={{ minWidth: 180 }}
              >
                {(types.data ?? []).map((type) => (
                  <MenuItem key={type.id} value={type.id}>
                    {type.name} · {clock(type.start_time)}–{clock(type.end_time)}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                label="Who counts"
                value={staffType}
                onChange={(event) => setStaffType(event.target.value)}
                sx={{ minWidth: 180 }}
              >
                <MenuItem value="">Anyone</MenuItem>
                {Object.entries(STAFF_TYPES).map(([value, label]) => (
                  <MenuItem key={value} value={value}>
                    {label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                label="Days"
                value={appliesOn}
                onChange={(event) => setAppliesOn(event.target.value as AppliesOn)}
                sx={{ minWidth: 180 }}
              >
                {Object.entries(APPLIES_ON).map(([value, label]) => (
                  <MenuItem key={value} value={value}>
                    {label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                type="number"
                size="small"
                label="At least"
                value={minimum}
                onChange={(event) => setMinimum(event.target.value)}
                error={!!errors.minimum}
                helperText={errors.minimum}
                slotProps={{ htmlInput: { min: 1, max: 999 } }}
                sx={{ width: 96 }}
              />
              <Button
                variant="contained"
                disabled={!shiftType || Number(minimum) < 1 || add.isPending}
                onClick={submit}
              >
                Add
              </Button>
            </Stack>
          )}
          {add.error && Object.keys(errors).length === 0 && <ErrorAlert error={add.error} />}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
