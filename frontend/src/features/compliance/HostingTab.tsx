import {
  Alert,
  Chip,
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

import type { HostingCheck } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useHostingReadiness } from "./api";

const STATUS: Record<HostingCheck["status"], { label: string; color: "success" | "warning" | "error" }> = {
  ok: { label: "OK", color: "success" },
  warn: { label: "Before real data", color: "warning" },
  fail: { label: "Must fix", color: "error" },
};

/** Hosting readiness (HIMS-OPS-020): this server's own settings and database checked against what any host must
 * give HIMS. "Must fix" blocks going on the internet at all; "Before real data" is fine with synthetic test data. */
export function HostingTab() {
  const { data, error, isLoading } = useHostingReadiness();
  return (
    <Stack spacing={2}>
      <Typography variant="body2">
        What this server still needs before it hosts HIMS, read from its own settings. The hosting analysis compares the
        free and paid hosts against the same list.
      </Typography>
      {isLoading && <LinearProgress />}
      {error && <ErrorAlert error={error} />}
      {data && (
        <>
          {data.ready_for_real_data ? (
            <Alert severity="success">Ready for real data.</Alert>
          ) : data.ready_to_host ? (
            <Alert severity="warning">
              Fit to host with synthetic test data. {data.before_real_data} item(s) are needed before real patient data.
            </Alert>
          ) : (
            <Alert severity={data.developer_pc ? "info" : "error"}>
              {data.failing} item(s) must be fixed before this server is on the internet
              {data.developer_pc ? " (expected on a developer PC)" : ""}.
            </Alert>
          )}
          <TableContainer component={Paper}>
            <Table size="small" aria-label="Hosting readiness checks">
              <TableHead>
                <TableRow>
                  <TableCell>Check</TableCell>
                  <TableCell>Result</TableCell>
                  <TableCell>Detail</TableCell>
                  <TableCell>Fix</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.checks.map((check) => (
                  <TableRow key={check.key}>
                    <TableCell>
                      {check.label}
                      <Typography variant="caption" component="p">
                        Spec {check.spec}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip size="small" color={STATUS[check.status].color} label={STATUS[check.status].label} />
                    </TableCell>
                    <TableCell>{check.detail}</TableCell>
                    <TableCell>{check.fix}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <Typography variant="body2" color="text.secondary">
            Environment: {data.environment}. The same list: <code>python manage.py hosting_check</code> and Security
            status in the admin console.
          </Typography>
        </>
      )}
    </Stack>
  );
}
