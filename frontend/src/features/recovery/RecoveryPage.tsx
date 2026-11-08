import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Link,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
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

import type { RestoreDrill } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { useBackups, useMakeBackup, useRecoveryStatus, useRestoreDrill, useRestoreDrills, useRunRestoreDrill } from "./api";

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const formatWhen = (value?: string | null) => (value ? when.format(new Date(value)) : "—");
const megabytes = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;
const count = (value: number) => value.toLocaleString();

function age(minutes: number): string {
  if (minutes < 60) return `${minutes} minute(s)`;
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)} hour(s)`;
  return `${Math.round(minutes / 60 / 24)} day(s)`;
}

const RESULT: Record<RestoreDrill["outcome"], { label: string; color: "success" | "error" }> = {
  passed: { label: "Passed", color: "success" },
  failed: { label: "Failed", color: "error" },
};

function DrillChip({ outcome }: { outcome: RestoreDrill["outcome"] }) {
  return <Chip size="small" color={RESULT[outcome].color} label={RESULT[outcome].label} />;
}

export function RecoveryPage() {
  const { data: me } = useCurrentUser();
  const canManage = hasOrganizationWidePermission(me, "recovery.manage");
  const status = useRecoveryStatus();
  const backups = useBackups();
  const drills = useRestoreDrills();
  const makeBackup = useMakeBackup();
  const runDrill = useRunRestoreDrill();
  const busy = makeBackup.isPending || runDrill.isPending;
  const info = status.data;
  const canRun = canManage && !!info?.can_run_here && !info?.tools_problem;

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Backups and restore drills
        </Typography>
        <Typography variant="body2">
          A backup only counts once it has been restored and checked. A restore drill puts a backup back into a
          separate copy (the live system is not touched), checks that every record, the audit log and every document
          came back, then removes the copy. The results are kept here as evidence.
        </Typography>
      </Box>

      {status.error && <ErrorAlert error={status.error} />}
      {makeBackup.error && <ErrorAlert error={makeBackup.error} />}
      {runDrill.error && <ErrorAlert error={runDrill.error} />}

      <Paper sx={{ p: 2 }}>
        {status.isLoading && <LinearProgress />}
        {info && (
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
              <Typography variant="h6" component="h2">
                Where things stand
              </Typography>
              {info.drill_overdue ? (
                <Chip size="small" color="warning" label="Restore drill due" />
              ) : (
                <Chip size="small" color="success" label="Restore proven" />
              )}
              <Box sx={{ flex: 1 }} />
              {canManage && (
                <Button variant="contained" onClick={() => makeBackup.mutate()} disabled={!canRun || busy}>
                  {makeBackup.isPending ? "Backing up…" : "Make a backup now"}
                </Button>
              )}
            </Stack>
            {busy && <LinearProgress />}
            {!info.can_run_here && (
              <Alert severity="info">
                This is a hosted environment: the cloud database service takes the backups here, and restore drills
                follow the cloud runbook. This page shows the drills made on a developer PC.
              </Alert>
            )}
            {info.can_run_here && info.tools_problem && <Alert severity="warning">{info.tools_problem}</Alert>}
            {makeBackup.data && (
              <Alert severity="success">
                Backup {makeBackup.data.name} made. Now run a restore drill on it to prove it can be restored.
              </Alert>
            )}
            {runDrill.data && (
              <Alert severity={runDrill.data.outcome === "passed" ? "success" : "error"}>
                {runDrill.data.outcome === "passed"
                  ? `Restore drill passed: everything came back in ${runDrill.data.restore_seconds.toFixed(1)} s.`
                  : `Restore drill failed: ${runDrill.data.problem_count} check(s) failed. `}
                <Link component={RouterLink} to={`/recovery/drills/${runDrill.data.id}`}>
                  See the checks
                </Link>
              </Alert>
            )}
            <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: 1 }}>
              <Typography component="dt" variant="body2" color="text.secondary">
                Last backup
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                {info.last_backup ? `${formatWhen(info.last_backup.created_at)} (${info.last_backup.name})` : "None yet"}
              </Typography>
              <Typography component="dt" variant="body2" color="text.secondary">
                Last passed drill
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                {info.last_passed_drill
                  ? `${formatWhen(info.last_passed_drill.finished_at)}: restored in ${info.last_passed_drill.restore_seconds.toFixed(1)} s`
                  : "None yet"}
                {` (a drill is due every ${info.drill_interval_days} days)`}
              </Typography>
              {info.can_run_here && (
                <>
                  <Typography component="dt" variant="body2" color="text.secondary">
                    Backup folder
                  </Typography>
                  <Typography component="dd" variant="body2" sx={{ m: 0, wordBreak: "break-all" }}>
                    {info.backup_folder}
                  </Typography>
                </>
              )}
            </Box>
            <Typography variant="caption">
              A backup holds every record, including password fingerprints and personal details: keep the folder
              private. The encryption and audit keys are not in it; without them a backup cannot be fully read, so keep
              them safe separately.
            </Typography>
          </Stack>
        )}
      </Paper>

      <Typography variant="h6" component="h2">
        Backups
      </Typography>
      {backups.error && <ErrorAlert error={backups.error} />}
      <TableContainer component={Paper}>
        {backups.isLoading && <LinearProgress />}
        <Table size="small" aria-label="Backups">
          <TableHead>
            <TableRow>
              <TableCell>Made</TableCell>
              <TableCell>By</TableCell>
              <TableCell align="right">Tables</TableCell>
              <TableCell align="right">Records</TableCell>
              <TableCell align="right">Documents</TableCell>
              <TableCell align="right">Size</TableCell>
              <TableCell>Latest drill</TableCell>
              {canManage && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {backups.data?.map((backup) => (
              <TableRow key={backup.id}>
                <TableCell>
                  {formatWhen(backup.created_at)}
                  <Typography variant="caption" component="p">
                    {backup.name}
                  </Typography>
                </TableCell>
                <TableCell>{backup.created_by_name ?? "Server command"}</TableCell>
                <TableCell align="right">{count(backup.tables)}</TableCell>
                <TableCell align="right">{count(backup.rows)}</TableCell>
                <TableCell align="right">{count(backup.documents)}</TableCell>
                <TableCell align="right">{megabytes(backup.dump_bytes + backup.documents_bytes)}</TableCell>
                <TableCell>
                  {backup.last_drill_outcome ? (
                    <DrillChip outcome={backup.last_drill_outcome as RestoreDrill["outcome"]} />
                  ) : (
                    "Not restored yet"
                  )}
                </TableCell>
                {canManage && (
                  <TableCell>
                    <Button
                      size="small"
                      onClick={() => runDrill.mutate(backup.id)}
                      disabled={!canRun || busy}
                      aria-label={`Run a restore drill on ${backup.name}`}
                    >
                      Run restore drill
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {backups.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={canManage ? 8 : 7}>No backups yet.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Typography variant="h6" component="h2">
        Restore drills
      </Typography>
      {drills.error && <ErrorAlert error={drills.error} />}
      <TableContainer component={Paper}>
        {drills.isLoading && <LinearProgress />}
        <Table size="small" aria-label="Restore drills">
          <TableHead>
            <TableRow>
              <TableCell>When</TableCell>
              <TableCell>Result</TableCell>
              <TableCell>Started by</TableCell>
              <TableCell>Backup</TableCell>
              <TableCell align="right">Time to restore</TableCell>
              <TableCell align="right">Backup age</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {drills.data?.map((drill) => (
              <TableRow key={drill.id}>
                <TableCell>
                  <Link component={RouterLink} to={`/recovery/drills/${drill.id}`}>
                    {formatWhen(drill.finished_at)}
                  </Link>
                </TableCell>
                <TableCell>
                  <DrillChip outcome={drill.outcome} />
                </TableCell>
                <TableCell>{drill.requested_by_name ?? drill.trigger_label}</TableCell>
                <TableCell>{drill.backup_name}</TableCell>
                <TableCell align="right">{drill.restore_seconds.toFixed(1)} s</TableCell>
                <TableCell align="right">{age(drill.backup_age_minutes)}</TableCell>
              </TableRow>
            ))}
            {drills.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>No restore drills yet.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}

export function RestoreDrillPage() {
  const { id = "" } = useParams();
  const { data: drill, error, isLoading } = useRestoreDrill(id);

  return (
    <Stack spacing={2}>
      <Box>
        <Link component={RouterLink} to="/recovery" variant="body2">
          Back to backups and restore drills
        </Link>
        <Typography variant="h5" component="h1">
          Restore drill
        </Typography>
      </Box>
      {isLoading && <LinearProgress />}
      {error && <ErrorAlert error={error} />}
      {drill && (
        <>
          {drill.outcome === "failed" && (
            <Alert severity="error">
              This backup could not be fully restored. Do not rely on it: make a new backup, run a drill on it, and look
              into the failed checks below.
            </Alert>
          )}
          <Paper sx={{ p: 2 }}>
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <DrillChip outcome={drill.outcome} />
                <Typography variant="body2">
                  {formatWhen(drill.finished_at)} · {drill.requested_by_name ?? drill.trigger_label}
                </Typography>
              </Stack>
              <Typography variant="body2">
                Backup {drill.backup_name} made {formatWhen(drill.backup_created_at)} ({age(drill.backup_age_minutes)}{" "}
                old) · restored in {drill.restore_seconds.toFixed(1)} s into a separate copy, removed afterwards
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Reference: {drill.id}
              </Typography>
            </Stack>
          </Paper>
          <Paper>
            <List aria-label="Checks" dense>
              {drill.checks.map((check) => (
                <ListItem key={check.key}>
                  <ListItemIcon sx={{ minWidth: 72 }}>
                    <Chip size="small" color={check.passed ? "success" : "error"} label={check.passed ? "OK" : "Failed"} />
                  </ListItemIcon>
                  <ListItemText primary={check.label} secondary={check.detail || undefined} />
                </ListItem>
              ))}
            </List>
          </Paper>
        </>
      )}
    </Stack>
  );
}
