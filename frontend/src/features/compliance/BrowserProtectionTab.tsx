import {
  Alert,
  Button,
  LinearProgress,
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

import type { BrowserSecurityReport } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useBrowserReports, useReviewBrowserReport, useSecurityStatus } from "./api";

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function ReviewButton({ report }: { report: BrowserSecurityReport }) {
  const review = useReviewBrowserReport(report.id);
  return (
    <>
      <Button
        size="small"
        disabled={review.isPending}
        aria-label={`Mark reviewed: ${report.directive} on ${report.day}`}
        onClick={() => review.mutate({ version: report.version })}
      >
        Mark reviewed
      </Button>
      {review.error && <ErrorAlert error={review.error} />}
    </>
  );
}

export function BrowserProtectionTab({ canManage }: { canManage: boolean }) {
  const status = useSecurityStatus();
  const reports = useBrowserReports();
  return (
    <Stack spacing={2}>
      <Typography variant="body2">
        HIMS tells browsers to load scripts and connect only to this hospital's own address, so injected code cannot
        run or send data elsewhere. Anything a browser blocks is listed here. One or two entries can be a browser
        add-on. Many entries, or a site you don't recognise, should be reported as a security incident.
      </Typography>
      {status.error && <ErrorAlert error={status.error} />}
      {status.data && (
        <>
          {status.data.policy_mode === "report_only" ? (
            <Alert severity="warning">
              Report-only mode: the admin console and server pages are reporting problems but not blocking them. Turn
              this off once the problem is fixed.
            </Alert>
          ) : (
            <Alert severity="success">Blocking is on for the admin console and server pages.</Alert>
          )}
          <Typography variant="body2">
            HIMS sees your address as <strong>{status.data.your_address ?? "unknown"}</strong>. This is the address
            written to the audit log.
            {!status.data.proxies_configured &&
              " No proxy addresses are set, which is correct when running without a load balancer."}
          </Typography>
        </>
      )}
      {reports.isLoading && <LinearProgress aria-label="Loading browser reports" />}
      {reports.error && <ErrorAlert error={reports.error} />}
      {reports.data && reports.data.length === 0 && <Alert severity="info">Nothing has been blocked.</Alert>}
      {reports.data && reports.data.length > 0 && (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="What browsers blocked">
            <TableHead>
              <TableRow>
                <TableCell>Day</TableCell>
                <TableCell>What was blocked</TableCell>
                <TableCell>Rule</TableCell>
                <TableCell>Page</TableCell>
                <TableCell align="right">Times</TableCell>
                <TableCell>Review</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {reports.data.map((report) => (
                <TableRow key={report.id}>
                  <TableCell>{report.day}</TableCell>
                  <TableCell>{report.blocked}</TableCell>
                  <TableCell>{report.directive}</TableCell>
                  <TableCell>{report.page_path || "—"}</TableCell>
                  <TableCell align="right">{report.occurrences}</TableCell>
                  <TableCell>
                    {report.reviewed_at ? (
                      <Typography variant="caption">
                        {report.reviewed_by_name ?? "Reviewed"}, {when.format(new Date(report.reviewed_at))}
                      </Typography>
                    ) : canManage ? (
                      <ReviewButton report={report} />
                    ) : (
                      "Not reviewed"
                    )}
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
