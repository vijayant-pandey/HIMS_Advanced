import {
  Box,
  Chip,
  LinearProgress,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useScheduledJobs } from "./api";

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function every(seconds: number): string {
  if (seconds % 86_400 === 0) return seconds === 86_400 ? "Every day" : `Every ${seconds / 86_400} days`;
  if (seconds % 3_600 === 0) return seconds === 3_600 ? "Every hour" : `Every ${seconds / 3_600} hours`;
  if (seconds % 60 === 0) return seconds === 60 ? "Every minute" : `Every ${seconds / 60} minutes`;
  return `Every ${seconds} seconds`;
}

const OUTCOME: Record<string, { label: string; color: "success" | "error" | "info" }> = {
  ok: { label: "Finished", color: "success" },
  failed: { label: "Failed", color: "error" },
  running: { label: "Running", color: "info" },
};

/** The scheduled jobs (HIMS-OPS-023): what runs on its own, how often, and how the last run went when the host's
 * timer starts them with run_scheduled_jobs. With Celery beat the runs are in the worker's log instead. */
export function ScheduledJobsSection() {
  const { data, error, isLoading } = useScheduledJobs();
  const neverRun = (data ?? []).every((job) => !job.last_started_at);
  return (
    <Box>
      <Typography variant="h6" component="h2">
        Scheduled jobs
      </Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>
        Work HIMS does on its own, on a timer.
        {data && neverRun
          ? " No runs recorded here: on this server they are run by the scheduler (Celery beat), or not at all on a developer PC."
          : ""}
      </Typography>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isLoading && <LinearProgress />}
        <Table size="small" aria-label="Scheduled jobs">
          <TableHead>
            <TableRow>
              <TableCell>Job</TableCell>
              <TableCell>How often</TableCell>
              <TableCell>Last run</TableCell>
              <TableCell>Result</TableCell>
              <TableCell align="right">Runs</TableCell>
              <TableCell>Last problem</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.map((job) => (
              <TableRow key={job.name}>
                <TableCell>{job.label}</TableCell>
                <TableCell>{every(job.every_seconds)}</TableCell>
                <TableCell>
                  {job.last_started_at ? when.format(new Date(job.last_started_at)) : "Never"}
                  {job.last_duration_ms !== null && (
                    <Typography variant="caption" component="p">
                      took {job.last_duration_ms} ms
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  {job.last_outcome ? (
                    <Chip
                      size="small"
                      color={OUTCOME[job.last_outcome]?.color ?? "info"}
                      label={OUTCOME[job.last_outcome]?.label ?? job.last_outcome}
                    />
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell align="right">
                  {job.runs}
                  {job.failures > 0 && ` (${job.failures} failed)`}
                </TableCell>
                <TableCell>{job.last_error || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
