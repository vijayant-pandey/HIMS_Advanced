import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
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

import type { LeaveRequest, LeaveType } from "../../api/types";
import { localDate } from "../../components/dates";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { useAllDepartments } from "../staff/api";
import { type LeaveDecision, useDecideLeave, useLeaveRequests, useRecordLeave, useRotaWeek } from "./api";
import { LEAVE_STATUS, formatDay, leavePeriod, mondayOf } from "./labels";
import { BalancesTab, EntitlementsTab } from "./LeaveBalances";
import { LeaveFields } from "./LeaveFields";

type Filter = "waiting" | "upcoming" | "past";
type LeaveTab = Filter | "balances" | "entitlements";

/** HIMS-STAFF-012: approvers decide leave for their departments, and record it for staff. */
export function LeavePage() {
  const { data: user } = useCurrentUser();
  const canSetPolicy = hasOrganizationWidePermission(user, "leave.policy.manage");
  const [tab, setTab] = useState<LeaveTab>("waiting");
  const filter: Filter = tab === "upcoming" || tab === "past" ? tab : "waiting";
  const leave = useLeaveRequests(filter);
  const [deciding, setDeciding] = useState<{ leave: LeaveRequest; decision: LeaveDecision } | null>(null);
  const [recording, setRecording] = useState(false);
  return (
    <Stack spacing={2}>
      <Stack direction="row" sx={{ alignItems: "flex-start" }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h5" component="h1">
            Leave
          </Typography>
          <Typography variant="body2">
            Leave asked for in the departments you approve for. Nobody decides their own leave. The person is emailed
            when you decide.
          </Typography>
        </Box>
        <Button variant="contained" onClick={() => setRecording(true)}>
          Record leave
        </Button>
      </Stack>
      <Tabs value={tab} onChange={(_, value) => setTab(value)}>
        <Tab value="waiting" label="To decide" />
        <Tab value="upcoming" label="Approved, coming up" />
        <Tab value="past" label="Past and closed" />
        <Tab value="balances" label="Balances" />
        <Tab value="entitlements" label="Entitlements" />
      </Tabs>
      {tab === "balances" && <BalancesTab canManage={canSetPolicy} />}
      {tab === "entitlements" && <EntitlementsTab canManage={canSetPolicy} year={Number(localDate().slice(0, 4))} />}
      {tab !== "balances" && tab !== "entitlements" && leave.error && <ErrorAlert error={leave.error} />}
      {tab !== "balances" && tab !== "entitlements" && leave.isPending && <LinearProgress aria-label="Loading leave" />}
      {tab !== "balances" && tab !== "entitlements" && <TableContainer component={Paper}>
        <Table size="small" aria-label="Leave">
          <TableHead>
            <TableRow>
              <TableCell>Person</TableCell>
              <TableCell>Leave</TableCell>
              <TableCell>When</TableCell>
              <TableCell>Status</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {leave.data?.map((item) => {
              const status = LEAVE_STATUS[item.status];
              return (
                <TableRow key={item.id}>
                  <TableCell>
                    {item.staff_name}
                    <Typography variant="caption" component="p">
                      {item.department_name}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    {item.leave_type_label}
                    {item.reason && (
                      <Typography variant="caption" component="p">
                        {item.reason}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    {leavePeriod(item)}
                    {item.conflicting_shifts.length > 0 && (
                      <Typography variant="caption" component="p" color="warning.main">
                        {item.conflicting_shifts.length} planned shift(s) during this leave
                      </Typography>
                    )}
                    {item.balance_after != null && item.balance_after < 0 && (
                      <Typography variant="caption" component="p" color="warning.main">
                        {-item.balance_after} day(s) over the balance
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip size="small" color={status.color} label={status.label} />
                    {(item.decided_by_name || item.decision_note || item.cancel_reason) && (
                      <Typography variant="caption" component="p">
                        {[item.decided_by_name, item.decision_note || item.cancel_reason].filter(Boolean).join(": ")}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={1}>
                      {item.status === "requested" && (
                        <>
                          <Button
                            size="small"
                            aria-label={`Approve leave for ${item.staff_name}`}
                            onClick={() => setDeciding({ leave: item, decision: "approve" })}
                          >
                            Approve
                          </Button>
                          <Button
                            size="small"
                            color="error"
                            aria-label={`Refuse leave for ${item.staff_name}`}
                            onClick={() => setDeciding({ leave: item, decision: "reject" })}
                          >
                            Refuse
                          </Button>
                        </>
                      )}
                      {(item.status === "requested" || item.status === "approved") && item.end_date >= localDate() && (
                        <Button
                          size="small"
                          aria-label={`Cancel leave for ${item.staff_name}`}
                          onClick={() => setDeciding({ leave: item, decision: "cancel" })}
                        >
                          Cancel
                        </Button>
                      )}
                    </Stack>
                  </TableCell>
                </TableRow>
              );
            })}
            {leave.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>Nothing here.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>}
      {deciding && <DecideDialog {...deciding} onClose={() => setDeciding(null)} />}
      {recording && <RecordLeaveDialog onClose={() => setRecording(false)} />}
    </Stack>
  );
}

const TITLES: Record<LeaveDecision, string> = { approve: "Approve leave", reject: "Refuse leave", cancel: "Cancel leave" };

function DecideDialog({
  leave,
  decision,
  onClose,
}: {
  leave: LeaveRequest;
  decision: LeaveDecision;
  onClose: () => void;
}) {
  const decide = useDecideLeave(leave.id, decision);
  const [note, setNote] = useState("");
  const [cancelShifts, setCancelShifts] = useState(false);
  const [overBalance, setOverBalance] = useState(false);
  const clashes = decision === "approve" ? leave.conflicting_shifts : [];
  const after = decision === "approve" ? leave.balance_after : null;
  const isOver = after != null && after < 0;
  const needsNote = decision !== "approve" || isOver;
  return (
    <FormDialog
      title={`${TITLES[decision]} · ${leave.staff_name}`}
      error={decide.error}
      fields={["note", "reason"]}
      submitLabel={TITLES[decision]}
      submitColor={decision === "approve" ? "primary" : "error"}
      submitDisabled={
        (needsNote && !note.trim()) || (clashes.length > 0 && !cancelShifts) || (isOver && !overBalance)
      }
      pending={decide.isPending}
      onClose={onClose}
      onSubmit={() =>
        decide.mutate(
          decision === "cancel"
            ? { version: leave.version, reason: note.trim() }
            : { version: leave.version, note: note.trim(), cancel_shifts: cancelShifts, ...(overBalance ? { allow_over_balance: true } : {}) },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        {leave.leave_type_label}, {leavePeriod(leave)}.
      </Typography>
      {after != null && !isOver && (
        <Typography variant="body2">If approved, {after} day(s) of this leave are left.</Typography>
      )}
      {isOver && (
        <Alert severity="warning">
          This goes {-after} day(s) over {leave.staff_name}&apos;s balance.
          <FormControlLabel
            control={<Checkbox checked={overBalance} onChange={(e) => setOverBalance(e.target.checked)} />}
            label="Approve anyway (say why below)"
          />
        </Alert>
      )}
      {clashes.length > 0 && (
        <Alert severity="warning">
          {leave.staff_name} has {clashes.length} planned shift(s) during this leave:
          <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {clashes.map((s) => (
              <li key={s.id}>
                {formatDay(s.on_date)}: {s.shift_type_name} {s.hours}, {s.department_name}
              </li>
            ))}
          </Box>
          <FormControlLabel
            control={<Checkbox checked={cancelShifts} onChange={(e) => setCancelShifts(e.target.checked)} />}
            label="Cancel those shifts (find cover on the Rota page)"
          />
        </Alert>
      )}
      <TextField
        label={needsNote ? "Reason" : "Note (optional)"}
        required={needsNote}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        helperText={
          decision === "reject"
            ? "The person sees this, e.g. Two others are away that week"
            : isOver
              ? "Kept in the audit log. No medical details."
              : undefined
        }
      />
    </FormDialog>
  );
}

function RecordLeaveDialog({ onClose }: { onClose: () => void }) {
  const record = useRecordLeave(useState(() => crypto.randomUUID())[0]);
  const departments = useAllDepartments();
  const active = (departments.data?.results ?? []).filter((d) => d.status === "active");
  const [department, setDepartment] = useState("");
  const people = useRotaWeek(department, mondayOf(localDate()));
  const [values, setValues] = useState({ staff: "", leave_type: "sick" as LeaveType, start_date: localDate(), end_date: localDate(), reason: "" });
  const set = (field: string, value: string) => setValues({ ...values, [field]: value });
  return (
    <FormDialog
      title="Record leave for someone"
      error={record.error}
      fields={["staff", "department", "leave_type", "start_date", "end_date", "reason"]}
      submitDisabled={!department || !values.staff || !values.start_date || !values.end_date}
      pending={record.isPending}
      onClose={onClose}
      onSubmit={() => record.mutate({ ...values, department, reason: values.reason.trim() }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        For example sick leave phoned in (up to 31 days back). It still needs a decision by someone other than the
        person.
      </Typography>
      <TextField select label="Department" required value={department} onChange={(e) => setDepartment(e.target.value)}>
        {active.map((d) => (
          <MenuItem key={d.id} value={d.id}>
            {d.name} · {d.facility_name}
          </MenuItem>
        ))}
      </TextField>
      {people.error && <ErrorAlert error={people.error} />}
      <TextField select label="Person" required value={values.staff} onChange={(e) => set("staff", e.target.value)} disabled={!people.data}>
        {(people.data?.people ?? []).map((p) => (
          <MenuItem key={p.staff_id} value={p.staff_id}>
            {p.name}
          </MenuItem>
        ))}
      </TextField>
      <LeaveFields values={values} set={set} />
    </FormDialog>
  );
}
