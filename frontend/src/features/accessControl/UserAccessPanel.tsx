import {
  Box,
  Button,
  Chip,
  FormControlLabel,
  LinearProgress,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { RoleAssignment } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasPermission } from "../auth/grants";
import { GrantRoleDialog, RevokeDialog } from "./AccessDialogs";
import { useRoleAssignments } from "./api";

export function scopeLabel(a: RoleAssignment): string {
  if (a.department_name) return `${a.department_name} (${a.facility_name})`;
  if (a.facility_name) return a.facility_name;
  return "Whole hospital";
}

export function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString() : "—";
}

/** One person's access: current roles, history, and give/remove access. */
export function UserAccessPanel({ userId, personName }: { userId: string; personName: string }) {
  const { data: me } = useCurrentUser();
  const [showHistory, setShowHistory] = useState(false);
  const { data, isPending, error } = useRoleAssignments({ user: userId, active: !showHistory });
  const [granting, setGranting] = useState(false);
  const [revoking, setRevoking] = useState<RoleAssignment>();
  // Hint only: the server checks the grant and refuses privilege escalation.
  const canManage = hasPermission(me, "access.assignments.manage");
  const isSelf = me?.id === userId;

  return (
    <Stack spacing={1}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 2 }}>
        <FormControlLabel
          label="Show removed and expired"
          control={<Switch checked={showHistory} onChange={(e) => setShowHistory(e.target.checked)} />}
        />
        {canManage && !isSelf && (
          <Button variant="contained" size="small" onClick={() => setGranting(true)}>
            Give access
          </Button>
        )}
      </Box>
      {isSelf && (
        <Typography variant="body2">You cannot change your own access; ask another administrator.</Typography>
      )}
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Access">
          <TableHead>
            <TableRow>
              <TableCell>Role</TableCell>
              <TableCell>Where</TableCell>
              <TableCell>Given by</TableCell>
              <TableCell>Until</TableCell>
              <TableCell>Status</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((a) => (
              <TableRow key={a.id}>
                <TableCell>
                  {a.role_name}
                  {a.covering_for_name && (
                    <Chip size="small" variant="outlined" label={`Cover for ${a.covering_for_name}`} sx={{ ml: 1 }} />
                  )}
                  {a.reason && (
                    <Typography variant="caption" component="p">
                      {a.reason}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>{scopeLabel(a)}</TableCell>
                <TableCell>
                  {a.granted_by_name ?? "System"}
                  <Typography variant="caption" component="p">
                    {formatDate(a.created_at)}
                  </Typography>
                </TableCell>
                <TableCell>{formatDate(a.valid_until)}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    color={a.is_active ? "success" : "default"}
                    label={a.revoked_at ? "Removed" : a.is_active ? "Active" : "Expired"}
                    title={a.revocation_reason || undefined}
                  />
                </TableCell>
                <TableCell align="right">
                  {canManage && !isSelf && a.is_active && (
                    <Button
                      size="small"
                      color="error"
                      onClick={() => setRevoking(a)}
                      aria-label={`Remove ${a.role_name}`}
                    >
                      Remove
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  {showHistory ? "No access records." : "No access yet."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {granting && (
        <GrantRoleDialog userId={userId} personName={personName} onClose={() => setGranting(false)} />
      )}
      {revoking && <RevokeDialog assignment={revoking} onClose={() => setRevoking(undefined)} />}
    </Stack>
  );
}
