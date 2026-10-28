import {
  Box,
  Button,
  Chip,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { Role, RoleAssignment } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission, hasPermission } from "../auth/grants";
import { RevokeDialog, RoleDialog } from "./AccessDialogs";
import { usePermissions, useRoleAssignments, useRoles } from "./api";
import { formatDate, scopeLabel } from "./UserAccessPanel";

function RolesTab() {
  const { data: user } = useCurrentUser();
  const { data, isPending, error } = useRoles();
  const permissions = usePermissions();
  const [open, setOpen] = useState<string>();
  const [editing, setEditing] = useState<Role | "new">();
  const canManage = hasOrganizationWidePermission(user, "access.roles.manage");
  const describe = (codename: string) =>
    permissions.data?.find((p) => p.codename === codename)?.description ?? codename;

  return (
    <Stack spacing={1}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="body2">
          System roles come with HIMS and stay up to date automatically. Custom roles are your own
          combinations of permissions.
        </Typography>
        {canManage && (
          <Button variant="contained" size="small" onClick={() => setEditing("new")}>
            New custom role
          </Button>
        )}
      </Box>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Roles">
          <TableHead>
            <TableRow>
              <TableCell>Role</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>People</TableCell>
              <TableCell>Permissions</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((role) => (
              <TableRow key={role.id} sx={{ verticalAlign: "top" }}>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {role.name}
                  </Typography>
                  <Typography variant="caption" component="p">
                    {role.description}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    variant="outlined"
                    label={role.is_system ? "System" : "Custom"}
                  />
                </TableCell>
                <TableCell>{role.active_assignments}</TableCell>
                <TableCell>
                  <Button size="small" onClick={() => setOpen(open === role.id ? undefined : role.id)}>
                    {open === role.id ? "Hide" : `Show ${role.permissions.length}`}
                  </Button>
                  {open === role.id && (
                    <Box component="ul" sx={{ m: 0, pl: 2 }}>
                      {role.permissions.map((codename) => (
                        <Typography key={codename} component="li" variant="caption">
                          {describe(codename)}
                        </Typography>
                      ))}
                    </Box>
                  )}
                </TableCell>
                <TableCell align="right">
                  {canManage && !role.is_system && (
                    <Button size="small" onClick={() => setEditing(role)} aria-label={`Edit ${role.name}`}>
                      Edit
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {editing && (
        <RoleDialog
          key={editing === "new" ? "new" : editing.id}
          role={editing === "new" ? undefined : editing}
          onClose={() => setEditing(undefined)}
        />
      )}
    </Stack>
  );
}

function WhoHasAccessTab() {
  const { data: user } = useCurrentUser();
  const roles = useRoles();
  const [role, setRole] = useState("");
  const { data, isPending, error } = useRoleAssignments({ role: role || undefined, active: true });
  const [revoking, setRevoking] = useState<RoleAssignment>();
  const canManage = hasPermission(user, "access.assignments.manage");

  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
        <TextField
          select
          size="small"
          label="Role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          sx={{ minWidth: 260 }}
        >
          <MenuItem value="">All roles</MenuItem>
          {(roles.data?.results ?? []).map((r) => (
            <MenuItem key={r.id} value={r.id}>
              {r.name}
            </MenuItem>
          ))}
        </TextField>
        <Typography variant="body2">
          Current access only. To give access, open the person on the Staff page.
        </Typography>
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Who has access">
          <TableHead>
            <TableRow>
              <TableCell>Person</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Where</TableCell>
              <TableCell>Given by</TableCell>
              <TableCell>Until</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((a) => (
              <TableRow key={a.id}>
                <TableCell>
                  {a.user_display_name}
                  <Typography variant="caption" component="p">
                    {a.user_email}
                  </Typography>
                </TableCell>
                <TableCell>{a.role_name}</TableCell>
                <TableCell>{scopeLabel(a)}</TableCell>
                <TableCell>
                  {a.granted_by_name ?? "System"}
                  <Typography variant="caption" component="p">
                    {formatDate(a.created_at)}
                  </Typography>
                </TableCell>
                <TableCell>{formatDate(a.valid_until)}</TableCell>
                <TableCell align="right">
                  {canManage && a.user !== user?.id && (
                    <Button
                      size="small"
                      color="error"
                      onClick={() => setRevoking(a)}
                      aria-label={`Remove ${a.role_name} from ${a.user_display_name}`}
                    >
                      Remove
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>Nobody has this role.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {revoking && <RevokeDialog assignment={revoking} onClose={() => setRevoking(undefined)} />}
    </Stack>
  );
}

export function AccessPage() {
  const [tab, setTab] = useState(0);
  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Roles and access
        </Typography>
        <Typography variant="body2">
          What each role can do, and who has access where. Every change is recorded in the audit
          log.
        </Typography>
      </Box>
      <Tabs value={tab} onChange={(_, value: number) => setTab(value)} aria-label="Access sections">
        <Tab label="Who has access" />
        <Tab label="Roles" />
      </Tabs>
      {tab === 0 ? <WhoHasAccessTab /> : <RolesTab />}
    </Stack>
  );
}
