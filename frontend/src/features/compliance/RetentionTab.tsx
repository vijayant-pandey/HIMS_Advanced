import {
  Alert,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  FormGroup,
  FormLabel,
  LinearProgress,
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

import type { LegalHold, RetentionCategory, RetentionPurgeRun } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import {
  useLegalHolds,
  usePlaceLegalHold,
  useReleaseLegalHold,
  useRetention,
  useRetentionRuns,
  useRunPurge,
  useSetRetentionPeriod,
} from "./api";

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const formatWhen = (value?: string | null) => (value ? when.format(new Date(value)) : "—");
const days = (value?: number | null) => (value == null ? "For ever" : `${value} days`);

// --- Periods ----------------------------------------------------------------------------------

function PeriodDialog({ row, waitDays, onClose }: { row: RetentionCategory; waitDays: number; onClose: () => void }) {
  const save = useSetRetentionPeriod(row.category);
  const [forever, setForever] = useState(row.keep_days == null && row.pending_keep_days == null);
  const [value, setValue] = useState(String(row.pending_keep_days ?? row.keep_days ?? row.minimum_days));
  const number = Number(value);
  const valid = forever || (Number.isInteger(number) && number >= row.minimum_days);
  const send = (keepDays: number | null) =>
    save.mutate({ keep_days: keepDays, version: row.version }, { onSuccess: onClose });
  return (
    <FormDialog
      title={`How long to keep: ${row.label}`}
      error={save.error}
      fields={["keep_days"]}
      submitDisabled={!valid}
      pending={save.isPending}
      onClose={onClose}
      onSubmit={() => send(forever ? null : number)}
    >
      <Typography variant="body2">{row.what}</Typography>
      <FormControlLabel
        control={<Checkbox checked={forever} onChange={(e) => setForever(e.target.checked)} />}
        label="Keep for ever (nothing deleted)"
      />
      {!forever && (
        <TextField
          type="number"
          label="Keep for (days)"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          error={!valid}
          helperText={`At least ${row.minimum_days} days. A shorter period than now waits ${waitDays} days before anything is deleted, so a mistake can be undone; a longer one applies at once.`}
          slotProps={{ htmlInput: { min: row.minimum_days } }}
        />
      )}
      {row.pending_keep_days != null && (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" disabled={save.isPending} onClick={() => send(row.keep_days ?? null)}>
              Cancel it
            </Button>
          }
        >
          {days(row.pending_keep_days)} is waiting to apply on {formatWhen(row.pending_from)}.
        </Alert>
      )}
    </FormDialog>
  );
}

function PeriodsTable({ rows, waitDays, canManage }: { rows: RetentionCategory[]; waitDays: number; canManage: boolean }) {
  const [open, setOpen] = useState<RetentionCategory>();
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small" aria-label="Retention periods">
        <TableHead>
          <TableRow>
            <TableCell>Kind of record</TableCell>
            <TableCell>Kept for</TableCell>
            <TableCell>Would delete now</TableCell>
            <TableCell align="right">Kept by legal hold</TableCell>
            {canManage && <TableCell />}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.category}>
              <TableCell>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {row.label}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {row.what}
                </Typography>
              </TableCell>
              <TableCell>
                {days(row.keep_days)}
                {row.pending_keep_days != null && (
                  <Chip
                    size="small"
                    color="warning"
                    sx={{ ml: 1 }}
                    label={`${days(row.pending_keep_days)} from ${formatWhen(row.pending_from)}`}
                  />
                )}
              </TableCell>
              <TableCell>{row.skipped || row.would_delete}</TableCell>
              <TableCell align="right">{row.held}</TableCell>
              {canManage && (
                <TableCell>
                  <Button size="small" aria-label={`Change period: ${row.label}`} onClick={() => setOpen(row)}>
                    Change
                  </Button>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {open && <PeriodDialog key={open.version} row={open} waitDays={waitDays} onClose={() => setOpen(undefined)} />}
    </TableContainer>
  );
}

// --- Legal holds ------------------------------------------------------------------------------

function PlaceHoldDialog({ kinds, onClose }: { kinds: RetentionCategory[]; onClose: () => void }) {
  const place = usePlaceLegalHold(useState(() => crypto.randomUUID())[0]);
  const [form, setForm] = useState({ reference: "", reason: "", subject_email: "" });
  const [chosen, setChosen] = useState<RetentionCategory["category"][]>([]);
  const toggle = (category: RetentionCategory["category"]) =>
    setChosen((now) => (now.includes(category) ? now.filter((c) => c !== category) : [...now, category]));
  return (
    <FormDialog
      title="Place a legal hold"
      error={place.error}
      fields={["reference", "reason", "categories", "subject_email"]}
      submitLabel="Place the hold"
      submitDisabled={!form.reference.trim() || !form.reason.trim()}
      pending={place.isPending}
      onClose={onClose}
      onSubmit={() =>
        place.mutate(
          {
            reference: form.reference.trim(),
            reason: form.reason.trim(),
            categories: chosen as NonNullable<Parameters<typeof place.mutate>[0]["categories"]>,
            subject_email: form.subject_email.trim(),
          },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        While the hold is active the purge keeps these records, even past their period. Use it when a dispute or
        investigation is expected.
      </Typography>
      <TextField
        label="Reference"
        required
        value={form.reference}
        onChange={(e) => setForm({ ...form, reference: e.target.value })}
        helperText="e.g. the case or matter number"
      />
      <TextField
        label="Reason"
        required
        multiline
        minRows={2}
        value={form.reason}
        onChange={(e) => setForm({ ...form, reason: e.target.value })}
        helperText="No patient details"
      />
      <FormGroup>
        <FormLabel component="legend">Kinds of record held (none ticked = every kind)</FormLabel>
        {kinds.map((kind) => (
          <FormControlLabel
            key={kind.category}
            control={<Checkbox checked={chosen.includes(kind.category)} onChange={() => toggle(kind.category)} />}
            label={kind.label}
          />
        ))}
      </FormGroup>
      <TextField
        label="Only records about this account (email)"
        type="email"
        value={form.subject_email}
        onChange={(e) => setForm({ ...form, subject_email: e.target.value })}
        helperText="Leave empty to hold everyone's records of the kinds ticked"
      />
    </FormDialog>
  );
}

function ReleaseDialog({ hold, onClose }: { hold: LegalHold; onClose: () => void }) {
  const release = useReleaseLegalHold(hold.id);
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`Release legal hold ${hold.reference}`}
      error={release.error}
      fields={["reason"]}
      submitLabel="Release"
      submitColor="error"
      submitDisabled={!reason.trim()}
      pending={release.isPending}
      onClose={onClose}
      onSubmit={() => release.mutate({ version: hold.version, reason: reason.trim() }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        After release, the records follow the normal periods again and the next purge may delete them.
      </Typography>
      <TextField
        label="Why the hold can end"
        required
        multiline
        minRows={2}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
    </FormDialog>
  );
}

function HoldsSection({ kinds, canManage }: { kinds: RetentionCategory[]; canManage: boolean }) {
  const holds = useLegalHolds();
  const [placing, setPlacing] = useState(false);
  const [releasing, setReleasing] = useState<LegalHold>();
  const label = (category: string) => kinds.find((kind) => kind.category === category)?.label ?? category;
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
          Legal holds
        </Typography>
        {canManage && (
          <Button variant="outlined" onClick={() => setPlacing(true)}>
            Place a legal hold
          </Button>
        )}
      </Stack>
      {holds.isLoading && <LinearProgress aria-label="Loading legal holds" />}
      {holds.error && <ErrorAlert error={holds.error} />}
      {holds.data && holds.data.length === 0 && <Alert severity="info">No legal hold has been placed.</Alert>}
      {holds.data && holds.data.length > 0 && (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Legal holds">
            <TableHead>
              <TableRow>
                <TableCell>Reference</TableCell>
                <TableCell>Holds</TableCell>
                <TableCell>About</TableCell>
                <TableCell>Placed</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {holds.data.map((hold) => (
                <TableRow key={hold.id}>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {hold.reference}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {hold.reason}
                    </Typography>
                  </TableCell>
                  <TableCell>{hold.categories.length ? hold.categories.map(label).join(", ") : "Every kind"}</TableCell>
                  <TableCell>{hold.subject_name ? `${hold.subject_name} (${hold.subject_email})` : "Everyone"}</TableCell>
                  <TableCell>
                    {hold.placed_by_name ?? "—"}, {formatWhen(hold.placed_at)}
                  </TableCell>
                  <TableCell>
                    {hold.is_active ? (
                      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                        <Chip size="small" color="warning" label="Active" />
                        {canManage && (
                          <Button
                            size="small"
                            color="error"
                            aria-label={`Release legal hold ${hold.reference}`}
                            onClick={() => setReleasing(hold)}
                          >
                            Release
                          </Button>
                        )}
                      </Stack>
                    ) : (
                      <Typography variant="caption">
                        Released by {hold.released_by_name ?? "—"}, {formatWhen(hold.released_at)}: {hold.release_reason}
                      </Typography>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      {placing && <PlaceHoldDialog kinds={kinds} onClose={() => setPlacing(false)} />}
      {releasing && <ReleaseDialog key={releasing.version} hold={releasing} onClose={() => setReleasing(undefined)} />}
    </Stack>
  );
}

// --- Runs -------------------------------------------------------------------------------------

function RunsSection({ canManage }: { canManage: boolean }) {
  const runs = useRetentionRuns();
  const run = useRunPurge();
  const describe = (item: RetentionPurgeRun) =>
    Object.values(item.details).some((plan) => plan.more_left) ? " (more next run)" : "";
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
          Purge runs
        </Typography>
        {canManage && (
          <Button variant="outlined" color="error" disabled={run.isPending} onClick={() => run.mutate()}>
            Run the purge now
          </Button>
        )}
      </Stack>
      <Typography variant="body2">
        The purge runs by itself once a day. Running it now deletes the same records the daily run would.
      </Typography>
      {run.error && <ErrorAlert error={run.error} />}
      {run.data && <Alert severity="success">Purge run: {run.data.deleted_total} record(s) deleted.</Alert>}
      {runs.error && <ErrorAlert error={runs.error} />}
      {runs.data && runs.data.length === 0 && <Alert severity="info">The purge has not run yet.</Alert>}
      {runs.data && runs.data.length > 0 && (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Purge runs">
            <TableHead>
              <TableRow>
                <TableCell>When</TableCell>
                <TableCell>Run by</TableCell>
                <TableCell align="right">Deleted</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {runs.data.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{formatWhen(item.started_at)}</TableCell>
                  <TableCell>{item.run_by_name ?? item.trigger_label}</TableCell>
                  <TableCell align="right">
                    {item.deleted_total}
                    {describe(item)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Stack>
  );
}

/** Retention and legal hold (spec 4.25, 28; HIMS-COMP-006): how long housekeeping records are kept, holds that stop
 * the purge, and what each purge deleted. Clinical, financial and audit records are never purged here. */
export function RetentionTab({ canManage }: { canManage: boolean }) {
  const status = useRetention();
  return (
    <Stack spacing={2}>
      <Typography variant="body2">
        Keeping personal data longer than needed is itself a risk, so the hospital sets how long each kind of
        housekeeping record is kept, and a daily purge deletes what is older. Nothing is deleted until a period is set.
        The audit log, staff records and patient, clinical and financial records are never deleted here. Legal counsel
        decides the periods (see the retention schedule).
      </Typography>
      {status.isLoading && <LinearProgress aria-label="Loading retention periods" />}
      {status.error && <ErrorAlert error={status.error} />}
      {status.data && (
        <>
          {status.data.active_holds > 0 && (
            <Alert severity="warning">
              {status.data.active_holds} legal hold(s) active: the records they cover are kept whatever the period.
            </Alert>
          )}
          <PeriodsTable rows={status.data.categories} waitDays={status.data.wait_days} canManage={canManage} />
          <HoldsSection kinds={status.data.categories} canManage={canManage} />
        </>
      )}
      <RunsSection canManage={canManage} />
    </Stack>
  );
}
