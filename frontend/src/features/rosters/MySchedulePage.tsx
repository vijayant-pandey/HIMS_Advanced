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

import type { LeaveRequest, LeaveType, MySchedule } from "../../api/types";
import { localDate } from "../../components/dates";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { useAskForLeave, useMySchedule, useWithdrawLeave } from "./api";
import { LEAVE_STATUS, formatDay, leavePeriod } from "./labels";
import { balanceText } from "./LeaveBalances";
import { LeaveFields } from "./LeaveFields";

/** HIMS-STAFF-012: your own shifts, on-call and leave; ask for leave here. */
export function MySchedulePage() {
  const { data, error, isPending } = useMySchedule();
  const [asking, setAsking] = useState(false);
  const [withdrawing, setWithdrawing] = useState<LeaveRequest | null>(null);
  const today = localDate();
  if (error) return <ErrorAlert error={error} />;
  if (isPending) return <LinearProgress aria-label="Loading your schedule" />;
  if (!data.has_staff_record) {
    return (
      <Stack spacing={2}>
        <Typography variant="h5" component="h1">
          My schedule
        </Typography>
        <Alert severity="info">
          Your account has no staff record, so there is no rota or leave for you. HR adds staff records on the Staff
          page.
        </Alert>
      </Stack>
    );
  }
  const shifts = data.shifts.filter((s) => s.status === "scheduled" && s.on_date >= today);
  return (
    <Stack spacing={2}>
      <Stack direction="row" sx={{ alignItems: "flex-start" }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h5" component="h1">
            My schedule
          </Typography>
          <Typography variant="body2">
            Your shifts and on-call for the next six weeks, and your leave. Posted in:{" "}
            {data.postings.map((p) => `${p.department_name} (${p.facility_name})`).join(", ") || "no department yet"}.
          </Typography>
        </Box>
        <Button variant="contained" disabled={data.postings.length === 0} onClick={() => setAsking(true)}>
          Ask for leave
        </Button>
      </Stack>
      <Typography variant="h6" component="h2">
        Coming shifts
      </Typography>
      <TableContainer component={Paper}>
        <Table size="small" aria-label="My coming shifts">
          <TableHead>
            <TableRow>
              <TableCell>Day</TableCell>
              <TableCell>Shift</TableCell>
              <TableCell>Hours</TableCell>
              <TableCell>Department</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {shifts.map((s) => (
              <TableRow key={s.id}>
                <TableCell>{formatDay(s.on_date)}</TableCell>
                <TableCell>
                  {s.shift_type_name}
                  {s.kind === "on_call" && <Chip size="small" color="secondary" label="On call" sx={{ ml: 1 }} />}
                  {s.note && (
                    <Typography variant="caption" component="p">
                      {s.note}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>{s.hours}</TableCell>
                <TableCell>{s.department_name}</TableCell>
              </TableRow>
            ))}
            {shifts.length === 0 && (
              <TableRow>
                <TableCell colSpan={4}>No shifts planned for you yet.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {data.leave_balances.length > 0 && (
        <>
          <Typography variant="h6" component="h2">
            My leave balance, {data.leave_balances[0]!.year_label}
          </Typography>
          <TableContainer component={Paper}>
            <Table size="small" aria-label="My leave balance">
              <TableHead>
                <TableRow>
                  <TableCell>Leave</TableCell>
                  <TableCell>Balance</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.leave_balances.map((balance) => (
                  <TableRow key={balance.leave_type}>
                    <TableCell>{balance.label}</TableCell>
                    <TableCell>{balanceText(balance)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}
      <Typography variant="h6" component="h2">
        My leave
      </Typography>
      <TableContainer component={Paper}>
        <Table size="small" aria-label="My leave">
          <TableHead>
            <TableRow>
              <TableCell>Leave</TableCell>
              <TableCell>When</TableCell>
              <TableCell>Status</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {data.leave.map((item) => {
              const status = LEAVE_STATUS[item.status];
              const canWithdraw =
                item.status === "requested" || (item.status === "approved" && item.start_date > today);
              return (
                <TableRow key={item.id}>
                  <TableCell>{item.leave_type_label}</TableCell>
                  <TableCell>{leavePeriod(item)}</TableCell>
                  <TableCell>
                    <Chip size="small" color={status.color} label={status.label} />
                    {(item.decision_note || item.cancel_reason) && (
                      <Typography variant="caption" component="p">
                        {item.decision_note || item.cancel_reason}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    {canWithdraw && (
                      <Button size="small" onClick={() => setWithdrawing(item)} aria-label={`Withdraw ${leavePeriod(item)}`}>
                        Withdraw
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {data.leave.length === 0 && (
              <TableRow>
                <TableCell colSpan={4}>No leave in the last year.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {asking && <AskDialog schedule={data} onClose={() => setAsking(false)} />}
      {withdrawing && <WithdrawDialog leave={withdrawing} onClose={() => setWithdrawing(null)} />}
    </Stack>
  );
}

function AskDialog({ schedule, onClose }: { schedule: MySchedule; onClose: () => void }) {
  const ask = useAskForLeave(useState(() => crypto.randomUUID())[0]);
  const [department, setDepartment] = useState(schedule.postings[0]?.department_id ?? "");
  const [values, setValues] = useState({
    leave_type: "annual" as LeaveType,
    start_date: localDate(),
    end_date: localDate(),
    reason: "",
  });
  const set = (field: string, value: string) => setValues({ ...values, [field]: value });
  return (
    <FormDialog
      title="Ask for leave"
      error={ask.error}
      fields={["department", "leave_type", "start_date", "end_date", "reason"]}
      submitLabel="Send"
      submitDisabled={!department || !values.start_date || !values.end_date}
      pending={ask.isPending}
      onClose={onClose}
      onSubmit={() => ask.mutate({ ...values, department, reason: values.reason.trim() }, { onSuccess: onClose })}
    >
      <Typography variant="body2">Your head of department is emailed and decides.</Typography>
      {schedule.postings.length > 1 && (
        <TextField select label="Department" required value={department} onChange={(e) => setDepartment(e.target.value)}>
          {schedule.postings.map((p) => (
            <MenuItem key={p.department_id} value={p.department_id}>
              {p.department_name} · {p.facility_name}
            </MenuItem>
          ))}
        </TextField>
      )}
      <LeaveFields values={values} set={set} />
    </FormDialog>
  );
}

function WithdrawDialog({ leave, onClose }: { leave: LeaveRequest; onClose: () => void }) {
  const withdraw = useWithdrawLeave(leave.id);
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title="Withdraw leave"
      error={withdraw.error}
      fields={["reason"]}
      submitLabel="Withdraw"
      submitColor="error"
      submitDisabled={!reason.trim()}
      pending={withdraw.isPending}
      onClose={onClose}
      onSubmit={() => withdraw.mutate({ version: leave.version, reason: reason.trim() }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        {leave.leave_type_label}, {leavePeriod(leave)}. Shifts cancelled for this leave are not planned again by
        themselves.
      </Typography>
      <TextField label="Why?" required value={reason} onChange={(e) => setReason(e.target.value)} helperText="e.g. Plans changed" />
    </FormDialog>
  );
}
