import {
  Box,
  Button,
  Chip,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
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

import type { CurrentUser, NumberingScheme } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission, hasPermission } from "../auth/grants";
import { useFacilities } from "../facilities/api";
import { useIssuedNumbers, useNumberingSchemes } from "./api";
import { ContinueNumberingDialog } from "./ContinueNumberingDialog";
import { DOCUMENT_TYPES, periodLabel } from "./labels";
import { SchemeDialog } from "./SchemeDialog";

const MANAGE = "numbering.manage";

/** Hint only; the API checks numbering.manage at the scheme's scope. */
function canManage(user: CurrentUser | null | undefined, scheme: NumberingScheme): boolean {
  if (hasOrganizationWidePermission(user, MANAGE)) return true;
  return (
    scheme.facility !== null &&
    !!user?.grants.some((g) => g.permission === MANAGE && g.facility_id === scheme.facility)
  );
}

function IssuedNumbers() {
  const [documentType, setDocumentType] = useState("mrn");
  const { data, isPending, error } = useIssuedNumbers(documentType);
  return (
    <Stack spacing={1}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}>
        <Typography variant="h6" component="h2">
          Issued numbers
        </Typography>
        <TextField
          select
          size="small"
          label="Type"
          value={documentType}
          onChange={(e) => setDocumentType(e.target.value)}
          sx={{ minWidth: 240 }}
        >
          {DOCUMENT_TYPES.map((t) => (
            <MenuItem key={t.value} value={t.value}>
              {t.label}
            </MenuItem>
          ))}
        </TextField>
      </Box>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Issued numbers">
          <TableHead>
            <TableRow>
              <TableCell>Number</TableCell>
              <TableCell>Issued</TableCell>
              <TableCell>By</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((row) => (
              <TableRow key={row.id}>
                <TableCell sx={{ fontFamily: "monospace" }}>{row.value}</TableCell>
                <TableCell>{new Date(row.created_at).toLocaleString()}</TableCell>
                <TableCell>{row.issued_by_name ?? "System"}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={3}>
                  None yet. Numbers appear here as patients, visits, invoices and claims are
                  created (those features come in later phases).
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}

export function NumberingPage() {
  const { data: user } = useCurrentUser();
  const { data: schemes, isPending, error } = useNumberingSchemes();
  const facilities = useFacilities();
  const [editing, setEditing] = useState<NumberingScheme>();
  const [continuing, setContinuing] = useState<NumberingScheme>();
  const [creating, setCreating] = useState(false);

  // Facilities this user may give their own series.
  const manageableFacilities = (facilities.data?.results ?? []).filter(
    (f) =>
      hasOrganizationWidePermission(user, MANAGE) ||
      !!user?.grants.some((g) => g.permission === MANAGE && g.facility_id === f.id),
  );

  return (
    <Stack spacing={3}>
      <Stack spacing={2}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}>
          <Box>
            <Typography variant="h5" component="h1">
              Numbering
            </Typography>
            <Typography variant="body2">
              How patient record (MRN), visit, invoice and claim numbers look. Numbers are never
              reused or handed out twice.
            </Typography>
          </Box>
          {hasPermission(user, MANAGE) && manageableFacilities.length > 0 && (
            <Button variant="contained" onClick={() => setCreating(true)}>
              Facility series
            </Button>
          )}
        </Box>
        {error && <ErrorAlert error={error} />}
        <TableContainer component={Paper}>
          {isPending && <LinearProgress />}
          <Table size="small" aria-label="Numbering schemes">
            <TableHead>
              <TableRow>
                <TableCell>Number type</TableCell>
                <TableCell>Applies to</TableCell>
                <TableCell>Next number</TableCell>
                <TableCell>Restarts</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {schemes?.map((scheme) => (
                <TableRow key={scheme.id}>
                  <TableCell>{scheme.document_type_label}</TableCell>
                  <TableCell>{scheme.facility_name ?? "Whole hospital"}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      variant="outlined"
                      label={scheme.next_number}
                      sx={{ fontFamily: "monospace" }}
                    />
                  </TableCell>
                  <TableCell>
                    {periodLabel(scheme.period, scheme.financial_year_start_month)}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={scheme.is_active ? "Active" : "Inactive"}
                      color={scheme.is_active ? "success" : "default"}
                    />
                  </TableCell>
                  <TableCell align="right">
                    {canManage(user, scheme) && (
                      <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
                        <Button size="small" onClick={() => setEditing(scheme)}>
                          Edit
                        </Button>
                        <Button size="small" onClick={() => setContinuing(scheme)}>
                          Continue from…
                        </Button>
                      </Stack>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {schemes?.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6}>No numbering set up yet.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Stack>

      <IssuedNumbers />

      {editing && (
        <SchemeDialog
          key={editing.id}
          scheme={editing}
          facilities={[]}
          onClose={() => setEditing(undefined)}
        />
      )}
      {creating && (
        <SchemeDialog facilities={manageableFacilities} onClose={() => setCreating(false)} />
      )}
      {continuing && (
        <ContinueNumberingDialog
          key={continuing.id}
          scheme={continuing}
          onClose={() => setContinuing(undefined)}
        />
      )}
    </Stack>
  );
}
