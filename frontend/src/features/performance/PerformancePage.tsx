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

import type { PerformanceCheck } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { usePerformanceCheck, usePerformanceChecks, usePerformanceStatus, useRunIndexCheck } from "./api";

/** Performance checks (spec 18, 28.6; HIMS-DATA-002, HIMS-OPS-017). */

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const formatWhen = (value?: string | null) => (value ? when.format(new Date(value)) : "—");
const count = (value: number) => value.toLocaleString();
const ms = (value: number) => `${value.toFixed(value < 10 ? 1 : 0)} ms`;

function ResultChip({ outcome }: { outcome: PerformanceCheck["outcome"] }) {
  return outcome === "passed" ? (
    <Chip size="small" color="success" label="Passed" />
  ) : (
    <Chip size="small" color="error" label="Failed" />
  );
}

function Latest({ title, check }: { title: string; check?: PerformanceCheck | null }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, flex: 1, minWidth: 220 }}>
      <Typography variant="subtitle2" component="h3">
        {title}
      </Typography>
      {check ? (
        <Stack spacing={0.5} sx={{ mt: 0.5 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <ResultChip outcome={check.outcome} />
            <Link component={RouterLink} to={`/performance/${check.id}`} variant="body2">
              {formatWhen(check.finished_at)}
            </Link>
          </Stack>
          <Typography variant="body2">{check.summary}</Typography>
          <Typography variant="caption">{count(check.dataset_rows)} records in the main tables</Typography>
        </Stack>
      ) : (
        <Typography variant="body2">Not run yet.</Typography>
      )}
    </Paper>
  );
}

export function PerformancePage() {
  const { data: me } = useCurrentUser();
  const canRun = hasOrganizationWidePermission(me, "platform.performance.manage");
  const status = usePerformanceStatus();
  const checks = usePerformanceChecks();
  const runCheck = useRunIndexCheck();
  const info = status.data;

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Performance
        </Typography>
        <Typography variant="body2">
          Two checks keep HIMS fast as the records grow. The <b>index check</b> asks the database how it answers the
          busiest searches and confirms each one uses its index. The <b>response times</b> measure how long the main
          screens take to answer. The real test is the <b>volume check</b>: both run on a throw-away copy filled with
          the records of a large hospital (all invented), which is removed afterwards.
        </Typography>
      </Box>

      {status.error && <ErrorAlert error={status.error} />}
      {runCheck.error && <ErrorAlert error={runCheck.error} />}

      <Paper sx={{ p: 2 }}>
        {status.isLoading && <LinearProgress />}
        {info && (
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
              <Typography variant="h6" component="h2">
                Targets
              </Typography>
              <Box sx={{ flex: 1 }} />
              {canRun && (
                <Button variant="contained" onClick={() => runCheck.mutate()} disabled={runCheck.isPending}>
                  {runCheck.isPending ? "Checking…" : "Run the index check now"}
                </Button>
              )}
            </Stack>
            {runCheck.isPending && <LinearProgress />}
            {runCheck.data && (
              <Alert severity={runCheck.data.outcome === "passed" ? "success" : "error"}>
                Index check {runCheck.data.outcome === "passed" ? "passed" : "failed"}: {runCheck.data.summary}.{" "}
                <Link component={RouterLink} to={`/performance/${runCheck.data.id}`}>
                  See each query
                </Link>
              </Alert>
            )}
            <Typography variant="body2">
              95 out of 100 answers within <b>{ms(info.page_target_ms)}</b> for screens showing one record or a short
              list, and within <b>{ms(info.search_target_ms)}</b> for searches and long lists (spec 18). Each busy search
              uses its index and takes at most 100 ms in the database.
            </Typography>
            {!info.can_measure_here && (
              <Alert severity="info">
                This is a hosted environment: response times come from monitoring real use and from the load test. The
                index check can still be run here; it only reads.
              </Alert>
            )}
            <Typography variant="subtitle1" component="h2">
              At the size of a large hospital (volume check)
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
              <Latest title="Index check" check={info.last_volume_index_check} />
              <Latest title="Response times" check={info.last_volume_response_times} />
            </Stack>
            <Typography variant="subtitle1" component="h2">
              Latest of each kind, any database
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
              <Latest title="Index check" check={info.last_index_check} />
              <Latest title="Response times" check={info.last_response_times} />
            </Stack>
            <Typography variant="caption">
              The volume check and response times run from the server command line on a developer PC: see the
              performance checks guide. Results cannot be changed or deleted.
            </Typography>
          </Stack>
        )}
      </Paper>

      <Typography variant="h6" component="h2">
        All checks
      </Typography>
      {checks.error && <ErrorAlert error={checks.error} />}
      <TableContainer component={Paper}>
        {checks.isLoading && <LinearProgress />}
        <Table size="small" aria-label="Performance checks">
          <TableHead>
            <TableRow>
              <TableCell>When</TableCell>
              <TableCell>Check</TableCell>
              <TableCell>Result</TableCell>
              <TableCell>Database</TableCell>
              <TableCell align="right">Records</TableCell>
              <TableCell>Started by</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {checks.data?.map((check) => (
              <TableRow key={check.id}>
                <TableCell>
                  <Link component={RouterLink} to={`/performance/${check.id}`}>
                    {formatWhen(check.finished_at)}
                  </Link>
                </TableCell>
                <TableCell>
                  {check.kind_label}
                  <Typography variant="caption" component="p">
                    {check.summary}
                  </Typography>
                </TableCell>
                <TableCell>
                  <ResultChip outcome={check.outcome} />
                </TableCell>
                <TableCell>{check.database}</TableCell>
                <TableCell align="right">{count(check.dataset_rows)}</TableCell>
                <TableCell>{check.requested_by_name ?? check.trigger_label}</TableCell>
              </TableRow>
            ))}
            {checks.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>No checks yet.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}

export function PerformanceCheckPage() {
  const { id = "" } = useParams();
  const { data: check, error, isLoading } = usePerformanceCheck(id);
  const tables = Object.entries(check?.dataset ?? {}).sort(([, a], [, b]) => b - a);

  return (
    <Stack spacing={2}>
      <Box>
        <Link component={RouterLink} to="/performance" variant="body2">
          Back to performance
        </Link>
        <Typography variant="h5" component="h1">
          {check?.kind_label ?? "Performance check"}
        </Typography>
      </Box>
      {isLoading && <LinearProgress />}
      {error && <ErrorAlert error={error} />}
      {check && (
        <>
          <Paper sx={{ p: 2 }}>
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <ResultChip outcome={check.outcome} />
                <Typography variant="body2">
                  {formatWhen(check.finished_at)} · {check.requested_by_name ?? check.trigger_label}
                </Typography>
              </Stack>
              <Typography variant="body2">
                {check.summary} · {check.database} · {count(check.dataset_rows)} records in the main tables
              </Typography>
              {tables.length > 0 && (
                <Typography variant="caption">
                  {tables.map(([table, rows]) => `${table} ${count(rows)}`).join(" · ")}
                </Typography>
              )}
            </Stack>
          </Paper>

          {check.query_results.length > 0 && (
            <TableContainer component={Paper}>
              <Table size="small" aria-label="Queries">
                <TableHead>
                  <TableRow>
                    <TableCell>Result</TableCell>
                    <TableCell>Query</TableCell>
                    <TableCell align="right">Table rows</TableCell>
                    <TableCell align="right">Time</TableCell>
                    <TableCell>Index used</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {check.query_results.map((item) => (
                    <TableRow key={item.key}>
                      <TableCell>
                        <Chip
                          size="small"
                          color={item.passed ? "success" : "error"}
                          label={item.passed ? "OK" : "Failed"}
                        />
                      </TableCell>
                      <TableCell>
                        {item.label}
                        {item.detail && (
                          <Typography variant="caption" component="p">
                            {item.detail}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell align="right">{count(item.table_rows)}</TableCell>
                      <TableCell align="right">
                        {ms(item.ms)}
                        <Typography variant="caption" component="p">
                          budget {ms(item.budget_ms)}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ wordBreak: "break-word" }}>
                        {item.indexes_used.join(", ") || "none (whole table read)"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}

          {check.screen_results.length > 0 && (
            <TableContainer component={Paper}>
              <Table size="small" aria-label="Screens">
                <TableHead>
                  <TableRow>
                    <TableCell>Result</TableCell>
                    <TableCell>Screen</TableCell>
                    <TableCell align="right">Typical (p50)</TableCell>
                    <TableCell align="right">95 of 100 within (p95)</TableCell>
                    <TableCell align="right">Target</TableCell>
                    <TableCell align="right">Queries</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {check.screen_results.map((item) => (
                    <TableRow key={item.key}>
                      <TableCell>
                        <Chip
                          size="small"
                          color={item.passed ? "success" : "error"}
                          label={item.passed ? "OK" : "Failed"}
                        />
                      </TableCell>
                      <TableCell>
                        {item.label}
                        {item.detail && (
                          <Typography variant="caption" component="p">
                            {item.detail}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell align="right">{ms(item.p50_ms)}</TableCell>
                      <TableCell align="right">{ms(item.p95_ms)}</TableCell>
                      <TableCell align="right">{ms(item.target_ms)}</TableCell>
                      <TableCell align="right">{item.queries}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </>
      )}
    </Stack>
  );
}
