import {
  Box,
  Chip,
  FormControlLabel,
  LinearProgress,
  Link,
  MenuItem,
  Paper,
  Stack,
  Switch,
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
import { Link as RouterLink } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useExpiringCredentials } from "./api";
import { EXPIRY, VERIFICATION } from "./labels";

export function daysText(days: number): string {
  if (days < 0) return `Expired ${-days} day${days === -1 ? "" : "s"} ago`;
  if (days === 0) return "Expires today";
  return `In ${days} day${days === 1 ? "" : "s"}`;
}

/** HIMS-STAFF-006: licences of working staff that are expired or expire soon. */
export function LicenceExpiryPage() {
  const [within, setWithin] = useState(60);
  const [includeExpired, setIncludeExpired] = useState(true);
  const { data, isPending, error } = useExpiringCredentials(within, includeExpired);
  const expired = data?.filter((c) => c.days_left < 0).length ?? 0;
  const soon = (data?.length ?? 0) - expired;

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Licence expiry
        </Typography>
        <Typography variant="body2">
          Licences and registrations of working staff that have expired or expire soon. HR and the
          person are emailed automatically 60, 30 and 7 days before, and again once expired.
        </Typography>
      </Box>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
        <TextField
          select
          size="small"
          label="Expiring within"
          value={within}
          onChange={(e) => setWithin(Number(e.target.value))}
          sx={{ minWidth: 180 }}
        >
          {[30, 60, 90, 180].map((d) => (
            <MenuItem key={d} value={d}>
              {d} days
            </MenuItem>
          ))}
        </TextField>
        <FormControlLabel
          label="Include expired"
          control={<Switch checked={includeExpired} onChange={(e) => setIncludeExpired(e.target.checked)} />}
        />
        {data && (
          <>
            {includeExpired && <Chip color="error" label={`${expired} expired`} />}
            <Chip color="warning" label={`${soon} expiring within ${within} days`} />
          </>
        )}
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Licence expiry">
          <TableHead>
            <TableRow>
              <TableCell>Person</TableCell>
              <TableCell>Licence</TableCell>
              <TableCell>Expires</TableCell>
              <TableCell>Verification</TableCell>
              <TableCell>Last alert</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.map((c) => {
              const e = EXPIRY[c.expiry_state] ?? EXPIRY.no_expiry!;
              const v = VERIFICATION[c.verification_status] ?? VERIFICATION.unverified!;
              return (
                <TableRow key={c.id}>
                  <TableCell>
                    <Link component={RouterLink} to={`/staff/${c.staff_member_id}`}>
                      {c.staff_name}
                    </Link>
                    <Typography variant="caption" component="p">
                      {c.employee_number} · {c.staff_type_label}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    {c.credential_type_label}
                    <Typography variant="caption" component="p">
                      {c.registration_number} · {c.issuing_authority}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    {c.expires_at}
                    <Box>
                      <Chip size="small" color={e.color} label={daysText(c.days_left)} />
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" variant="outlined" color={v.color} label={v.label} />
                  </TableCell>
                  <TableCell>
                    {c.last_alert ? (
                      <>
                        {c.last_alert === "expired" ? "Expired notice" : c.last_alert}
                        <Typography variant="caption" component="p">
                          {c.last_alert_at && new Date(c.last_alert_at).toLocaleDateString()}
                        </Typography>
                      </>
                    ) : (
                      "Not yet"
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>Nothing to renew. All licences are valid for now.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}
