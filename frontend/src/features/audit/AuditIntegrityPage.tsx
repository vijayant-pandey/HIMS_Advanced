import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { Link as RouterLink, useParams } from "react-router-dom";

import type { AuditIntegrityCheck, IntegrityProblem } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useIntegrityCheck, useIntegrityChecks, useIntegrityStatus, useRunIntegrityCheck } from "./integrityApi";

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const formatWhen = (value?: string | null) => (value ? when.format(new Date(value)) : "—");
const count = (value: number) => value.toLocaleString();

const RESULT: Record<AuditIntegrityCheck["outcome"], { label: string; color: "success" | "error" }> = {
  passed: { label: "Passed", color: "success" },
  failed: { label: "Problems found", color: "error" },
};

function ResultChip({ check }: { check: AuditIntegrityCheck }) {
  const result = RESULT[check.outcome];
  return <Chip size="small" color={result.color} label={result.label} />;
}

/** Long fingerprints are shown in a monospace font, wrapped, so they can be copied exactly. */
function Fingerprint({ value }: { value: string }) {
  return (
    <Typography component="span" sx={{ fontFamily: "monospace", fontSize: "0.8rem", wordBreak: "break-all" }}>
      {value || "—"}
    </Typography>
  );
}

function IncidentAdvice() {
  return (
    <Alert severity="error">
      Someone may have changed or removed audit records directly in the database. Treat this as a possible
      security incident: do not change anything, write down the reference shown below, and follow your incident
      procedure. Auditors have been emailed.
    </Alert>
  );
}

export function AuditIntegrityPage() {
  const status = useIntegrityStatus();
  const checks = useIntegrityChecks();
  const run = useRunIntegrityCheck();
  const last = status.data?.last_check ?? null;

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Audit integrity
        </Typography>
        <Typography variant="body2">
          Proof that nobody has changed or removed audit records. Every record is sealed into a chain within about a
          minute; the whole chain is checked every day, and you can check it now.
        </Typography>
        <Link component={RouterLink} to="/audit" variant="body2">
          Back to the audit log
        </Link>
      </Box>

      {status.error && <ErrorAlert error={status.error} />}
      {run.error && <ErrorAlert error={run.error} />}
      {last?.outcome === "failed" && <IncidentAdvice />}

      <Paper sx={{ p: 2 }}>
        {status.isLoading && <LinearProgress />}
        {status.data && (
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
              <Typography variant="h6" component="h2">
                Latest check
              </Typography>
              {last ? <ResultChip check={last} /> : <Chip size="small" label="Never checked" />}
              <Box sx={{ flex: 1 }} />
              <Button variant="contained" onClick={() => run.mutate()} disabled={run.isPending}>
                {run.isPending ? "Checking…" : "Check now"}
              </Button>
            </Stack>
            {run.isPending && <LinearProgress />}
            {last ? (
              <Typography variant="body2">
                {formatWhen(last.finished_at)} · {last.trigger_label}
                {last.requested_by_name ? ` (${last.requested_by_name})` : ""} · {count(last.entries_checked)} record(s)
                checked · {count(last.problem_count)} problem(s) ·{" "}
                <Link component={RouterLink} to={`/audit/integrity/${last.id}`}>
                  Details
                </Link>
              </Typography>
            ) : (
              <Typography variant="body2">No check has run yet. Press “Check now” to run the first one.</Typography>
            )}
            {run.data && (
              <Alert severity={run.data.outcome === "passed" ? "success" : "error"}>
                {run.data.outcome === "passed"
                  ? `Passed: ${count(run.data.entries_checked)} record(s) checked, nothing was changed.`
                  : `${count(run.data.problem_count)} problem(s) found.`}
              </Alert>
            )}
            <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: 1 }}>
              <Typography component="dt" variant="body2" color="text.secondary">
                Records sealed
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                {count(status.data.sealed_events)}
                {status.data.last_sealed_at && ` (last sealed ${formatWhen(status.data.last_sealed_at)})`}
              </Typography>
              <Typography component="dt" variant="body2" color="text.secondary">
                Waiting to be sealed
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                {count(status.data.waiting_to_be_sealed)} (normal: sealed within a minute, or at the next check)
              </Typography>
              <Typography component="dt" variant="body2" color="text.secondary">
                Chain fingerprint
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                <Fingerprint value={status.data.chain_head} />
              </Typography>
              <Typography component="dt" variant="body2" color="text.secondary">
                Signing key name
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                {status.data.key_id}
              </Typography>
            </Box>
            <Typography variant="caption">
              Tip: from time to time, copy the chain fingerprint of a passed check somewhere outside HIMS (for example
              your compliance register). If the history is ever rewritten, that copy will no longer match.
            </Typography>
          </Stack>
        )}
      </Paper>

      <Typography variant="h6" component="h2">
        Past checks
      </Typography>
      {checks.error && <ErrorAlert error={checks.error} />}
      <TableContainer component={Paper}>
        {checks.isLoading && <LinearProgress />}
        <Table size="small" aria-label="Past integrity checks">
          <TableHead>
            <TableRow>
              <TableCell>When</TableCell>
              <TableCell>Result</TableCell>
              <TableCell>Started by</TableCell>
              <TableCell align="right">Records checked</TableCell>
              <TableCell align="right">Problems</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {checks.data?.map((check) => (
              <TableRow key={check.id}>
                <TableCell>
                  <Link component={RouterLink} to={`/audit/integrity/${check.id}`}>
                    {formatWhen(check.finished_at)}
                  </Link>
                </TableCell>
                <TableCell>
                  <ResultChip check={check} />
                </TableCell>
                <TableCell>{check.requested_by_name ?? check.trigger_label}</TableCell>
                <TableCell align="right">{count(check.entries_checked)}</TableCell>
                <TableCell align="right">{count(check.problem_count)}</TableCell>
              </TableRow>
            ))}
            {checks.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>No checks yet.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}

function problemPlace(problem: IntegrityProblem): string {
  if (problem.last_missing != null && problem.sequence != null)
    return problem.last_missing > problem.sequence
      ? `Records #${problem.sequence} to #${problem.last_missing}`
      : `Record #${problem.sequence}`;
  if (problem.previous_last_sequence != null)
    return `Was #${problem.previous_last_sequence}, now #${problem.last_sequence ?? 0}`;
  if (problem.sequence != null) return `Record #${problem.sequence}`;
  return "Not in the chain";
}

export function AuditIntegrityDetailPage() {
  const { id = "" } = useParams();
  const { data: check, error, isLoading } = useIntegrityCheck(id);

  return (
    <Stack spacing={2}>
      <Box>
        <Link component={RouterLink} to="/audit/integrity" variant="body2">
          Back to audit integrity
        </Link>
        <Typography variant="h5" component="h1">
          Integrity check
        </Typography>
      </Box>
      {isLoading && <LinearProgress />}
      {error && <ErrorAlert error={error} />}
      {check && (
        <>
          {check.outcome === "failed" && <IncidentAdvice />}
          <Paper sx={{ p: 2 }}>
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <ResultChip check={check} />
                <Typography variant="body2">
                  {formatWhen(check.finished_at)} · {check.trigger_label}
                  {check.requested_by_name ? ` (${check.requested_by_name})` : ""}
                </Typography>
              </Stack>
              <Typography variant="body2">
                {count(check.entries_checked)} record(s) checked ({count(check.events_sealed)} newly sealed just
                before) · {count(check.problem_count)} problem(s) · {count(check.unsealed_overdue)} record(s) never
                sealed
              </Typography>
              <Typography variant="body2">
                Chain fingerprint at record #{check.last_sequence}: <Fingerprint value={check.chain_head} />
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Reference: <Fingerprint value={check.id} />
              </Typography>
            </Stack>
          </Paper>
          {check.problems.length > 0 && (
            <TableContainer component={Paper}>
              <Table size="small" aria-label="Problems found">
                <TableHead>
                  <TableRow>
                    <TableCell>What was found</TableCell>
                    <TableCell>Where</TableCell>
                    <TableCell>Record (as it is now)</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {check.problems.map((problem, index) => (
                    <TableRow key={`${problem.kind}-${problem.sequence ?? ""}-${problem.event_id ?? ""}-${index}`}>
                      <TableCell>{problem.text}</TableCell>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>{problemPlace(problem)}</TableCell>
                      <TableCell>
                        {problem.action_label ?? "—"}
                        {problem.occurred_at && (
                          <Typography variant="caption" component="p">
                            {formatWhen(problem.occurred_at)}
                          </Typography>
                        )}
                        {problem.event_id && (
                          <Typography variant="caption" component="p" sx={{ fontFamily: "monospace" }}>
                            {problem.event_id}
                          </Typography>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {check.problem_count > check.problems.length && (
                <Typography variant="caption" sx={{ p: 1, display: "block" }}>
                  Showing the first {check.problems.length} of {count(check.problem_count)} problems.
                </Typography>
              )}
            </TableContainer>
          )}
          {check.outcome === "passed" && (
            <Alert severity="success">Nothing was changed or removed up to record #{check.last_sequence}.</Alert>
          )}
        </>
      )}
    </Stack>
  );
}
