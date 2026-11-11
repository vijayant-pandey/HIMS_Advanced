import {
  Alert,
  Chip,
  LinearProgress,
  List,
  ListItem,
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

import type { ReviewFinding, SecurityTestCase } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useSecurityReview } from "./api";

const SEVERITY_COLOR: Record<ReviewFinding["severity"], "error" | "warning" | "info" | "default"> = {
  high: "error",
  medium: "warning",
  low: "info",
  info: "default",
};

const CASE_COLOR: Record<SecurityTestCase["status"], "success" | "info" | "default"> = {
  tested: "success",
  phase1_form: "info",
  waits: "default",
};

/** The Phase 1 security review of the threat model (HIMS-SEC-011): findings and their fixes, the ten security tests
 * of spec 13.5, what remains before real patient data, and whether an old encryption key can be removed. Read-only. */
export function SecurityReviewTab() {
  const { data, error, isLoading } = useSecurityReview();
  return (
    <Stack spacing={2}>
      {isLoading && <LinearProgress />}
      {error && <ErrorAlert error={error} />}
      {data && (
        <>
          <Typography variant="body2">
            Reviewed {new Date(`${data.reviewed_on}T00:00:00`).toLocaleDateString()}. {data.reviewer}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {data.scope}
          </Typography>

          <Typography variant="h6" component="h2">
            Findings
          </Typography>
          <TableContainer component={Paper}>
            <Table size="small" aria-label="Security review findings">
              <TableHead>
                <TableRow>
                  <TableCell>Finding</TableCell>
                  <TableCell>What was done</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.findings.map((finding) => (
                  <TableRow key={finding.code}>
                    <TableCell>
                      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
                        <strong>{finding.code}</strong>
                        <Chip size="small" color={SEVERITY_COLOR[finding.severity]} label={finding.severity} />
                        <Typography variant="caption">{finding.area}</Typography>
                      </Stack>
                      {finding.finding}
                    </TableCell>
                    <TableCell>{finding.fix}</TableCell>
                    <TableCell>{finding.status === "fixed" ? "Fixed" : "Accepted"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Typography variant="h6" component="h2">
            The ten security tests of spec 13.5
          </Typography>
          <TableContainer component={Paper}>
            <Table size="small" aria-label="Security tests">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell>
                  <TableCell>Case</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>How</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.cases.map((item) => (
                  <TableRow key={item.number}>
                    <TableCell>{item.number}</TableCell>
                    <TableCell>{item.case}</TableCell>
                    <TableCell>
                      <Chip size="small" color={CASE_COLOR[item.status]} label={item.status_label} />
                    </TableCell>
                    <TableCell>
                      {item.how}
                      {item.tests > 0 && (
                        <Typography variant="caption" component="p">
                          {item.tests} automated test{item.tests === 1 ? "" : "s"}
                        </Typography>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Typography variant="h6" component="h2">
            Encryption keys for stored secrets
          </Typography>
          {data.encryption.on_older_keys === 0 ? (
            <Alert severity="success">
              {data.encryption.keys} key(s) configured; every stored secret uses the newest key, so older keys can be
              removed.
            </Alert>
          ) : (
            <Alert severity="warning">
              {data.encryption.on_older_keys} stored secret(s) still need an older key. Run{" "}
              <code>python manage.py rotate_encryption_keys</code> before removing it.
            </Alert>
          )}

          <Typography variant="h6" component="h2">
            Before real patient data
          </Typography>
          <Paper>
            <List dense aria-label="Before real patient data">
              {data.before_go_live.map((item) => (
                <ListItem key={item.ticket}>
                  <ListItemText primary={item.what} secondary={item.ticket} />
                </ListItem>
              ))}
            </List>
          </Paper>
        </>
      )}
    </Stack>
  );
}
