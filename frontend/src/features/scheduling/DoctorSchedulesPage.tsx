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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type {
  AddedException,
  DepartmentWeek,
  DoctorSchedule,
  OpdSession,
  ScheduleException,
  ScheduleExceptionKind,
  WeekDoctor,
} from "../../api/types";
import { localDate } from "../../components/dates";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { WEEKDAYS, addDays, formatDay, mondayOf } from "../rosters/labels";
import { useAllDepartments } from "../staff/api";
import {
  useAddException,
  useAddSessions,
  useCancelException,
  useChangeSession,
  useDepartmentWeek,
  useDoctorDay,
  useEndSession,
} from "./api";
import { EXCEPTION_KINDS, SESSION_STATUS, exceptionPeriod, offText } from "./labels";

/**
 * Doctor schedules (HIMS-OPD-001; spec 4.6): one department's doctors over a week, with their OPD
 * sessions and free slots. Doctors away, holidays and approved leave on the Leave page take
 * sessions off by themselves. Heads of department and OPD schedulers keep them; the front desk
 * sees them (and not why a doctor is away). Times are on the facility's clock.
 */
export function DoctorSchedulesPage() {
  const departments = useAllDepartments();
  const active = (departments.data?.results ?? []).filter((d) => d.status === "active");
  const [chosen, setChosen] = useState("");
  const department = chosen || active[0]?.id || "";
  const [start, setStart] = useState(() => mondayOf(localDate()));
  const week = useDepartmentWeek(department, start);
  const [adding, setAdding] = useState(false);
  const [recording, setRecording] = useState<ScheduleExceptionKind | null>(null);
  const [slots, setSlots] = useState<{ doctor: WeekDoctor; session: OpdSession } | null>(null);
  const data = week.data;

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Doctor schedules
        </Typography>
        <Typography variant="body2">
          Each doctor's OPD sessions and free slots, department by department. A doctor away, a holiday or leave
          approved on the Leave page takes sessions off by itself. Times are on the facility's clock.
        </Typography>
      </Box>
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
            <Button onClick={() => setRecording("leave")}>Doctor away</Button>
            <Button onClick={() => setRecording("holiday")}>Holiday</Button>
            <Button variant="outlined" onClick={() => setRecording("extra_session")}>
              Extra session
            </Button>
            <Button variant="contained" onClick={() => setAdding(true)}>
              Add weekly session
            </Button>
          </>
        )}
      </Stack>
      {departments.error && <ErrorAlert error={departments.error} />}
      {week.error && <ErrorAlert error={week.error} />}
      {(departments.isPending || week.isFetching) && <LinearProgress aria-label="Loading the doctor schedules" />}
      {!departments.isPending && active.length === 0 && <Alert severity="info">No departments to show.</Alert>}
      {data && <WeekGrid week={data} onSlots={(doctor, session) => setSlots({ doctor, session })} />}
      {data && <WeeklySessions week={data} />}
      {data && <Exceptions week={data} />}
      {data && adding && <AddSessionsDialog week={data} onClose={() => setAdding(false)} />}
      {data && recording && <ExceptionDialog week={data} kind={recording} onClose={() => setRecording(null)} />}
      {slots && <SlotsDialog {...slots} onClose={() => setSlots(null)} />}
    </Stack>
  );
}

function sessionLabel(session: OpdSession): string {
  const extra = session.source === "extra" ? " (extra)" : "";
  if (session.status === "off") return `${session.hours}${extra} · off`;
  return `${session.hours}${extra} · ${session.open_slots} slots`;
}

function WeekGrid({ week, onSlots }: { week: DepartmentWeek; onSlots: (d: WeekDoctor, s: OpdSession) => void }) {
  const today = localDate();
  return (
    <TableContainer component={Paper}>
      <Table size="small" aria-label={`Doctor schedules for ${week.department_name}`}>
        <TableHead>
          <TableRow>
            <TableCell>Doctor</TableCell>
            {week.days.map((day) => (
              <TableCell key={day} sx={day === today ? { fontWeight: 700 } : undefined}>
                {formatDay(day)}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {week.doctors.map((doctor) => (
            <TableRow key={doctor.staff_id}>
              <TableCell>
                {doctor.name}
                {doctor.designation && (
                  <Typography variant="caption" component="p">
                    {doctor.designation}
                  </Typography>
                )}
              </TableCell>
              {doctor.days.map((day) => (
                <TableCell key={day.day} sx={{ verticalAlign: "top", minWidth: 120 }}>
                  <Stack spacing={0.5}>
                    {day.leave_asked && (
                      <Chip size="small" variant="outlined" color="warning" label="Leave asked" />
                    )}
                    {day.sessions.map((session) => (
                      <Box key={`${session.source}-${session.schedule_id ?? session.exception_id}`}>
                        <Chip
                          size="small"
                          color={SESSION_STATUS[session.status].color}
                          variant={session.status === "off" ? "outlined" : "filled"}
                          label={sessionLabel(session)}
                          onClick={() => onSlots(doctor, session)}
                          aria-label={`${sessionLabel(session)}, ${doctor.name}, ${formatDay(day.day)}, ${
                            SESSION_STATUS[session.status].label
                          }: see the slots`}
                        />
                        {session.off.length > 0 && (
                          <Typography variant="caption" component="p">
                            {offText(session)}
                          </Typography>
                        )}
                      </Box>
                    ))}
                  </Stack>
                </TableCell>
              ))}
            </TableRow>
          ))}
          {week.doctors.length === 0 && (
            <TableRow>
              <TableCell colSpan={8}>
                No doctors are posted in {week.department_name}. Post doctors on the Staff page first.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function WeeklySessions({ week }: { week: DepartmentWeek }) {
  const [changing, setChanging] = useState<DoctorSchedule | null>(null);
  const [ending, setEnding] = useState<DoctorSchedule | null>(null);
  const rows = week.doctors.flatMap((d) => d.weekly);
  return (
    <>
      <Typography variant="h6" component="h2">
        Weekly sessions
      </Typography>
      <TableContainer component={Paper}>
        <Table size="small" aria-label="Weekly sessions">
          <TableHead>
            <TableRow>
              <TableCell>Doctor</TableCell>
              <TableCell>Day and hours</TableCell>
              <TableCell>Slots</TableCell>
              <TableCell>From</TableCell>
              <TableCell>Until</TableCell>
              <TableCell>Note</TableCell>
              {week.can_manage && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((s) => (
              <TableRow key={s.id}>
                <TableCell>{s.staff_name}</TableCell>
                <TableCell>
                  {s.weekday_label} {s.hours}
                </TableCell>
                <TableCell>
                  {s.slot_minutes} min
                  {s.extra_bookings_allowed > 0 ? ` · ${s.extra_bookings_allowed} extra` : ""}
                </TableCell>
                <TableCell>{formatDay(s.valid_from)}</TableCell>
                <TableCell>{s.valid_until ? formatDay(s.valid_until) : "No end"}</TableCell>
                <TableCell>{s.note || "—"}</TableCell>
                {week.can_manage && (
                  <TableCell sx={{ whiteSpace: "nowrap" }}>
                    <Button size="small" onClick={() => setChanging(s)} aria-label={`Change ${s.staff_name} ${s.weekday_label} ${s.hours}`}>
                      Change
                    </Button>
                    <Button size="small" color="error" onClick={() => setEnding(s)} aria-label={`End ${s.staff_name} ${s.weekday_label} ${s.hours}`}>
                      End
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>No weekly sessions in {week.department_name} yet.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {changing && <ChangeSessionDialog schedule={changing} onClose={() => setChanging(null)} />}
      {ending && <EndSessionDialog schedule={ending} onClose={() => setEnding(null)} />}
    </>
  );
}

function Exceptions({ week }: { week: DepartmentWeek }) {
  const [cancelling, setCancelling] = useState<ScheduleException | null>(null);
  const today = localDate();
  return (
    <>
      <Typography variant="h6" component="h2">
        Away, holidays and extra sessions this week
      </Typography>
      <TableContainer component={Paper}>
        <Table size="small" aria-label="Schedule exceptions">
          <TableHead>
            <TableRow>
              <TableCell>What</TableCell>
              <TableCell>Who or where</TableCell>
              <TableCell>When</TableCell>
              <TableCell>Why</TableCell>
              {week.can_manage && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {week.exceptions.map((item) => (
              <TableRow key={item.id}>
                <TableCell>{item.kind_label}</TableCell>
                <TableCell>{item.staff_name || item.department_name || `${item.facility_name} (whole facility)`}</TableCell>
                <TableCell>{exceptionPeriod(item)}</TableCell>
                <TableCell>{item.reason || "—"}</TableCell>
                {week.can_manage && (
                  <TableCell>
                    {item.end_date >= today && (
                      <Button size="small" color="error" onClick={() => setCancelling(item)} aria-label={`Cancel ${item.kind_label}, ${exceptionPeriod(item)}`}>
                        Cancel
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
            {week.exceptions.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>Nothing this week.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {cancelling && <CancelExceptionDialog item={cancelling} onClose={() => setCancelling(null)} />}
    </>
  );
}

function SlotsDialog({ doctor, session, onClose }: { doctor: WeekDoctor; session: OpdSession; onClose: () => void }) {
  const day = useDoctorDay(doctor.staff_id, session.day);
  const shown = day.data?.sessions.find(
    (s) => s.schedule_id === session.schedule_id && s.exception_id === session.exception_id,
  );
  const upcoming = shown?.slots.filter((slot) => !slot.is_past) ?? [];
  const passed = (shown?.slots.length ?? 0) - upcoming.length;
  return (
    <FormDialog
      title={`${doctor.name} · ${formatDay(session.day)} ${session.hours}`}
      error={day.error}
      pending={false}
      submitLabel="Done"
      onClose={onClose}
      onSubmit={onClose}
    >
      {day.isPending && <LinearProgress aria-label="Loading the slots" />}
      {shown && (
        <>
          <Typography variant="body2">
            {SESSION_STATUS[shown.status].label}. {shown.slot_minutes}-minute slots
            {shown.extra_bookings_allowed > 0 ? `, up to ${shown.extra_bookings_allowed} extra bookings` : ""}.{" "}
            {shown.off.length > 0 && offText(shown)}
          </Typography>
          {upcoming.length > 0 && (
            <Box role="list" aria-label="Free slots" sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
              {upcoming.map((slot) => (
                <Chip key={slot.starts_at} role="listitem" size="small" variant="outlined" label={slot.time} />
              ))}
            </Box>
          )}
          {passed > 0 && (
            <Typography variant="body2">
              {upcoming.length > 0
                ? `${passed} earlier slot(s) have already passed.`
                : `All ${passed} slot(s) in this session have already passed.`}
            </Typography>
          )}
          {shown.slots.length === 0 && <Typography variant="body2">No free slots in this session.</Typography>}
          <Typography variant="caption">Booking appointments into these slots comes next (HIMS-OPD-002).</Typography>
        </>
      )}
    </FormDialog>
  );
}

function AddSessionsDialog({ week, onClose }: { week: DepartmentWeek; onClose: () => void }) {
  const add = useAddSessions(useState(() => crypto.randomUUID())[0]);
  const [values, setValues] = useState({
    staff: week.doctors[0]?.staff_id ?? "",
    start_time: "09:00",
    end_time: "13:00",
    slot_minutes: "10",
    extra_bookings_allowed: "0",
    valid_from: localDate() > week.start ? localDate() : week.start,
    valid_until: "",
    note: "",
  });
  const [weekdays, setWeekdays] = useState<number[]>([0]);
  const set = (field: string, value: string) => setValues({ ...values, [field]: value });
  return (
    <FormDialog
      title={`Add weekly session · ${week.department_name}`}
      error={add.error}
      fields={["staff", "weekdays", "start_time", "end_time", "slot_minutes", "extra_bookings_allowed", "valid_from", "valid_until", "note"]}
      submitLabel="Add"
      submitDisabled={!values.staff || weekdays.length === 0}
      pending={add.isPending}
      onClose={onClose}
      onSubmit={() =>
        add.mutate(
          {
            staff: values.staff,
            department: week.department_id,
            weekdays: [...weekdays].sort(),
            start_time: values.start_time,
            end_time: values.end_time,
            slot_minutes: Number(values.slot_minutes),
            extra_bookings_allowed: Number(values.extra_bookings_allowed),
            valid_from: values.valid_from,
            valid_until: values.valid_until || null,
            note: values.note.trim(),
          },
          { onSuccess: onClose },
        )
      }
    >
      <TextField select label="Doctor" required value={values.staff} onChange={(e) => set("staff", e.target.value)}>
        {week.doctors.map((d) => (
          <MenuItem key={d.staff_id} value={d.staff_id}>
            {d.name}
          </MenuItem>
        ))}
      </TextField>
      <FormGroup row aria-label="On these weekdays">
        {WEEKDAYS.map((name, index) => (
          <FormControlLabel
            key={name}
            label={name}
            control={
              <Checkbox
                checked={weekdays.includes(index)}
                onChange={(e) =>
                  setWeekdays((current) => (e.target.checked ? [...current, index] : current.filter((d) => d !== index)))
                }
              />
            }
          />
        ))}
      </FormGroup>
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
          slotProps={{ inputLabel: { shrink: true } }}
          fullWidth
        />
      </Stack>
      <Stack direction="row" spacing={2}>
        <TextField
          type="number"
          label="Slot (minutes)"
          value={values.slot_minutes}
          onChange={(e) => set("slot_minutes", e.target.value)}
          slotProps={{ htmlInput: { min: 5, max: 120 } }}
          fullWidth
        />
        <TextField
          type="number"
          label="Extra bookings per session"
          value={values.extra_bookings_allowed}
          onChange={(e) => set("extra_bookings_allowed", e.target.value)}
          helperText="Over the slots; 0 = none"
          slotProps={{ htmlInput: { min: 0, max: 20 } }}
          fullWidth
        />
      </Stack>
      <Stack direction="row" spacing={2}>
        <TextField
          type="date"
          label="From"
          required
          value={values.valid_from}
          onChange={(e) => set("valid_from", e.target.value)}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: localDate() } }}
          fullWidth
        />
        <TextField
          type="date"
          label="Until (optional)"
          value={values.valid_until}
          onChange={(e) => set("valid_until", e.target.value)}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: values.valid_from } }}
          fullWidth
        />
      </Stack>
      <TextField
        label="Note (optional)"
        value={values.note}
        onChange={(e) => set("note", e.target.value)}
        helperText="e.g. Room 4. No patient details."
      />
    </FormDialog>
  );
}

function ChangeSessionDialog({ schedule, onClose }: { schedule: DoctorSchedule; onClose: () => void }) {
  const change = useChangeSession(schedule.id);
  const [slot, setSlot] = useState(String(schedule.slot_minutes));
  const [extra, setExtra] = useState(String(schedule.extra_bookings_allowed));
  const [note, setNote] = useState(schedule.note);
  return (
    <FormDialog
      title={`Change ${schedule.staff_name} · ${schedule.weekday_label} ${schedule.hours}`}
      error={change.error}
      fields={["slot_minutes", "extra_bookings_allowed", "note"]}
      pending={change.isPending}
      onClose={onClose}
      onSubmit={() =>
        change.mutate(
          {
            version: schedule.version,
            slot_minutes: Number(slot),
            extra_bookings_allowed: Number(extra),
            note: note.trim(),
          },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        To change the day or the hours, end this session and add a new one, so the old pattern stays on record.
      </Typography>
      <TextField type="number" label="Slot (minutes)" value={slot} onChange={(e) => setSlot(e.target.value)} />
      <TextField type="number" label="Extra bookings per session" value={extra} onChange={(e) => setExtra(e.target.value)} />
      <TextField label="Note" value={note} onChange={(e) => setNote(e.target.value)} />
    </FormDialog>
  );
}

function EndSessionDialog({ schedule, onClose }: { schedule: DoctorSchedule; onClose: () => void }) {
  const end = useEndSession(schedule.id);
  const [lastDay, setLastDay] = useState(localDate());
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`End ${schedule.staff_name} · ${schedule.weekday_label} ${schedule.hours}`}
      error={end.error}
      fields={["last_day", "reason"]}
      submitLabel="End session"
      submitColor="error"
      submitDisabled={!reason.trim() || !lastDay}
      pending={end.isPending}
      onClose={onClose}
      onSubmit={() =>
        end.mutate({ version: schedule.version, last_day: lastDay, reason: reason.trim() }, { onSuccess: onClose })
      }
    >
      <Typography variant="body2">
        It runs on its last day and then stops. A last day before {formatDay(schedule.valid_from)} withdraws it. It
        stays on record.
      </Typography>
      <TextField
        type="date"
        label="Last day"
        required
        value={lastDay}
        onChange={(e) => setLastDay(e.target.value)}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <TextField label="Why?" required value={reason} onChange={(e) => setReason(e.target.value)} helperText="e.g. Moves to afternoons" />
    </FormDialog>
  );
}

function AffectedList({ result }: { result: AddedException }) {
  return (
    <Alert severity={result.affected.length ? "warning" : "success"}>
      {result.affected.length === 0
        ? "Recorded. No session is affected."
        : `Recorded. ${result.affected.length} session(s) are off, all or in part:`}
      {result.affected.length > 0 && (
        <Box component="ul" sx={{ m: 0, pl: 2 }}>
          {result.affected.map((s) => (
            <li key={`${s.staff_id}-${s.starts_at}`}>
              {formatDay(s.day)} {s.hours}, {s.department_name}
            </li>
          ))}
        </Box>
      )}
      {result.affected.length > 0 && " Patients booked in them will be listed here once booking exists (HIMS-OPD-002)."}
    </Alert>
  );
}

function ExceptionDialog({
  week,
  kind,
  onClose,
}: {
  week: DepartmentWeek;
  kind: ScheduleExceptionKind;
  onClose: () => void;
}) {
  const add = useAddException(useState(() => crypto.randomUUID())[0]);
  const meta = EXCEPTION_KINDS.find((k) => k.value === kind)!;
  const first = localDate() > week.start ? localDate() : week.start;
  const [values, setValues] = useState({
    staff: kind === "holiday" ? "" : (week.doctors[0]?.staff_id ?? ""),
    start_date: first,
    end_date: "",
    start_time: kind === "extra_session" ? "14:00" : "",
    end_time: kind === "extra_session" ? "16:00" : "",
    slot_minutes: "10",
    reason: "",
  });
  const [wholeFacility, setWholeFacility] = useState(false);
  const set = (field: string, value: string) => setValues({ ...values, [field]: value });
  if (add.data) {
    return (
      <FormDialog title={meta.label} error={null} pending={false} submitLabel="Done" onClose={onClose} onSubmit={onClose}>
        <AffectedList result={add.data} />
      </FormDialog>
    );
  }
  const partOfDay = !!values.start_time || !!values.end_time;
  return (
    <FormDialog
      title={`${meta.label} · ${wholeFacility ? week.facility_name : week.department_name}`}
      error={add.error}
      fields={["staff", "start_date", "end_date", "start_time", "end_time", "slot_minutes", "reason"]}
      submitLabel="Record"
      submitDisabled={!values.reason.trim() || (kind !== "holiday" && !values.staff)}
      pending={add.isPending}
      onClose={onClose}
      onSubmit={() =>
        add.mutate({
          kind,
          department: wholeFacility ? null : week.department_id,
          facility: week.facility_id,
          staff: kind === "holiday" ? null : values.staff,
          start_date: values.start_date,
          end_date: kind === "extra_session" || partOfDay ? null : values.end_date || null,
          start_time: values.start_time || null,
          end_time: values.end_time || null,
          slot_minutes: kind === "extra_session" ? Number(values.slot_minutes) : null,
          reason: values.reason.trim(),
        })
      }
    >
      <Typography variant="body2">{meta.help}</Typography>
      {kind !== "holiday" && (
        <TextField select label="Doctor" required value={values.staff} onChange={(e) => set("staff", e.target.value)}>
          {week.doctors.map((d) => (
            <MenuItem key={d.staff_id} value={d.staff_id}>
              {d.name}
            </MenuItem>
          ))}
        </TextField>
      )}
      {kind === "holiday" && week.can_close_facility && (
        <FormControlLabel
          control={<Checkbox checked={wholeFacility} onChange={(e) => setWholeFacility(e.target.checked)} />}
          label={`The whole facility (${week.facility_name}), not only ${week.department_name}`}
        />
      )}
      <Stack direction="row" spacing={2}>
        <TextField
          type="date"
          label={kind === "extra_session" ? "Day" : "First day"}
          required
          value={values.start_date}
          onChange={(e) => set("start_date", e.target.value)}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: localDate() } }}
          fullWidth
        />
        {kind !== "extra_session" && (
          <TextField
            type="date"
            label="Last day (optional)"
            value={values.end_date}
            onChange={(e) => set("end_date", e.target.value)}
            helperText={partOfDay ? "With hours: the first day only" : "For several days"}
            slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: values.start_date } }}
            fullWidth
          />
        )}
      </Stack>
      <Stack direction="row" spacing={2}>
        <TextField
          type="time"
          label={kind === "extra_session" ? "Starts" : "From (optional)"}
          required={kind === "extra_session"}
          value={values.start_time}
          onChange={(e) => set("start_time", e.target.value)}
          helperText={kind === "extra_session" ? undefined : "Empty = the whole day"}
          slotProps={{ inputLabel: { shrink: true } }}
          fullWidth
        />
        <TextField
          type="time"
          label={kind === "extra_session" ? "Ends" : "Until (optional)"}
          required={kind === "extra_session"}
          value={values.end_time}
          onChange={(e) => set("end_time", e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          fullWidth
        />
      </Stack>
      {kind === "extra_session" && (
        <TextField
          type="number"
          label="Slot (minutes)"
          value={values.slot_minutes}
          onChange={(e) => set("slot_minutes", e.target.value)}
          slotProps={{ htmlInput: { min: 5, max: 120 } }}
        />
      )}
      <TextField
        label="Why?"
        required
        value={values.reason}
        onChange={(e) => set("reason", e.target.value)}
        helperText={
          kind === "holiday"
            ? "e.g. Diwali. Everyone who sees the schedule sees it."
            : "e.g. Conference. No medical details: only schedulers see it."
        }
      />
    </FormDialog>
  );
}

function CancelExceptionDialog({ item, onClose }: { item: ScheduleException; onClose: () => void }) {
  const cancel = useCancelException(item.id);
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`Cancel · ${item.kind_label}`}
      error={cancel.error}
      fields={["reason"]}
      submitLabel="Cancel it"
      submitColor="error"
      submitDisabled={!reason.trim()}
      pending={cancel.isPending}
      onClose={onClose}
      onSubmit={() => cancel.mutate({ version: item.version, reason: reason.trim() }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        {item.staff_name || item.department_name || item.facility_name}, {exceptionPeriod(item)}. The sessions come back;
        it stays on record as cancelled.
      </Typography>
      <TextField label="Why?" required value={reason} onChange={(e) => setReason(e.target.value)} />
    </FormDialog>
  );
}
