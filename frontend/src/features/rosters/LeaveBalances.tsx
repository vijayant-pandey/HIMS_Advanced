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

import type { LeaveBalance, LeaveEntitlement, LeaveType, PersonBalances } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { useAllDepartments } from "../staff/api";
import { useAdjustBalance, useAdjustments, useLeaveBalances, useLeaveEntitlements, useSaveEntitlement } from "./api";
import { LEAVE_TYPES } from "./labels";

/** "12 left of 20 (2 carried in, 1 waiting)". */
export function balanceText(balance: LeaveBalance): string {
  const extras = [
    balance.carried_in ? `${balance.carried_in} carried in` : "",
    balance.adjusted ? `${balance.adjusted > 0 ? "+" : ""}${balance.adjusted} adjusted` : "",
    balance.waiting ? `${balance.waiting} waiting` : "",
  ].filter(Boolean);
  const main = `${balance.remaining} left of ${balance.entitled}`;
  return extras.length ? `${main} (${extras.join(", ")})` : main;
}

function AdjustDialog({
  person,
  balance,
  onClose,
}: {
  person: PersonBalances;
  balance: LeaveBalance;
  onClose: () => void;
}) {
  const adjust = useAdjustBalance(useState(() => crypto.randomUUID())[0]);
  const past = useAdjustments(person.staff_id);
  const [days, setDays] = useState("");
  const [reason, setReason] = useState("");
  const errors = fieldErrors(adjust.error);
  const count = Number(days);
  return (
    <FormDialog
      title={`Adjust balance · ${person.name}`}
      error={adjust.error}
      fields={["days", "reason"]}
      submitDisabled={!count || !Number.isInteger(count) || !reason.trim()}
      pending={adjust.isPending}
      onClose={onClose}
      onSubmit={() =>
        adjust.mutate(
          {
            staff: person.staff_id,
            leave_type: balance.leave_type as LeaveType,
            leave_year: balance.year,
            days: count,
            reason: reason.trim(),
          },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        {balance.label}, {balance.year_label}: {balanceText(balance)}.
      </Typography>
      <TextField
        type="number"
        label="Days"
        required
        value={days}
        onChange={(event) => setDays(event.target.value)}
        error={!!errors.days}
        helperText={errors.days ?? "Plus adds days, minus takes them away, e.g. 5 or -2"}
      />
      <TextField
        label="Why?"
        required
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        error={!!errors.reason}
        helperText={errors.reason ?? "e.g. Balance brought from the old system. No medical details."}
      />
      <Alert severity="info">An adjustment cannot be changed once saved. To correct a mistake, add another one.</Alert>
      {past.data && past.data.length > 0 && (
        <Box>
          <Typography variant="subtitle2" component="h2">
            Earlier adjustments
          </Typography>
          <Box component="ul" aria-label="Earlier adjustments" sx={{ m: 0, pl: 2.5 }}>
            {past.data.map((row) => (
              <Typography key={row.id} component="li" variant="body2">
                {row.days > 0 ? "+" : ""}
                {row.days}, {row.leave_type_label}, {row.leave_year}: {row.reason}
                {row.created_by_name ? ` (${row.created_by_name})` : ""}
              </Typography>
            ))}
          </Box>
        </Box>
      )}
    </FormDialog>
  );
}

/** Everyone in a department and what is left of each kind of leave (HIMS-STAFF-013). */
export function BalancesTab({ canManage }: { canManage: boolean }) {
  const departments = useAllDepartments();
  const active = (departments.data?.results ?? []).filter((d) => d.status === "active");
  const [chosen, setChosen] = useState("");
  const department = chosen || active[0]?.id || "";
  const balances = useLeaveBalances(department);
  const [adjusting, setAdjusting] = useState<{ person: PersonBalances; balance: LeaveBalance }>();
  const data = balances.data;
  const tracked = (data?.people ?? []).some((person) => person.balances.length > 0);
  return (
    <Stack spacing={2}>
      <TextField
        select
        size="small"
        label="Department"
        value={department}
        onChange={(event) => setChosen(event.target.value)}
        sx={{ maxWidth: 320 }}
      >
        {active.map((d) => (
          <MenuItem key={d.id} value={d.id}>
            {d.name} · {d.facility_name}
          </MenuItem>
        ))}
      </TextField>
      {balances.error && <ErrorAlert error={balances.error} />}
      {balances.isFetching && <LinearProgress aria-label="Loading leave balances" />}
      {data && !tracked && (
        <Alert severity="info">
          No balances yet. Set days per year under Entitlements. Kinds of leave with no entitlement have no balance.
        </Alert>
      )}
      {data && tracked && (
        <TableContainer component={Paper}>
          <Table size="small" aria-label={`Leave balances ${data.year_label}`}>
            <TableHead>
              <TableRow>
                <TableCell>Person</TableCell>
                <TableCell>Leave</TableCell>
                <TableCell>Balance {data.year_label}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {data.people.flatMap((person) =>
                person.balances.map((balance) => (
                  <TableRow key={`${person.staff_id}-${balance.leave_type}`}>
                    <TableCell>{person.name}</TableCell>
                    <TableCell>{balance.label}</TableCell>
                    <TableCell sx={{ color: balance.remaining < 0 ? "error.main" : undefined }}>
                      {balanceText(balance)}
                    </TableCell>
                    <TableCell align="right">
                      {canManage && (
                        <Button
                          size="small"
                          aria-label={`Adjust ${balance.label} for ${person.name}`}
                          onClick={() => setAdjusting({ person, balance })}
                        >
                          Adjust
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                )),
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      {adjusting && <AdjustDialog {...adjusting} onClose={() => setAdjusting(undefined)} />}
    </Stack>
  );
}

function EntitlementDialog({ row, year, onClose }: { row?: LeaveEntitlement; year: number; onClose: () => void }) {
  const save = useSaveEntitlement(row?.id, useState(() => crypto.randomUUID())[0]);
  const [leaveType, setLeaveType] = useState<LeaveType>(row?.leave_type ?? "annual");
  const [fromYear, setFromYear] = useState(String(row?.from_year ?? year));
  const [days, setDays] = useState(String(row?.days ?? 20));
  const [carry, setCarry] = useState(String(row?.max_carry_over ?? 0));
  const [prorate, setProrate] = useState(row?.prorate_on_joining ?? true);
  const [tracked, setTracked] = useState(row?.tracked ?? true);
  const errors = fieldErrors(save.error);
  const common = {
    days: Number(days),
    max_carry_over: Number(carry),
    prorate_on_joining: prorate,
    tracked,
  };
  return (
    <FormDialog
      title={row ? `Change entitlement · ${row.leave_type_label}` : "Add an entitlement"}
      error={save.error}
      fields={["leave_type", "from_year", "days", "max_carry_over"]}
      pending={save.isPending}
      onClose={onClose}
      onSubmit={() =>
        save.mutate(
          row
            ? { version: row.version, ...common }
            : { leave_type: leaveType, from_year: Number(fromYear), ...common },
          { onSuccess: onClose },
        )
      }
    >
      {!row && (
        <>
          <TextField
            select
            label="Kind of leave"
            value={leaveType}
            onChange={(event) => setLeaveType(event.target.value as LeaveType)}
          >
            {LEAVE_TYPES.map((type) => (
              <MenuItem key={type.value} value={type.value}>
                {type.label}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            type="number"
            label="From leave year"
            value={fromYear}
            onChange={(event) => setFromYear(event.target.value)}
            error={!!errors.from_year}
            helperText={errors.from_year ?? "This year or later, so past balances stay as they were."}
          />
        </>
      )}
      <TextField
        type="number"
        label="Days per leave year"
        value={days}
        onChange={(event) => setDays(event.target.value)}
        error={!!errors.days}
        helperText={errors.days}
        slotProps={{ htmlInput: { min: 0, max: 366 } }}
      />
      <TextField
        type="number"
        label="Most days carried into the next year"
        value={carry}
        onChange={(event) => setCarry(event.target.value)}
        error={!!errors.max_carry_over}
        helperText={errors.max_carry_over ?? "0 means unused days are lost."}
        slotProps={{ htmlInput: { min: 0, max: 366 } }}
      />
      <FormControlLabel
        control={<Checkbox checked={prorate} onChange={(event) => setProrate(event.target.checked)} />}
        label="Someone joining during the year gets a share by whole months"
      />
      <FormControlLabel
        control={<Checkbox checked={tracked} onChange={(event) => setTracked(event.target.checked)} />}
        label="Keep a balance for this kind of leave"
      />
    </FormDialog>
  );
}

/** Days per year, set by the hospital (HIMS-STAFF-013). */
export function EntitlementsTab({ canManage, year }: { canManage: boolean; year: number }) {
  const rows = useLeaveEntitlements();
  const [editing, setEditing] = useState<LeaveEntitlement | "new">();
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
        <Typography variant="body2" sx={{ flexGrow: 1 }}>
          Days per leave year for each kind of leave. A kind with no entitlement has no balance and no limit. An
          entitlement applies from its year until a later one replaces it. Every calendar day of leave counts, weekends
          included.
        </Typography>
        {canManage && (
          <Button variant="contained" sx={{ flexShrink: 0 }} onClick={() => setEditing("new")}>
            Add an entitlement
          </Button>
        )}
      </Stack>
      {rows.error && <ErrorAlert error={rows.error} />}
      {rows.isPending && <LinearProgress aria-label="Loading entitlements" />}
      <TableContainer component={Paper}>
        <Table size="small" aria-label="Leave entitlements">
          <TableHead>
            <TableRow>
              <TableCell>Leave</TableCell>
              <TableCell>From</TableCell>
              <TableCell>Days per year</TableCell>
              <TableCell>Most carried over</TableCell>
              <TableCell>Share when joining</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.data?.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  {row.leave_type_label}
                  {!row.tracked && <Chip size="small" label="No balance from this year" sx={{ ml: 1 }} />}
                </TableCell>
                <TableCell>{row.year_label}</TableCell>
                <TableCell>{row.days}</TableCell>
                <TableCell>{row.max_carry_over}</TableCell>
                <TableCell>{row.prorate_on_joining ? "Yes" : "No"}</TableCell>
                <TableCell align="right">
                  {canManage && row.can_change && (
                    <Button
                      size="small"
                      aria-label={`Change ${row.leave_type_label} from ${row.year_label}`}
                      onClick={() => setEditing(row)}
                    >
                      Change
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {rows.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>None set: no kind of leave has a balance or a limit.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {editing && (
        <EntitlementDialog
          row={editing === "new" ? undefined : editing}
          year={year}
          onClose={() => setEditing(undefined)}
        />
      )}
    </Stack>
  );
}
