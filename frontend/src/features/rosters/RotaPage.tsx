import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  FormGroup,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { AddShiftsResult, RotaPerson, RotaWeek, Shift, ShiftType } from "../../api/types";
import { localDate } from "../../components/dates";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { useAllDepartments } from "../staff/api";
import {
  useAddShifts,
  useCancelShift,
  useCopyWeek,
  useCreateShiftType,
  useRotaNow,
  useRotaWeek,
  useShiftTypes,
  useUpdateShiftType,
} from "./api";
import { WEEKDAYS, addDays, clock, formatDay, mondayOf } from "./labels";

/** HIMS-STAFF-012: one department's week, who is on call now, and the hospital's shift types. */
export function RotaPage() {
  const [tab, setTab] = useState<"week" | "types">("week");
  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Rota
        </Typography>
        <Typography variant="body2">
          Who works which shift and who is on call, department by department. Times are on the facility's clock.
        </Typography>
      </Box>
      <OnCallNow />
      <Tabs value={tab} onChange={(_, value) => setTab(value)}>
        <Tab value="week" label="Week" />
        <Tab value="types" label="Shift types" />
      </Tabs>
      {tab === "week" ? <WeekTab /> : <ShiftTypesTab />}
    </Stack>
  );
}

function OnCallNow() {
  const { data, error } = useRotaNow();
  if (error) return <ErrorAlert error={error} />;
  if (!data) return null;
  return (
    <Paper sx={{ p: 2 }} component="section" aria-label="On call now">
      <Typography variant="subtitle2" component="h2" sx={{ mb: 1 }}>
        On call now
      </Typography>
      {data.on_call.length === 0 ? (
        <Typography variant="body2">Nobody is on call right now in the departments you can see.</Typography>
      ) : (
        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", rowGap: 1 }}>
          {data.on_call.map((s) => (
            <Chip
              key={s.id}
              color="secondary"
              label={`${s.department_name}: ${s.staff_name} · until ${s.hours.split("-")[1]}`}
            />
          ))}
        </Stack>
      )}
      <Typography variant="caption" component="p" sx={{ mt: 1 }}>
        {data.working.length} {data.working.length === 1 ? "person is" : "people are"} on a working shift now.
      </Typography>
    </Paper>
  );
}

function WeekTab() {
  const departments = useAllDepartments();
  const active = (departments.data?.results ?? []).filter((d) => d.status === "active");
  const [chosen, setChosen] = useState("");
  const department = chosen || active[0]?.id || "";
  const [start, setStart] = useState(() => mondayOf(localDate()));
  const week = useRotaWeek(department, start);
  const [adding, setAdding] = useState<{ person?: RotaPerson; day?: string } | null>(null);
  const [cancelling, setCancelling] = useState<Shift | null>(null);
  const [copying, setCopying] = useState(false);
  const data = week.data;

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
        <TextField
          select
          size="small"
          label="Department"
          value={department}
          onChange={(e) => setChosen(e.target.value)}
          sx={{ minWidth: 260 }}
        >
          {active.map((d) => (
            <MenuItem key={d.id} value={d.id}>
              {d.name} · {d.facility_name}
            </MenuItem>
          ))}
        </TextField>
        <Button onClick={() => setStart(addDays(start, -7))}>Previous week</Button>
        <Button onClick={() => setStart(mondayOf(localDate()))}>This week</Button>
        <Button onClick={() => setStart(addDays(start, 7))}>Next week</Button>
        <Box sx={{ flexGrow: 1 }} />
        {data?.can_manage && (
          <>
            <Button variant="outlined" onClick={() => setCopying(true)}>
              Copy previous week here
            </Button>
            <Button variant="contained" onClick={() => setAdding({})}>
              Plan shifts
            </Button>
          </>
        )}
      </Stack>
      {departments.error && <ErrorAlert error={departments.error} />}
      {week.error && <ErrorAlert error={week.error} />}
      {(departments.isPending || week.isFetching) && <LinearProgress aria-label="Loading the rota" />}
      {!departments.isPending && active.length === 0 && <Alert severity="info">No departments to show.</Alert>}
      {data && <WeekGrid week={data} onAdd={setAdding} onCancel={setCancelling} />}
      {data && adding && <AddShiftsDialog week={data} initial={adding} onClose={() => setAdding(null)} />}
      {cancelling && <CancelShiftDialog shift={cancelling} onClose={() => setCancelling(null)} />}
      {data && copying && <CopyWeekDialog week={data} onClose={() => setCopying(false)} />}
    </Stack>
  );
}

function WeekGrid({
  week,
  onAdd,
  onCancel,
}: {
  week: RotaWeek;
  onAdd: (target: { person: RotaPerson; day: string }) => void;
  onCancel: (shift: Shift) => void;
}) {
  const today = localDate();
  return (
    <TableContainer component={Paper}>
      <Table size="small" aria-label={`Rota for ${week.department_name}`}>
        <TableHead>
          <TableRow>
            <TableCell>Person</TableCell>
            {week.days.map((day) => (
              <TableCell key={day} sx={day === today ? { fontWeight: 700 } : undefined}>
                {formatDay(day)}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {week.people.map((person) => (
            <TableRow key={person.staff_id}>
              <TableCell>
                {person.name}
                {person.designation && (
                  <Typography variant="caption" component="p">
                    {person.designation}
                  </Typography>
                )}
              </TableCell>
              {week.days.map((day) => {
                const shifts = person.shifts.filter((s) => s.on_date === day && s.status === "scheduled");
                const away = person.away.find((a) => a.start_date <= day && a.end_date >= day);
                return (
                  <TableCell key={day} sx={{ verticalAlign: "top", minWidth: 110 }}>
                    <Stack spacing={0.5}>
                      {away && (
                        <Chip
                          size="small"
                          variant="outlined"
                          color={away.status === "approved" ? "default" : "warning"}
                          label={
                            (away.status === "approved" ? "On leave" : "Leave asked") +
                            (away.leave_type_label ? ` · ${away.leave_type_label}` : "")
                          }
                        />
                      )}
                      {shifts.map((s) => (
                        <Chip
                          key={s.id}
                          size="small"
                          color={s.kind === "on_call" ? "secondary" : "primary"}
                          title={s.note || undefined}
                          label={`${s.shift_type_name} ${s.hours}`}
                          onClick={week.can_manage ? () => onCancel(s) : undefined}
                          aria-label={
                            week.can_manage
                              ? `${s.shift_type_name} ${s.hours}, ${person.name}, ${formatDay(day)}: cancel`
                              : undefined
                          }
                        />
                      ))}
                      {week.can_manage && day >= today && (
                        <Button
                          size="small"
                          aria-label={`Plan a shift for ${person.name} on ${formatDay(day)}`}
                          onClick={() => onAdd({ person, day })}
                          sx={{ minWidth: 0, alignSelf: "flex-start" }}
                        >
                          +
                        </Button>
                      )}
                    </Stack>
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
          {week.people.length === 0 && (
            <TableRow>
              <TableCell colSpan={8}>
                Nobody is posted in {week.department_name} this week. Post staff on the Staff page first.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function SkippedList({ result }: { result: AddShiftsResult }) {
  if (result.skipped.length === 0) return null;
  return (
    <Alert severity="warning">
      {result.created.length} planned. Not planned:
      <Box component="ul" sx={{ m: 0, pl: 2 }}>
        {result.skipped.map((s) => (
          <li key={`${s.person}-${s.on_date}`}>
            {formatDay(s.on_date)}, {s.person}: {s.reason}
          </li>
        ))}
      </Box>
    </Alert>
  );
}

function AddShiftsDialog({
  week,
  initial,
  onClose,
}: {
  week: RotaWeek;
  initial: { person?: RotaPerson; day?: string };
  onClose: () => void;
}) {
  const add = useAddShifts(useState(() => crypto.randomUUID())[0]);
  const types = useShiftTypes(true);
  const [person, setPerson] = useState(initial.person?.staff_id ?? "");
  const [shiftType, setShiftType] = useState("");
  const [from, setFrom] = useState(initial.day ?? localDate());
  const [to, setTo] = useState(initial.day ?? "");
  const [weekdays, setWeekdays] = useState<number[]>([0, 1, 2, 3, 4, 5, 6]);
  const [note, setNote] = useState("");
  const several = !!to && to !== from;
  if (add.data && add.data.skipped.length > 0) {
    return (
      <FormDialog title="Shifts planned" error={null} pending={false} submitLabel="Done" onClose={onClose} onSubmit={onClose}>
        <SkippedList result={add.data} />
      </FormDialog>
    );
  }
  return (
    <FormDialog
      title={`Plan shifts · ${week.department_name}`}
      error={add.error}
      fields={["staff", "shift_type", "from_date", "to_date", "weekdays", "note"]}
      submitLabel="Plan"
      submitDisabled={!person || !shiftType || !from}
      pending={add.isPending}
      onClose={onClose}
      onSubmit={() =>
        add.mutate(
          {
            staff: person,
            department: week.department_id,
            shift_type: shiftType,
            from_date: from,
            to_date: to || from,
            weekdays: several ? weekdays : undefined,
            note: note.trim(),
          },
          { onSuccess: (result) => result.skipped.length === 0 && onClose() },
        )
      }
    >
      <TextField select label="Person" required value={person} onChange={(e) => setPerson(e.target.value)}>
        {week.people.map((p) => (
          <MenuItem key={p.staff_id} value={p.staff_id}>
            {p.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField select label="Shift" required value={shiftType} onChange={(e) => setShiftType(e.target.value)}>
        {(types.data ?? []).map((t) => (
          <MenuItem key={t.id} value={t.id}>
            {t.name} · {clock(t.start_time)}–{clock(t.end_time)}
            {t.kind === "on_call" ? " (on call)" : ""}
          </MenuItem>
        ))}
      </TextField>
      <Stack direction="row" spacing={2}>
        <TextField
          type="date"
          label="First day"
          required
          value={from}
          onChange={(e) => setFrom(e.target.value)}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: localDate() } }}
          fullWidth
        />
        <TextField
          type="date"
          label="Last day (optional)"
          value={to}
          onChange={(e) => setTo(e.target.value)}
          helperText="For several days; at most 62"
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: from } }}
          fullWidth
        />
      </Stack>
      {several && (
        <FormGroup row aria-label="On these weekdays">
          {WEEKDAYS.map((name, index) => (
            <FormControlLabel
              key={name}
              label={name}
              control={
                <Checkbox
                  checked={weekdays.includes(index)}
                  onChange={(e) =>
                    setWeekdays((current) =>
                      e.target.checked ? [...current, index] : current.filter((d) => d !== index),
                    )
                  }
                />
              }
            />
          ))}
        </FormGroup>
      )}
      <TextField
        label="Note (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        helperText="Seen by everyone who sees the rota. No patient details."
      />
    </FormDialog>
  );
}

function CancelShiftDialog({ shift, onClose }: { shift: Shift; onClose: () => void }) {
  const cancel = useCancelShift(shift.id);
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`Cancel shift · ${shift.staff_name}`}
      error={cancel.error}
      fields={["reason"]}
      submitLabel="Cancel shift"
      submitColor="error"
      submitDisabled={!reason.trim()}
      pending={cancel.isPending}
      onClose={onClose}
      onSubmit={() => cancel.mutate({ version: shift.version, reason: reason.trim() }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        {shift.shift_type_name} on {formatDay(shift.on_date)}, {shift.hours}. It stays on record as cancelled.
      </Typography>
      <TextField
        label="Why?"
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        helperText="e.g. Swapped with Ravi"
      />
    </FormDialog>
  );
}

function CopyWeekDialog({ week, onClose }: { week: RotaWeek; onClose: () => void }) {
  const copy = useCopyWeek(useState(() => crypto.randomUUID())[0]);
  const from = addDays(week.start, -7);
  if (copy.data) {
    return (
      <FormDialog title="Week copied" error={null} pending={false} submitLabel="Done" onClose={onClose} onSubmit={onClose}>
        <Typography variant="body2">{copy.data.created.length} shift(s) planned.</Typography>
        <SkippedList result={copy.data} />
      </FormDialog>
    );
  }
  return (
    <FormDialog
      title={`Copy a week · ${week.department_name}`}
      error={copy.error}
      submitLabel="Copy"
      pending={copy.isPending}
      onClose={onClose}
      onSubmit={() => copy.mutate({ department: week.department_id, from_start: from, to_start: week.start })}
    >
      <Typography variant="body2">
        Every shift planned in the week of {formatDay(from)} is planned again on the same weekday in the week of{" "}
        {formatDay(week.start)}. People on leave, no longer posted here or already busy are skipped and listed.
      </Typography>
    </FormDialog>
  );
}

function ShiftTypesTab() {
  const { data: user } = useCurrentUser();
  const canManage = hasOrganizationWidePermission(user, "rota.manage");
  const types = useShiftTypes();
  const [editing, setEditing] = useState<ShiftType | "new" | null>(null);
  return (
    <Stack spacing={2}>
      <Stack direction="row" sx={{ alignItems: "center" }}>
        <Typography variant="body2" sx={{ flexGrow: 1 }}>
          The kinds of shift used across the hospital. A change applies to shifts planned afterwards.
        </Typography>
        {canManage && (
          <Button variant="contained" onClick={() => setEditing("new")}>
            Add shift type
          </Button>
        )}
      </Stack>
      {types.error && <ErrorAlert error={types.error} />}
      <TableContainer component={Paper}>
        <Table size="small" aria-label="Shift types">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Kind</TableCell>
              <TableCell>Hours</TableCell>
              <TableCell>Status</TableCell>
              {canManage && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {types.data?.map((t) => (
              <TableRow key={t.id}>
                <TableCell>
                  {t.name}
                  <Typography variant="caption" component="p">
                    {t.code}
                    {t.is_custom ? " · added by the hospital" : ""}
                  </Typography>
                </TableCell>
                <TableCell>{t.kind_label}</TableCell>
                <TableCell>
                  {clock(t.start_time)}–{clock(t.end_time)} ({Math.round(t.minutes / 6) / 10} h)
                </TableCell>
                <TableCell>{t.is_active ? "In use" : "Switched off"}</TableCell>
                {canManage && (
                  <TableCell>
                    <Button size="small" onClick={() => setEditing(t)} aria-label={`Edit ${t.name}`}>
                      Edit
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {editing && <ShiftTypeDialog shiftType={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </Stack>
  );
}

function ShiftTypeDialog({ shiftType, onClose }: { shiftType: ShiftType | null; onClose: () => void }) {
  const create = useCreateShiftType(useState(() => crypto.randomUUID())[0]);
  const update = useUpdateShiftType(shiftType?.id ?? "");
  const save = shiftType ? update : create;
  const [values, setValues] = useState({
    code: "",
    name: shiftType?.name ?? "",
    kind: shiftType?.kind ?? "shift",
    start_time: clock(shiftType?.start_time ?? "08:00"),
    end_time: clock(shiftType?.end_time ?? "14:00"),
    is_active: shiftType?.is_active ?? true,
  });
  const set = (field: string, value: string | boolean) => setValues({ ...values, [field]: value });
  return (
    <FormDialog
      title={shiftType ? `Edit ${shiftType.name}` : "Add shift type"}
      error={save.error}
      fields={["code", "name", "kind", "start_time", "end_time"]}
      submitDisabled={!values.name.trim() || (!shiftType && !values.code)}
      pending={save.isPending}
      onClose={onClose}
      onSubmit={() => {
        const { code, ...rest } = values;
        if (shiftType) update.mutate({ version: shiftType.version, ...rest }, { onSuccess: onClose });
        else create.mutate({ code, name: rest.name, kind: rest.kind, start_time: rest.start_time, end_time: rest.end_time }, { onSuccess: onClose });
      }}
    >
      {!shiftType && (
        <TextField
          label="Code"
          required
          value={values.code}
          onChange={(e) => set("code", e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))}
          helperText="Short, never changes, e.g. theatre-long"
        />
      )}
      <TextField label="Name" required value={values.name} onChange={(e) => set("name", e.target.value)} />
      <TextField select label="Kind" value={values.kind} onChange={(e) => set("kind", e.target.value)}>
        <MenuItem value="shift">Working shift</MenuItem>
        <MenuItem value="on_call">On call</MenuItem>
      </TextField>
      <Stack direction="row" spacing={2}>
        <TextField
          type="time"
          label="Starts"
          value={values.start_time}
          onChange={(e) => set("start_time", e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          fullWidth
        />
        <TextField
          type="time"
          label="Ends"
          value={values.end_time}
          onChange={(e) => set("end_time", e.target.value)}
          helperText="Earlier than the start = the next day"
          slotProps={{ inputLabel: { shrink: true } }}
          fullWidth
        />
      </Stack>
      {shiftType && (
        <FormControlLabel
          control={<Switch checked={values.is_active} onChange={(e) => set("is_active", e.target.checked)} />}
          label="In use (switched-off types cannot be planned)"
        />
      )}
    </FormDialog>
  );
}
