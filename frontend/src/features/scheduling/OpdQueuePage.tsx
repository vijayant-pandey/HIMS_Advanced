import {
  Alert,
  Box,
  Button,
  Chip,
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

import type { ApiError } from "../../api/client";
import type { Appointment, AppointmentKind, DayDoctor, OpdQueue } from "../../api/types";
import { localDate } from "../../components/dates";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { addDays, formatDay } from "../rosters/labels";
import { useAllDepartments } from "../staff/api";
import { PatientFinder, type PickedPatient, patientText } from "./AppointmentsPage";
import { useCallNext, useLeftUnseen, useOpdQueue, useQueueStep, useWalkIn } from "./api";
import { offText } from "./labels";

// The order a doctor's list is shown in: who is in now, who waits (by token), who is still to come.
const ORDER: Record<string, number> = {
  in_consultation: 0,
  checked_in: 1,
  booked: 2,
  completed: 3,
  no_show: 4,
  cancelled: 5,
};

const KINDS: { value: AppointmentKind; label: string }[] = [
  { value: "new", label: "New" },
  { value: "follow_up", label: "Follow-up" },
];

/** Shown in the queue: not the bookings moved or cancelled before the day, only those who left. */
function inQueue(item: Appointment): boolean {
  return item.status !== "cancelled" || item.cancel_reason === "left_unseen";
}

function minutesSince(instant: string | null | undefined, now: number): number {
  return instant ? Math.max(0, Math.round((now - new Date(instant).getTime()) / 60_000)) : 0;
}

function statusText(item: Appointment, now: number): string {
  switch (item.status) {
    case "checked_in":
      return `Waiting ${minutesSince(item.checked_in_at, now)} min`;
    case "in_consultation":
      return "With the doctor";
    case "completed":
      return "Seen";
    case "booked":
      return "Still to come";
    case "no_show":
      return "Did not come";
    default:
      return item.cancel_reason_label || item.status_label;
  }
}

/**
 * OPD queue (HIMS-OPD-003; spec 4.6, P0 part 01 section 4 and part 06): one department's doctors today, each
 * with their patients by token: waiting, with the doctor, seen, still to come, did not come. The front desk
 * checks booked patients in (each gets the doctor's next token, in the order they arrive), checks in walk-ins
 * (no slot needed), calls the next token in to the doctor and marks the patient seen; patients not checked in
 * when their session ends are marked "did not come" by the hospital's job. Heads of department and
 * administrators see it; other days are shown as they were.
 */
export function OpdQueuePage() {
  const departments = useAllDepartments();
  const active = (departments.data?.results ?? []).filter((d) => d.status === "active");
  const [chosen, setChosen] = useState("");
  const department = chosen || active[0]?.id || "";
  // "" = today on the facility's clock (the server decides: the browser may be in another time zone).
  const [date, setDate] = useState("");
  const queue = useOpdQueue(department, date);
  const [walkingIn, setWalkingIn] = useState<DayDoctor | null>(null);
  const [problem, setProblem] = useState<ApiError | null>(null);
  const data = queue.data;
  const shown = date || data?.day || "";
  const canManage = !!data?.can_manage && !!data?.is_today;

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          OPD queue
        </Typography>
        <Typography variant="body2">
          Each doctor's patients today by token. Check in booked patients as they arrive, check in walk-ins, and call
          the next token in to the doctor.
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
        <TextField
          size="small"
          type="date"
          label="Day"
          value={shown}
          onChange={(e) => e.target.value && setDate(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <Button onClick={() => setDate(addDays(shown || localDate(), -1))}>Previous day</Button>
        <Button onClick={() => setDate("")}>Today</Button>
      </Stack>
      {departments.error && <ErrorAlert error={departments.error} />}
      {queue.error && <ErrorAlert error={queue.error} />}
      {problem && <ErrorAlert error={problem} />}
      {(departments.isPending || queue.isFetching) && <LinearProgress aria-label="Loading the queue" />}
      {!departments.isPending && active.length === 0 && <Alert severity="info">No departments to show.</Alert>}
      {data && !data.is_today && (
        <Alert severity="info">
          {formatDay(data.day)} is shown as it was: patients are checked in on the day of their visit only.
        </Alert>
      )}
      {data && data.doctors.length === 0 && (
        <Alert severity="info">No doctor has an OPD session in {data.department_name} on this day.</Alert>
      )}
      {data?.doctors.map((doctor) => (
        <DoctorQueue
          key={doctor.staff_id}
          queue={data}
          now={queue.dataUpdatedAt}
          doctor={doctor}
          canManage={canManage}
          onWalkIn={() => setWalkingIn(doctor)}
          onProblem={setProblem}
        />
      ))}
      {data && walkingIn && <WalkInDialog queue={data} doctor={walkingIn} onClose={() => setWalkingIn(null)} />}
    </Stack>
  );
}

function DoctorQueue({
  queue,
  now,
  doctor,
  canManage,
  onWalkIn,
  onProblem,
}: {
  queue: OpdQueue;
  /** When the queue was read: waiting times and passed slots are counted from it. */
  now: number;
  doctor: DayDoctor;
  canManage: boolean;
  onWalkIn: () => void;
  onProblem: (error: ApiError | null) => void;
}) {
  const callNext = useCallNext();
  const rows = queue.appointments
    .filter((a) => a.staff_id === doctor.staff_id && inQueue(a))
    .sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9) || (a.token_number ?? 0) - (b.token_number ?? 0));
  const count = (status: string) => rows.filter((a) => a.status === status).length;
  const waiting = count("checked_in");
  const hours = doctor.sessions.map((s) => (s.status === "off" ? `${s.hours} (off: ${offText(s)})` : s.hours)).join(", ");
  return (
    <Paper variant="outlined" component="section" aria-label={`Queue, ${doctor.name}`} sx={{ p: 1.5 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, flexGrow: 1 }}>
          {doctor.name}
          {doctor.designation ? ` · ${doctor.designation}` : ""} · {hours || "No session"}
        </Typography>
        {canManage && (
          <>
            <Button
              variant="contained"
              size="small"
              disabled={callNext.isPending || (waiting === 0 && count("in_consultation") === 0)}
              aria-label={`Call next for ${doctor.name}`}
              onClick={() => {
                onProblem(null);
                callNext.mutate({ department: queue.department_id, staff: doctor.staff_id }, { onError: onProblem });
              }}
            >
              Call next
            </Button>
            <Button size="small" onClick={onWalkIn} aria-label={`Walk in for ${doctor.name}`}>
              Walk in
            </Button>
          </>
        )}
      </Stack>
      <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", my: 1 }}>
        <Chip size="small" color={waiting ? "warning" : "default"} label={`Waiting ${waiting}`} />
        <Chip size="small" label={`With the doctor ${count("in_consultation")}`} />
        <Chip size="small" label={`Seen ${count("completed")}`} />
        <Chip size="small" label={`Still to come ${count("booked")}`} />
        <Chip size="small" label={`Did not come ${count("no_show")}`} />
      </Box>
      <TableContainer>
        <Table size="small" aria-label={`Patients of ${doctor.name}`}>
          <TableHead>
            <TableRow>
              <TableCell>Token</TableCell>
              <TableCell>Patient</TableCell>
              <TableCell>Booked for</TableCell>
              <TableCell>Status</TableCell>
              {canManage && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((item) => (
              <TableRow key={item.id} selected={item.status === "in_consultation"}>
                <TableCell>{item.token_number ?? "—"}</TableCell>
                <TableCell>
                  {patientText(item)}
                  {item.reason ? ` · ${item.reason}` : ""}
                </TableCell>
                <TableCell>{item.source === "walk_in" ? "Walk-in" : item.time}</TableCell>
                <TableCell>{statusText(item, now)}</TableCell>
                {canManage && (
                  <TableCell>
                    <RowActions item={item} now={now} onProblem={onProblem} />
                  </TableCell>
                )}
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>No patients on this day.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}

function RowActions({
  item,
  now,
  onProblem,
}: {
  item: Appointment;
  now: number;
  onProblem: (error: ApiError | null) => void;
}) {
  const checkIn = useQueueStep(item.id, "check-in");
  const seen = useQueueStep(item.id, "seen");
  const noShow = useQueueStep(item.id, "no-show");
  const undo = useQueueStep(item.id, "undo-no-show");
  const left = useLeftUnseen(item.id);
  const who = item.patient_name;
  const run = (mutation: typeof checkIn) => () => {
    onProblem(null);
    mutation.mutate({ version: item.version }, { onError: onProblem });
  };
  const passed = new Date(item.starts_at).getTime() < now;
  return (
    <Stack direction="row" spacing={0.5}>
      {(item.status === "booked" || item.status === "no_show") && (
        <Button size="small" onClick={run(checkIn)} disabled={checkIn.isPending} aria-label={`Check in ${who}`}>
          Check in
        </Button>
      )}
      {item.status === "booked" && passed && (
        <Button size="small" onClick={run(noShow)} disabled={noShow.isPending} aria-label={`Did not come: ${who}`}>
          Did not come
        </Button>
      )}
      {item.status === "no_show" && (
        <Button size="small" onClick={run(undo)} disabled={undo.isPending} aria-label={`Undo did not come: ${who}`}>
          Undo
        </Button>
      )}
      {item.status === "in_consultation" && (
        <Button size="small" onClick={run(seen)} disabled={seen.isPending} aria-label={`Seen: ${who}`}>
          Seen
        </Button>
      )}
      {item.status === "checked_in" && (
        <Button
          size="small"
          color="error"
          disabled={left.isPending}
          aria-label={`Left before being seen: ${who}`}
          onClick={() => {
            onProblem(null);
            left.mutate({ version: item.version, note: "" }, { onError: onProblem });
          }}
        >
          Left
        </Button>
      )}
    </Stack>
  );
}

function WalkInDialog({ queue, doctor, onClose }: { queue: OpdQueue; doctor: DayDoctor; onClose: () => void }) {
  const walkIn = useWalkIn(useState(() => crypto.randomUUID())[0]);
  const [patient, setPatient] = useState<PickedPatient | null>(null);
  const [kind, setKind] = useState<AppointmentKind>("new");
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`Walk in · ${doctor.name}`}
      error={walkIn.error}
      fields={["patient", "kind", "reason"]}
      pending={walkIn.isPending}
      submitLabel="Check in"
      submitDisabled={!patient}
      onClose={onClose}
      onSubmit={() =>
        patient &&
        walkIn.mutate(
          { patient: patient.id, staff: doctor.staff_id, department: queue.department_id, kind, reason: reason.trim() },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        A patient without an appointment: checked in at once with {doctor.name}'s next token. No slot is needed.
      </Typography>
      {patient ? (
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <Typography>
            Patient: {patient.name} ({patient.mrn})
          </Typography>
          <Button size="small" onClick={() => setPatient(null)}>
            Change
          </Button>
        </Stack>
      ) : (
        <PatientFinder value={patient} onChange={setPatient} />
      )}
      <TextField select label="Visit" value={kind} onChange={(e) => setKind(e.target.value as AppointmentKind)}>
        {KINDS.map((k) => (
          <MenuItem key={k.value} value={k.value}>
            {k.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        label="Reason (optional)"
        helperText="Short, e.g. Fever since yesterday. No detailed history."
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        slotProps={{ htmlInput: { maxLength: 200 } }}
      />
    </FormDialog>
  );
}
