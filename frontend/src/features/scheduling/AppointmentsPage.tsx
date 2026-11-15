import {
  Alert,
  Box,
  Button,
  Chip,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
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
import { useLocation } from "react-router-dom";

import type {
  Appointment,
  AppointmentCancelChoice,
  AppointmentKind,
  AppointmentSource,
  DayDoctor,
  DepartmentDay,
  OpdSession,
  ToRebook,
} from "../../api/types";
import { localDate } from "../../components/dates";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { addDays, formatDay } from "../rosters/labels";
import { useAllDepartments } from "../staff/api";
import {
  useBook,
  useCancelAppointment,
  useDepartmentDay,
  usePatientSearch,
  useReschedule,
  useToRebook,
} from "./api";
import { offText } from "./labels";

type Slot = OpdSession["slots"][number];

/** A patient chosen before coming here, e.g. from the chart's Book button. */
export interface PickedPatient {
  id: string;
  name: string;
  mrn: string;
}

const KINDS: { value: AppointmentKind; label: string }[] = [
  { value: "new", label: "New" },
  { value: "follow_up", label: "Follow-up" },
];
const SOURCES: { value: AppointmentSource; label: string }[] = [
  { value: "front_desk", label: "At the front desk" },
  { value: "phone", label: "By phone" },
];
const CANCEL_REASONS: { value: AppointmentCancelChoice; label: string }[] = [
  { value: "patient_request", label: "The patient asked" },
  { value: "hospital", label: "The hospital cancelled" },
  { value: "doctor_unavailable", label: "The doctor is not available" },
];

export function patientText(item: Pick<Appointment, "patient_name" | "patient_mrn">): string {
  return `${item.patient_name} (${item.patient_mrn})`;
}

/**
 * Appointments (HIMS-OPD-002; spec 4.6, P0 part 01 section 4): one department's doctors on one day,
 * each session's slots free or booked. The front desk and OPD schedulers book a patient into a free
 * slot (or over the slots when the session allows it), move an appointment to another time and
 * cancel it with the reason; heads of department see it all. Patients whose doctor is now away, on
 * leave, or whose session ended are listed under "To move". Times are on the facility's clock.
 */
export function AppointmentsPage() {
  const location = useLocation();
  const [preset, setPreset] = useState<PickedPatient | null>(
    () => (location.state as { patient?: PickedPatient } | null)?.patient ?? null,
  );
  const departments = useAllDepartments();
  const active = (departments.data?.results ?? []).filter((d) => d.status === "active");
  const [chosen, setChosen] = useState("");
  const department = chosen || active[0]?.id || "";
  const [date, setDate] = useState(() => localDate());
  const day = useDepartmentDay(department, date);
  const rebook = useToRebook(department);
  const [booking, setBooking] = useState<{ doctor: DayDoctor; session: OpdSession; slot: Slot | null } | null>(
    null,
  );
  const [moving, setMoving] = useState<Appointment | null>(null);
  const [cancelling, setCancelling] = useState<Appointment | null>(null);
  const data = day.data;
  const canBook = !!data?.can_book;

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Appointments
        </Typography>
        <Typography variant="body2">
          Book patients into doctors' free slots, move appointments to another time and cancel them. Times are on
          the facility's clock.
        </Typography>
      </Box>
      {preset && (
        <Alert severity="info" onClose={() => setPreset(null)}>
          Booking for {preset.name} ({preset.mrn}): choose a free slot.
        </Alert>
      )}
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
        <TextField
          size="small"
          type="date"
          label="Day"
          value={date}
          onChange={(e) => e.target.value && setDate(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <Button onClick={() => setDate(addDays(date, -1))}>Previous day</Button>
        <Button onClick={() => setDate(localDate())}>Today</Button>
        <Button onClick={() => setDate(addDays(date, 1))}>Next day</Button>
      </Stack>
      {departments.error && <ErrorAlert error={departments.error} />}
      {day.error && <ErrorAlert error={day.error} />}
      {(departments.isPending || day.isFetching) && <LinearProgress aria-label="Loading the appointments" />}
      {!departments.isPending && active.length === 0 && <Alert severity="info">No departments to show.</Alert>}
      {rebook.data && rebook.data.length > 0 && (
        <ToMove rows={rebook.data} canBook={canBook} onMove={setMoving} onCancel={setCancelling} />
      )}
      {data && (
        <DoctorsDay day={data} canBook={canBook} onBook={(doctor, session, slot) => setBooking({ doctor, session, slot })} />
      )}
      {data && (
        <DayAppointments day={data} canBook={canBook} onMove={setMoving} onCancel={setCancelling} />
      )}
      {data && booking && (
        <BookDialog
          day={data}
          {...booking}
          preset={preset}
          onClose={(booked) => {
            setBooking(null);
            if (booked) setPreset(null);
          }}
        />
      )}
      {moving && <MoveDialog appointment={moving} onClose={() => setMoving(null)} />}
      {cancelling && <CancelDialog appointment={cancelling} onClose={() => setCancelling(null)} />}
    </Stack>
  );
}

function sessionSummary(session: OpdSession): string {
  const extra = session.source === "extra" ? " (extra session)" : "";
  if (session.status === "off") return `${session.hours}${extra} · off: ${offText(session)}`;
  const over = session.extra_booked ? `, ${session.extra_booked} over the slots` : "";
  const off = session.off.length ? ` · ${offText(session)}` : "";
  return `${session.hours}${extra} · ${session.booked} booked${over} · ${session.free_slots} free${off}`;
}

function DoctorsDay({
  day,
  canBook,
  onBook,
}: {
  day: DepartmentDay;
  canBook: boolean;
  onBook: (doctor: DayDoctor, session: OpdSession, slot: Slot | null) => void;
}) {
  if (day.doctors.length === 0) {
    return <Alert severity="info">No doctors are posted in {day.department_name}.</Alert>;
  }
  return (
    <Stack spacing={1.5} component="section" aria-label={`Doctors' sessions on ${formatDay(day.day)}`}>
      <Typography variant="h6" component="h2">
        {day.department_name} · {formatDay(day.day)}
      </Typography>
      {day.doctors.map((doctor) => (
        <Paper key={doctor.staff_id} variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600 }}>
            {doctor.name}
            {doctor.designation ? ` · ${doctor.designation}` : ""}
            {doctor.leave_asked && <Chip size="small" label="Leave asked" sx={{ ml: 1 }} />}
          </Typography>
          {doctor.sessions.length === 0 && <Typography variant="body2">No OPD session this day.</Typography>}
          {doctor.sessions.map((session) => (
            <SessionSlots
              key={`${session.schedule_id ?? session.exception_id}`}
              doctor={doctor}
              session={session}
              canBook={canBook}
              onBook={onBook}
            />
          ))}
        </Paper>
      ))}
    </Stack>
  );
}

function SessionSlots({
  doctor,
  session,
  canBook,
  onBook,
}: {
  doctor: DayDoctor;
  session: OpdSession;
  canBook: boolean;
  onBook: (doctor: DayDoctor, session: OpdSession, slot: Slot | null) => void;
}) {
  const coming = session.slots.filter((slot) => !slot.is_past);
  const passed = session.slots.length - coming.length;
  const extraLeft = session.extra_bookings_allowed - session.extra_booked;
  const canGoOver = canBook && extraLeft > 0 && coming.some((slot) => slot.is_booked);
  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="body2">{sessionSummary(session)}</Typography>
      {coming.length > 0 && (
        <Box
          role="list"
          aria-label={`Slots, ${doctor.name}, ${session.hours}`}
          sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5 }}
        >
          {coming.map((slot) =>
            slot.is_booked ? (
              <Chip key={slot.starts_at} role="listitem" size="small" label={`${slot.time} booked`} />
            ) : (
              <Box key={slot.starts_at} role="listitem">
                <Chip
                  size="small"
                  variant="outlined"
                  color="success"
                  label={slot.time}
                  onClick={canBook ? () => onBook(doctor, session, slot) : undefined}
                  aria-label={canBook ? `${slot.time} free: book with ${doctor.name}` : `${slot.time} free`}
                />
              </Box>
            ),
          )}
        </Box>
      )}
      {passed > 0 && (
        <Typography variant="caption" component="p">
          {coming.length > 0
            ? `${passed} earlier slot(s) have already passed.`
            : `All ${passed} slot(s) in this session have already passed.`}
        </Typography>
      )}
      {canGoOver && (
        <Button size="small" onClick={() => onBook(doctor, session, null)}>
          Book over the slots ({extraLeft} left)
        </Button>
      )}
    </Box>
  );
}

function AppointmentActions({
  item,
  onMove,
  onCancel,
}: {
  item: Appointment;
  onMove: (a: Appointment) => void;
  onCancel: (a: Appointment) => void;
}) {
  const who = `${item.patient_name}, ${item.time}`;
  return (
    <Stack direction="row" spacing={0.5}>
      <Button size="small" onClick={() => onMove(item)} aria-label={`Move ${who}`}>
        Move
      </Button>
      <Button size="small" color="error" onClick={() => onCancel(item)} aria-label={`Cancel ${who}`}>
        Cancel
      </Button>
    </Stack>
  );
}

function ToMove({
  rows,
  canBook,
  onMove,
  onCancel,
}: {
  rows: ToRebook[];
  canBook: boolean;
  onMove: (a: Appointment) => void;
  onCancel: (a: Appointment) => void;
}) {
  return (
    <Paper variant="outlined" component="section" aria-label="To move" sx={{ p: 1.5 }}>
      <Typography variant="h6" component="h2">
        To move
      </Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>
        Booked patients whose doctor is now away or on leave, or whose session ended: move each one to another
        time, or cancel it.
        {rows.length >= 200 && " These are the soonest 200: the next ones show as these are moved."}
      </Typography>
      <TableContainer>
        <Table size="small" aria-label="Appointments to move">
          <TableHead>
            <TableRow>
              <TableCell>Day</TableCell>
              <TableCell>Time</TableCell>
              <TableCell>Patient</TableCell>
              <TableCell>Doctor</TableCell>
              <TableCell>Why</TableCell>
              {canBook && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map(({ appointment, why }) => (
              <TableRow key={appointment.id}>
                <TableCell>{formatDay(appointment.local_date)}</TableCell>
                <TableCell>{appointment.time}</TableCell>
                <TableCell>{patientText(appointment)}</TableCell>
                <TableCell>{appointment.staff_name}</TableCell>
                <TableCell>{why}</TableCell>
                {canBook && (
                  <TableCell>
                    <AppointmentActions item={appointment} onMove={onMove} onCancel={onCancel} />
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}

function DayAppointments({
  day,
  canBook,
  onMove,
  onCancel,
}: {
  day: DepartmentDay;
  canBook: boolean;
  onMove: (a: Appointment) => void;
  onCancel: (a: Appointment) => void;
}) {
  return (
    <Box component="section" aria-label="The day's appointments">
      <Typography variant="h6" component="h2" sx={{ mb: 1 }}>
        Appointments on {formatDay(day.day)}
      </Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small" aria-label={`Appointments in ${day.department_name}`}>
          <TableHead>
            <TableRow>
              <TableCell>Time</TableCell>
              <TableCell>Patient</TableCell>
              <TableCell>Doctor</TableCell>
              <TableCell>Visit</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Reason</TableCell>
              {canBook && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {day.appointments.map((item) => (
              <TableRow key={item.id}>
                <TableCell>{item.time}</TableCell>
                <TableCell>
                  {patientText(item)}
                  {item.is_extra && <Chip size="small" label="Over the slots" sx={{ ml: 1 }} />}
                </TableCell>
                <TableCell>{item.staff_name}</TableCell>
                <TableCell>
                  {item.kind_label} · {item.source_label}
                </TableCell>
                <TableCell>
                  {item.status_label}
                  {item.status === "cancelled" && item.cancel_reason_label ? ` (${item.cancel_reason_label})` : ""}
                  {item.token_number ? ` · token ${item.token_number}` : ""}
                </TableCell>
                <TableCell>{item.reason || "—"}</TableCell>
                {canBook && (
                  <TableCell>
                    {item.status === "booked" && (
                      <AppointmentActions item={item} onMove={onMove} onCancel={onCancel} />
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
            {day.appointments.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>Nobody is booked on this day.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

/** Find the patient by MRN, phone, ID number or name; each search is audited on the server. */
export function PatientFinder({ value, onChange }: { value: PickedPatient | null; onChange: (p: PickedPatient) => void }) {
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const found = usePatientSearch(search);
  const results = (found.data?.results ?? []).filter((p) => !p.hidden);
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1}>
        <TextField
          label="Find the patient"
          helperText="MRN, phone, ID number or name"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              setSearch(typed.trim());
            }
          }}
          fullWidth
          size="small"
        />
        <Button onClick={() => setSearch(typed.trim())} disabled={!typed.trim()}>
          Search
        </Button>
      </Stack>
      {found.isFetching && <LinearProgress aria-label="Searching" />}
      {found.error && <ErrorAlert error={found.error} />}
      {search && found.data && results.length === 0 && (
        <Typography variant="body2">No patient found. Register them on the Patients page first.</Typography>
      )}
      {results.length > 0 && (
        <RadioGroup
          aria-label="Patients found"
          value={value?.id ?? ""}
          onChange={(e) => {
            const patient = results.find((p) => p.id === e.target.value);
            if (patient) onChange({ id: patient.id, name: patient.name, mrn: patient.mrn });
          }}
        >
          {results.slice(0, 10).map((p) => (
            <FormControlLabel
              key={p.id}
              value={p.id}
              control={<Radio size="small" />}
              label={`${p.name} · ${p.mrn} · ${p.age} ${p.sex}`}
            />
          ))}
        </RadioGroup>
      )}
    </Stack>
  );
}

function BookDialog({
  day,
  doctor,
  session,
  slot,
  preset,
  onClose,
}: {
  day: DepartmentDay;
  doctor: DayDoctor;
  session: OpdSession;
  slot: Slot | null;
  preset: PickedPatient | null;
  onClose: (booked: boolean) => void;
}) {
  const book = useBook(useState(() => crypto.randomUUID())[0]);
  const extra = slot === null; // over the slots: into a booked slot
  const bookedSlots = session.slots.filter((s) => s.is_booked && !s.is_past);
  const [overSlot, setOverSlot] = useState(bookedSlots[0]?.starts_at ?? "");
  const [patient, setPatient] = useState<PickedPatient | null>(preset);
  const [changing, setChanging] = useState(!preset);
  const [kind, setKind] = useState<AppointmentKind>("new");
  const [source, setSource] = useState<AppointmentSource>("front_desk");
  const [reason, setReason] = useState("");
  const startsAt = extra ? overSlot : (slot?.starts_at ?? "");
  const time = extra ? bookedSlots.find((s) => s.starts_at === overSlot)?.time : slot?.time;
  return (
    <FormDialog
      title={`Book ${doctor.name} · ${formatDay(day.day)} ${time ?? ""}${extra ? " (over the slots)" : ""}`}
      error={book.error}
      fields={["patient", "reason", "kind", "source"]}
      pending={book.isPending}
      submitLabel="Book"
      submitDisabled={!patient || !startsAt}
      onClose={() => onClose(false)}
      onSubmit={() =>
        patient &&
        book.mutate(
          {
            patient: patient.id,
            staff: doctor.staff_id,
            department: day.department_id,
            starts_at: startsAt,
            kind,
            source,
            reason: reason.trim(),
            extra,
          },
          { onSuccess: () => onClose(true) },
        )
      }
    >
      {extra && (
        <TextField select label="Booked slot to add to" value={overSlot} onChange={(e) => setOverSlot(e.target.value)}>
          {bookedSlots.map((s) => (
            <MenuItem key={s.starts_at} value={s.starts_at}>
              {s.time}
            </MenuItem>
          ))}
        </TextField>
      )}
      {patient && !changing ? (
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <Typography>
            Patient: {patient.name} ({patient.mrn})
          </Typography>
          <Button size="small" onClick={() => setChanging(true)}>
            Change
          </Button>
        </Stack>
      ) : (
        <PatientFinder
          value={patient}
          onChange={(picked) => {
            setPatient(picked);
            setChanging(false);
          }}
        />
      )}
      <TextField select label="Visit" value={kind} onChange={(e) => setKind(e.target.value as AppointmentKind)}>
        {KINDS.map((k) => (
          <MenuItem key={k.value} value={k.value}>
            {k.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField select label="Booked" value={source} onChange={(e) => setSource(e.target.value as AppointmentSource)}>
        {SOURCES.map((s) => (
          <MenuItem key={s.value} value={s.value}>
            {s.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        label="Reason (optional)"
        helperText="Short, e.g. Blood pressure review. No detailed history."
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        slotProps={{ htmlInput: { maxLength: 200 } }}
      />
    </FormDialog>
  );
}

function MoveDialog({ appointment, onClose }: { appointment: Appointment; onClose: () => void }) {
  const move = useReschedule(appointment.id);
  const [date, setDate] = useState(appointment.local_date);
  const day = useDepartmentDay(appointment.department_id, date);
  const [doctorId, setDoctorId] = useState(appointment.staff_id);
  const [startsAt, setStartsAt] = useState("");
  const [note, setNote] = useState("");
  const doctor = day.data?.doctors.find((d) => d.staff_id === doctorId);
  const free = (doctor?.sessions ?? []).flatMap((session) =>
    session.slots
      .filter((s) => !s.is_past && !s.is_booked)
      .map((s) => ({ ...s, label: `${s.time} (${session.hours})` })),
  );
  return (
    <FormDialog
      title={`Move ${patientText(appointment)}`}
      error={move.error}
      fields={["starts_at", "staff", "note"]}
      pending={move.isPending}
      submitLabel="Move"
      submitDisabled={!startsAt}
      onClose={onClose}
      onSubmit={() =>
        move.mutate(
          { version: appointment.version, starts_at: startsAt, staff: doctorId, extra: false, note: note.trim() },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        Now: {formatDay(appointment.local_date)} {appointment.time} with {appointment.staff_name}. The old
        appointment is kept as moved and links to the new one.
      </Typography>
      <TextField
        type="date"
        label="New day"
        value={date}
        onChange={(e) => {
          if (e.target.value) setDate(e.target.value);
          setStartsAt("");
        }}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <TextField
        select
        label="Doctor"
        value={day.data ? doctorId : ""}
        onChange={(e) => {
          setDoctorId(e.target.value);
          setStartsAt("");
        }}
      >
        {(day.data?.doctors ?? []).map((d) => (
          <MenuItem key={d.staff_id} value={d.staff_id}>
            {d.name}
          </MenuItem>
        ))}
      </TextField>
      {day.isFetching && <LinearProgress aria-label="Loading the free slots" />}
      {day.error && <ErrorAlert error={day.error} />}
      <TextField
        select
        label="Free slot"
        value={startsAt}
        onChange={(e) => setStartsAt(e.target.value)}
        helperText={day.data && free.length === 0 ? "No free slot for this doctor on this day." : undefined}
      >
        {free.map((s) => (
          <MenuItem key={s.starts_at} value={s.starts_at}>
            {s.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField label="Why it moves (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
    </FormDialog>
  );
}

function CancelDialog({ appointment, onClose }: { appointment: Appointment; onClose: () => void }) {
  const cancel = useCancelAppointment(appointment.id);
  const [reason, setReason] = useState<AppointmentCancelChoice>("patient_request");
  const [note, setNote] = useState("");
  return (
    <FormDialog
      title={`Cancel ${patientText(appointment)}`}
      error={cancel.error}
      fields={["reason", "note"]}
      pending={cancel.isPending}
      submitLabel="Cancel appointment"
      submitColor="error"
      onClose={onClose}
      onSubmit={() =>
        cancel.mutate({ version: appointment.version, reason, note: note.trim() }, { onSuccess: onClose })
      }
    >
      <Typography variant="body2">
        {formatDay(appointment.local_date)} {appointment.time} with {appointment.staff_name}. It stays on record as
        cancelled.
      </Typography>
      <TextField
        select
        label="Why"
        value={reason}
        onChange={(e) => setReason(e.target.value as AppointmentCancelChoice)}
      >
        {CANCEL_REASONS.map((r) => (
          <MenuItem key={r.value} value={r.value}>
            {r.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
    </FormDialog>
  );
}
