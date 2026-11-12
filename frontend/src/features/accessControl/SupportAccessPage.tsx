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

import type { SupportAccess } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { formatWhen } from "./CoverPage";
import {
  type SupportFilter,
  useAskForSupportAccess,
  useMySupportRequests,
  useSupportDecision,
  useSupportOptions,
  useSupportRequests,
} from "./supportAccessApi";

const STATUS_COLOR: Record<SupportAccess["status"], "success" | "info" | "default" | "warning" | "error"> = {
  waiting: "info",
  active: "success",
  finished: "default",
  refused: "error",
  cancelled: "default",
  ended_early: "warning",
};

export function SupportStatusChip({ access }: { access: SupportAccess }) {
  return <Chip size="small" color={STATUS_COLOR[access.status]} label={access.status_label} />;
}

function AskDialog({ onClose, onDone }: { onClose: () => void; onDone: (access: SupportAccess) => void }) {
  const ask = useAskForSupportAccess(useState(() => crypto.randomUUID())[0]);
  const options = useSupportOptions();
  const [role, setRole] = useState("");
  const [hours, setHours] = useState("");
  const [reason, setReason] = useState("");
  const [emergency, setEmergency] = useState(false);
  const chosenHours = Number(hours || options.data?.default_hours || 2);
  const ready = !!role && !!reason.trim() && chosenHours >= 1 && chosenHours <= (options.data?.max_hours ?? 8);

  return (
    <FormDialog
      title="Ask for support access"
      error={ask.error ?? options.error}
      fields={["role", "hours", "reason", "emergency"]}
      submitLabel={emergency ? "Open emergency access now" : "Ask the hospital"}
      submitColor={emergency ? "error" : "primary"}
      submitDisabled={!ready}
      pending={ask.isPending}
      onClose={onClose}
      onSubmit={() =>
        ask.mutate({ role, hours: chosenHours, reason: reason.trim(), emergency }, { onSuccess: onDone })
      }
    >
      <Typography variant="body2">
        The hospital&apos;s administrator approves or refuses this. The access ends by itself after the hours you ask
        for, and every request you make while it lasts is recorded in the hospital&apos;s audit log.
      </Typography>
      {options.isPending && <LinearProgress />}
      <TextField select label="Access" required value={role} onChange={(e) => setRole(e.target.value)}>
        {options.data?.roles.map((r) => (
          <MenuItem key={r.id} value={r.id}>
            {r.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        type="number"
        label="Hours"
        value={hours}
        placeholder={String(options.data?.default_hours ?? 2)}
        onChange={(e) => setHours(e.target.value)}
        helperText={`1 to ${options.data?.max_hours ?? 8} hours (${options.data?.default_hours ?? 2} if left empty)`}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: 1, max: options.data?.max_hours ?? 8 } }}
      />
      <TextField
        label="Reason"
        required
        multiline
        minRows={2}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        helperText="What you need to check or fix. No patient details."
      />
      <FormControlLabel
        control={<Checkbox checked={emergency} onChange={(e) => setEmergency(e.target.checked)} />}
        label="Emergency: open it now without waiting for the hospital"
      />
      {emergency && (
        <Alert severity="warning">
          Emergency access opens at once.{" "}
          {options.data?.emergency_notice
            ? "The hospital's administrators are emailed."
            : "The hospital is not emailed, but it is shown on their Support access page and in the audit log."}
        </Alert>
      )}
    </FormDialog>
  );
}

function DecisionDialog({
  access,
  decision,
  mine,
  onClose,
}: {
  access: SupportAccess;
  decision: "approve" | "refuse" | "end" | "cancel";
  mine: boolean;
  onClose: () => void;
}) {
  const act = useSupportDecision(access.id, decision, mine);
  const [text, setText] = useState("");
  const needsText = decision === "refuse" || decision === "end";
  const titles = {
    approve: `Approve · ${access.role.name} for ${access.hours} hour(s)`,
    refuse: "Refuse the request",
    end: "End the access now",
    cancel: "Cancel your request",
  };
  const labels = { approve: "Approve", refuse: "Refuse", end: "End now", cancel: "Cancel request" };
  return (
    <FormDialog
      title={titles[decision]}
      error={act.error}
      fields={["note", "reason"]}
      submitLabel={labels[decision]}
      submitColor={decision === "approve" ? "primary" : "error"}
      submitDisabled={needsText && !text.trim()}
      pending={act.isPending}
      onClose={onClose}
      onSubmit={() =>
        act.mutate(
          decision === "end"
            ? { version: access.version, reason: text.trim() }
            : { version: access.version, note: text.trim() },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        {decision === "approve" &&
          `${access.requested_by.display_name} gets ${access.role.name} access from now for ${access.hours} hour(s). It ends by itself.`}
        {decision === "refuse" && "The supplier is told the reason."}
        {decision === "end" && "The access is removed at once."}
        {decision === "cancel" && "The hospital no longer sees it as waiting."}
      </Typography>
      {decision !== "cancel" && (
        <TextField
          label={decision === "end" ? "Why does it end now?" : decision === "refuse" ? "Why is it refused?" : "Note (optional)"}
          required={needsText}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      )}
    </FormDialog>
  );
}

function RequestsTable({
  rows,
  label,
  mine,
  canAct,
  empty,
  onAct,
}: {
  rows: SupportAccess[] | undefined;
  label: string;
  mine: boolean;
  canAct: boolean;
  empty: string;
  onAct: (access: SupportAccess, decision: "approve" | "refuse" | "end" | "cancel") => void;
}) {
  return (
    <TableContainer component={Paper}>
      <Table size="small" aria-label={label}>
        <TableHead>
          <TableRow>
            {!mine && <TableCell>Supplier</TableCell>}
            <TableCell>Access</TableCell>
            <TableCell>Reason</TableCell>
            <TableCell>Asked</TableCell>
            <TableCell>Runs</TableCell>
            <TableCell>Status</TableCell>
            <TableCell />
          </TableRow>
        </TableHead>
        <TableBody>
          {rows?.map((access) => (
            <TableRow key={access.id}>
              {!mine && <TableCell>{access.requested_by.display_name}</TableCell>}
              <TableCell>
                {access.role.name}
                <Typography variant="caption" component="p">
                  {access.hours} hour(s)
                </Typography>
                {access.kind === "emergency" && <Chip size="small" color="error" variant="outlined" label="Emergency" />}
              </TableCell>
              <TableCell>{access.reason}</TableCell>
              <TableCell sx={{ whiteSpace: "nowrap" }}>{formatWhen(access.created_at)}</TableCell>
              <TableCell sx={{ whiteSpace: "nowrap" }}>
                {access.starts_at ? (
                  <>
                    {formatWhen(access.starts_at)}
                    <Typography variant="caption" component="p">
                      to {formatWhen(access.ends_at)}
                    </Typography>
                  </>
                ) : (
                  "—"
                )}
              </TableCell>
              <TableCell>
                <SupportStatusChip access={access} />
                {(access.decision_note || access.end_reason) && (
                  <Typography variant="caption" component="p">
                    {access.end_reason || access.decision_note}
                    {access.ended_by_name || access.decided_by_name
                      ? ` (${access.ended_by_name ?? access.decided_by_name})`
                      : ""}
                  </Typography>
                )}
              </TableCell>
              <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                {canAct && access.status === "waiting" && !mine && (
                  <>
                    <Button size="small" onClick={() => onAct(access, "approve")}>
                      Approve
                    </Button>
                    <Button size="small" color="error" onClick={() => onAct(access, "refuse")}>
                      Refuse
                    </Button>
                  </>
                )}
                {canAct && access.status === "waiting" && mine && (
                  <Button size="small" onClick={() => onAct(access, "cancel")}>
                    Cancel
                  </Button>
                )}
                {canAct && access.status === "active" && (
                  <Button size="small" color="error" onClick={() => onAct(access, "end")}>
                    End now
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
          {rows?.length === 0 && (
            <TableRow>
              <TableCell colSpan={mine ? 6 : 7}>{empty}</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

/** Supplier support access, the "locked box" (HIMS-IAM-021): the hospital decides, the supplier asks. */
export function SupportAccessPage() {
  const { data: me } = useCurrentUser();
  const canManage = hasOrganizationWidePermission(me, "support.access.manage");
  const canAsk = hasOrganizationWidePermission(me, "support.access.request");
  const [tab, setTab] = useState<SupportFilter>("current");
  const hospital = useSupportRequests(tab, canManage);
  const mine = useMySupportRequests(canAsk);
  const [asking, setAsking] = useState(false);
  const [acting, setActing] = useState<{ access: SupportAccess; decision: "approve" | "refuse" | "end" | "cancel"; mine: boolean }>();
  const [created, setCreated] = useState<SupportAccess>();

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
        <Box>
          <Typography variant="h5" component="h1">
            Support access
          </Typography>
          <Typography variant="body2">
            The software supplier&apos;s support account has no access to this hospital of its own. It asks for access
            for a few hours with a reason; the hospital approves or refuses it. In an emergency the supplier can open it
            at once. The access ends by itself, and every request the supplier makes while it lasts is in the audit log.
          </Typography>
        </Box>
        {canAsk && (
          <Button variant="contained" onClick={() => setAsking(true)}>
            Ask for access
          </Button>
        )}
      </Box>

      {created && (
        <Alert severity="success" onClose={() => setCreated(undefined)}>
          {created.status === "active"
            ? `${created.role.name} access is open until ${formatWhen(created.ends_at)}.`
            : "Your request is waiting for the hospital."}
        </Alert>
      )}

      {canAsk && (
        <>
          <Typography variant="h6" component="h2">
            Your requests
          </Typography>
          {mine.error && <ErrorAlert error={mine.error} />}
          {mine.isPending && <LinearProgress />}
          <RequestsTable
            rows={mine.data}
            label="Your support access requests"
            mine
            canAct
            empty="You have not asked for access yet."
            onAct={(access, decision) => setActing({ access, decision, mine: true })}
          />
        </>
      )}

      {canManage && (
        <>
          <Tabs value={tab} onChange={(_, value: SupportFilter) => setTab(value)}>
            <Tab value="current" label="Waiting and running" />
            <Tab value="past" label="Past" />
          </Tabs>
          {hospital.error && <ErrorAlert error={hospital.error} />}
          {hospital.isPending && <LinearProgress />}
          <RequestsTable
            rows={hospital.data}
            label="Support access requests"
            mine={false}
            canAct
            empty={tab === "current" ? "Nothing is waiting or running." : "No past support access."}
            onAct={(access, decision) => setActing({ access, decision, mine: false })}
          />
        </>
      )}

      {asking && (
        <AskDialog
          onClose={() => setAsking(false)}
          onDone={(access) => {
            setAsking(false);
            setCreated(access);
          }}
        />
      )}
      {acting && <DecisionDialog {...acting} onClose={() => setActing(undefined)} />}
    </Stack>
  );
}
