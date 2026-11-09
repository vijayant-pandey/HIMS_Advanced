import {
  Alert,
  Button,
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

import type { ConsoleAccessBlock } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useConsoleAccess, useConsoleRefusals, useReviewConsoleRefusal } from "./api";

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function ReviewButton({ refusal }: { refusal: ConsoleAccessBlock }) {
  const review = useReviewConsoleRefusal(refusal.id);
  return (
    <>
      <Button
        size="small"
        disabled={review.isPending}
        aria-label={`Mark reviewed: ${refusal.ip_address} on ${refusal.day}`}
        onClick={() => review.mutate({ version: refusal.version })}
      >
        Mark reviewed
      </Button>
      {review.error && <ErrorAlert error={review.error} />}
    </>
  );
}

/** Console access (HIMS-SEC-015): the admin console answers only listed addresses. Read-only by design: the list is
 * a server setting, so what protects the console cannot be changed through the app or the console. */
export function ConsoleAccessTab({ canManage }: { canManage: boolean }) {
  const status = useConsoleAccess();
  const refusals = useConsoleRefusals();
  return (
    <Stack spacing={2}>
      <Typography variant="body2">
        The admin console answers only the addresses listed below, such as this hospital's office or VPN network.
        Anyone else gets "Not found", before they can even try a password, and a stolen session does not help from
        elsewhere. Refused addresses are listed here. A few can be a staff member working from home; a session that
        was signed in, or many addresses, should be reported as a security incident.
      </Typography>
      {status.error && <ErrorAlert error={status.error} />}
      {status.data && (
        <>
          {!status.data.enabled ? (
            <Alert severity="info">The admin console is switched off on this server.</Alert>
          ) : status.data.you_are_allowed ? (
            <Alert severity="success">
              Your address ({status.data.your_address}) can use the admin console.
            </Alert>
          ) : (
            <Alert severity="warning">
              Your address ({status.data.your_address ?? "unknown"}) is not on the list, so the admin console will
              show "Not found" for you.
            </Alert>
          )}
          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", rowGap: 1, alignItems: "center" }}>
            <Typography variant="body2" component="span">
              Allowed addresses:
            </Typography>
            {status.data.allowed_networks.length === 0 ? (
              <Chip size="small" color="warning" label="None: nobody can use the console" />
            ) : (
              status.data.allowed_networks.map((network) => <Chip key={network} size="small" label={network} />)
            )}
          </Stack>
          <Typography variant="body2">
            The list is the server setting <code>HIMS_ADMIN_ALLOWED_NETWORKS</code>
            {status.data.developer_pc ? " (on this computer: this computer only, unless you add more)" : ""}. It is
            changed with the server's settings, not here.
          </Typography>
        </>
      )}
      {refusals.isLoading && <LinearProgress aria-label="Loading refused addresses" />}
      {refusals.error && <ErrorAlert error={refusals.error} />}
      {refusals.data && refusals.data.length === 0 && (
        <Alert severity="info">No address has been refused.</Alert>
      )}
      {refusals.data && refusals.data.length > 0 && (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Refused console addresses">
            <TableHead>
              <TableRow>
                <TableCell>Day</TableCell>
                <TableCell>Address</TableCell>
                <TableCell align="right">Times</TableCell>
                <TableCell>Last page</TableCell>
                <TableCell>Signed in as</TableCell>
                <TableCell>Review</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {refusals.data.map((refusal) => (
                <TableRow key={refusal.id}>
                  <TableCell>{refusal.day}</TableCell>
                  <TableCell>{refusal.ip_address}</TableCell>
                  <TableCell align="right">{refusal.attempts}</TableCell>
                  <TableCell>{refusal.last_path || "—"}</TableCell>
                  <TableCell>
                    {refusal.signed_in_user_name ? (
                      <Chip size="small" color="error" label={refusal.signed_in_user_name} />
                    ) : (
                      "Nobody"
                    )}
                  </TableCell>
                  <TableCell>
                    {refusal.reviewed_at ? (
                      <Typography variant="caption">
                        {refusal.reviewed_by_name ?? "Reviewed"}, {when.format(new Date(refusal.reviewed_at))}
                      </Typography>
                    ) : canManage ? (
                      <ReviewButton refusal={refusal} />
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
