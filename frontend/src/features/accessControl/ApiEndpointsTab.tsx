import {
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
import { useMemo, useState } from "react";

import type { ApiEndpoint } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useApiEndpoints } from "./api";

const ACCESS_LABELS: Record<ApiEndpoint["access"], string> = {
  permission: "Needs a permission",
  signed_in: "Anyone signed in",
  public: "Anyone (no sign-in)",
};

function WhoMayCall({ endpoint }: { endpoint: ApiEndpoint }) {
  if (endpoint.access !== "permission") return <>{ACCESS_LABELS[endpoint.access]}</>;
  return (
    <>
      <code>{endpoint.permission}</code>
      {endpoint.scope === "facility" && " (facility or department)"}
      <Typography variant="caption" component="p">
        {endpoint.roles.length ? endpoint.roles.join(", ") : "Custom roles only"}
      </Typography>
    </>
  );
}

/**
 * Every API endpoint, who may call it and what it records (HIMS-DOC-001). Read from the server's
 * code, so it always matches what the server enforces; the full contracts are in the repository.
 */
export function ApiEndpointsTab() {
  const { data, isPending, error } = useApiEndpoints();
  const [area, setArea] = useState("");
  const [access, setAccess] = useState("");
  const [search, setSearch] = useState("");

  const areas = useMemo(() => {
    const seen = new Map<string, string>();
    for (const row of data?.endpoints ?? []) seen.set(row.area, row.area_label);
    return [...seen.entries()];
  }, [data]);

  const term = search.trim().toLowerCase();
  const shown = (data?.endpoints ?? []).filter(
    (row) =>
      (!area || row.area === area) &&
      (!access || row.access === access) &&
      (!term ||
        `${row.method} ${row.path} ${row.summary} ${row.permission}`.toLowerCase().includes(term)),
  );
  const summary = data?.summary;

  return (
    <Stack spacing={1}>
      {summary && (
        <Typography variant="body2">
          {summary.total} endpoints: {summary.permission} need a permission, {summary.signed_in}{" "}
          need any sign-in, {summary.public} are open without sign-in.{" "}
          {summary.confirm_identity} need a recent &ldquo;confirm it&rsquo;s you&rdquo;;{" "}
          {summary.audited_writes} of {summary.writes} changes record an audit event.
        </Typography>
      )}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <TextField
          select
          size="small"
          label="Area"
          value={area}
          onChange={(e) => setArea(e.target.value)}
          sx={{ minWidth: 260 }}
        >
          <MenuItem value="">All areas</MenuItem>
          {areas.map(([key, label]) => (
            <MenuItem key={key} value={key}>
              {label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Access"
          value={access}
          onChange={(e) => setAccess(e.target.value)}
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">Any</MenuItem>
          {Object.entries(ACCESS_LABELS).map(([key, label]) => (
            <MenuItem key={key} value={key}>
              {label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="Search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Path, permission or words"
        />
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="API endpoints">
          <TableHead>
            <TableRow>
              <TableCell>Method and path</TableCell>
              <TableCell>What it does</TableCell>
              <TableCell>Who may call it</TableCell>
              <TableCell>Records</TableCell>
              <TableCell>Requirement</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {shown.map((row) => (
              <TableRow key={`${row.method} ${row.path}`}>
                <TableCell>
                  <code>
                    {row.method} {row.path}
                  </code>
                </TableCell>
                <TableCell>{row.summary}</TableCell>
                <TableCell>
                  <WhoMayCall endpoint={row} />
                  {row.confirm_identity && (
                    <Chip size="small" label="Confirm it's you" sx={{ mt: 0.5 }} />
                  )}
                </TableCell>
                <TableCell>{row.audit_actions.join(", ") || "—"}</TableCell>
                <TableCell>{row.requirements.join(", ") || "—"}</TableCell>
              </TableRow>
            ))}
            {data && shown.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>No endpoints match.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}
