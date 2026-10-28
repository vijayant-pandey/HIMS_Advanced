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
import { useDeferredValue, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { Account } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { AddAccountDialog } from "./AccountDialogs";
import { useAccounts } from "./api";

export function accountState(a: Account): { label: string; color: "success" | "warning" | "default" | "info" } {
  if (!a.is_active) return { label: "Switched off", color: "default" };
  if (a.activated) return { label: "Active", color: "success" };
  if (a.invitation_expires_at) return { label: "Invitation sent", color: "info" };
  return { label: "Not activated", color: "warning" };
}

export function AccountsPage() {
  const navigate = useNavigate();
  const { data: user } = useCurrentUser();
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const deferred = useDeferredValue(search.trim());
  const { data, isFetching, error } = useAccounts({ search: deferred, kind, status });
  const [adding, setAdding] = useState(false);

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}>
        <Box>
          <Typography variant="h5" component="h1">
            Accounts
          </Typography>
          <Typography variant="body2">
            Everyone who can sign in, including people who are not on the staff list (e.g. the
            first administrator, auditors, IT support).
          </Typography>
        </Box>
        {hasOrganizationWidePermission(user, "accounts.manage") && (
          <Button variant="contained" onClick={() => setAdding(true)}>
            Add account
          </Button>
        )}
      </Box>
      <Stack direction="row" spacing={2}>
        <TextField
          label="Search by name or email"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ maxWidth: 360, flex: 1 }}
        />
        <TextField select label="Who" value={kind} onChange={(e) => setKind(e.target.value)} sx={{ minWidth: 180 }}>
          <MenuItem value="">Everyone</MenuItem>
          <MenuItem value="not_staff">Not staff</MenuItem>
          <MenuItem value="staff">Staff</MenuItem>
        </TextField>
        <TextField select label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 160 }}>
          <MenuItem value="">All</MenuItem>
          <MenuItem value="active">On</MenuItem>
          <MenuItem value="inactive">Switched off</MenuItem>
        </TextField>
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isFetching && <LinearProgress />}
        <Table size="small" aria-label="Accounts">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Access</TableCell>
              <TableCell>Two-factor</TableCell>
              <TableCell>Last sign-in</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((a) => {
              const state = accountState(a);
              return (
                <TableRow key={a.id} hover onClick={() => navigate(`/accounts/${a.id}`)} sx={{ cursor: "pointer" }}>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {a.display_name}
                    </Typography>
                    <Typography variant="caption" component="p">
                      {a.email}
                    </Typography>
                  </TableCell>
                  <TableCell>{a.staff_member_id ? "Staff" : "Not staff"}</TableCell>
                  <TableCell>{a.roles.length ? a.roles.join(", ") : "No access"}</TableCell>
                  <TableCell>{a.two_factor_enabled ? "On" : "Off"}</TableCell>
                  <TableCell>{a.last_login ? new Date(a.last_login).toLocaleString() : "Never"}</TableCell>
                  <TableCell>
                    <Chip size="small" color={state.color} label={state.label} />
                  </TableCell>
                </TableRow>
              );
            })}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>No accounts found.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {adding && <AddAccountDialog onClose={() => setAdding(false)} />}
    </Stack>
  );
}
