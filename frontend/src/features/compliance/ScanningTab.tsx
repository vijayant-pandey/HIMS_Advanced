import { Alert, Box, Button, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useScanDocuments, useScanningStatus } from "./api";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <Typography component="dt" variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography component="dd" variant="body2" sx={{ m: 0 }}>
        {children}
      </Typography>
    </>
  );
}

const TRACES: Record<string, string> = {
  none: "Off: nothing is recorded",
  console: "Printed on this server only",
  otlp: "Sent to the trace collector",
};

/** Virus scanning of uploads (HIMS-SEC-013) and what traces keep (HIMS-SEC-020). Read-only: the scanner and
 * tracing are set at hosting. */
export function ScanningTab({ canManage }: { canManage: boolean }) {
  const { data, error, isLoading } = useScanningStatus();
  const scan = useScanDocuments();
  return (
    <Stack spacing={2}>
      <Typography variant="body2">
        Every file uploaded to HIMS (staff documents, the hospital logo) is checked for viruses before it is saved. A
        file with a virus is refused, never stored, recorded in the audit log and reported to the compliance team.
      </Typography>
      {isLoading && <LinearProgress aria-label="Loading scanning status" />}
      {error && <ErrorAlert error={error} />}
      {data && (
        <>
          {data.protects && data.reachable && <Alert severity="success">Uploads are checked by {data.label}.</Alert>}
          {data.protects && !data.reachable && (
            <Alert severity="error">
              The virus scanner cannot be reached, so uploads are refused until it is back. Tell whoever runs the
              hosting.
            </Alert>
          )}
          {!data.protects && data.developer_pc && (
            <Alert severity="info">
              No real virus scanner on this computer: only the standard anti-virus test file is recognised, so you can
              see a refusal. Files are recorded as not checked. Hosted environments use ClamAV.
            </Alert>
          )}
          {!data.protects && !data.developer_pc && (
            <Alert severity="error">
              Uploads are not checked for viruses. Treat this as a security finding: set up ClamAV (guide “Virus
              scanning”).
            </Alert>
          )}
          <Paper sx={{ p: 2 }}>
            <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: 1 }}>
              <Fact label="Scanner">{data.label}</Fact>
              <Fact label="Staff documents">
                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
                  <Chip size="small" color="success" label={`${data.documents.clean} checked`} />
                  <Chip size="small" label={`${data.documents.not_scanned} not checked`} />
                  <Chip
                    size="small"
                    color={data.documents.infected ? "error" : "default"}
                    label={`${data.documents.infected} blocked`}
                  />
                </Stack>
              </Fact>
              <Fact label="Viruses blocked, last 30 days">{data.blocked_last_30_days}</Fact>
            </Box>
          </Paper>
          {canManage && data.protects && (
            <Box>
              <Button
                variant="outlined"
                disabled={scan.isPending || !data.reachable || data.documents.not_scanned === 0}
                onClick={() => scan.mutate()}
              >
                Check documents not checked yet
              </Button>
              <Typography variant="caption" component="p">
                Up to 200 at a time. A virus found blocks the file and archives the document.
              </Typography>
            </Box>
          )}
          {scan.error && <ErrorAlert error={scan.error} />}
          {scan.data && (
            <Alert severity={scan.data.infected ? "warning" : "success"}>
              Checked {scan.data.checked}: {scan.data.clean} without a virus, {scan.data.infected} with a virus
              (blocked)
              {scan.data.missing ? `, ${scan.data.missing} file(s) missing` : ""}.
            </Alert>
          )}
          <Typography variant="h6" component="h2">
            Traces
          </Typography>
          <Paper sx={{ p: 2 }}>
            <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: 1 }}>
              <Fact label="Tracing">{TRACES[data.traces.exporter] ?? data.traces.exporter}</Fact>
              <Fact label="Error text in traces">
                {data.traces.error_text_filtered
                  ? "Filtered with the same rules as the logs: no passwords, links, names, emails or phone numbers"
                  : "Not filtered"}
              </Fact>
            </Box>
          </Paper>
        </>
      )}
    </Stack>
  );
}
