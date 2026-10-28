import {
  Box,
  Button,
  Chip,
  LinearProgress,
  Link,
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
import { Link as RouterLink, useSearchParams } from "react-router-dom";

import type { Department } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasPermission, hasPermissionAt } from "../auth/grants";
import { useDepartmentList, useFacilities } from "./api";
import { AddDepartmentDialog, EditDepartmentDialog } from "./SetupDialogs";

export function DepartmentsPage() {
  const { data: user } = useCurrentUser();
  const facilities = useFacilities();
  const [params, setParams] = useSearchParams();
  const facilityId = params.get("facility") ?? "";
  const [status, setStatus] = useState("active");
  const { data, isPending, error } = useDepartmentList(facilityId || undefined, status || undefined);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Department>();
  // Hints only: the API checks departments.manage at the department's facility.
  const manageable = (facilities.data?.results ?? []).filter(
    (f) => f.status === "active" && hasPermissionAt(user, "departments.manage", f.id),
  );
  const canSeeStaff = hasPermission(user, "staff.view");

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}>
        <Box>
          <Typography variant="h5" component="h1">
            Departments
          </Typography>
          <Typography variant="body2">
            Clinical and support departments of each facility. Staff are posted to departments, and
            wards can belong to one.
          </Typography>
        </Box>
        {manageable.length > 0 && (
          <Button variant="contained" onClick={() => setAdding(true)}>
            Add department
          </Button>
        )}
      </Box>
      <Stack direction="row" spacing={2}>
        <TextField
          select
          size="small"
          label="Facility"
          value={facilityId}
          onChange={(e) => setParams(e.target.value ? { facility: e.target.value } : {})}
          sx={{ minWidth: 240 }}
        >
          <MenuItem value="">All facilities</MenuItem>
          {facilities.data?.results.map((f) => (
            <MenuItem key={f.id} value={f.id}>
              {f.name}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="active">Active</MenuItem>
          <MenuItem value="inactive">Inactive</MenuItem>
          <MenuItem value="">All</MenuItem>
        </TextField>
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Departments">
          <TableHead>
            <TableRow>
              <TableCell>Department</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Facility</TableCell>
              <TableCell align="right">Staff</TableCell>
              <TableCell align="right">Wards</TableCell>
              <TableCell>Status</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((d) => (
              <TableRow key={d.id} sx={{ opacity: d.status === "active" ? 1 : 0.6 }}>
                <TableCell>
                  {d.name}
                  <Typography variant="caption" component="p">
                    {d.code}
                  </Typography>
                </TableCell>
                <TableCell>{d.department_type_label}</TableCell>
                <TableCell>{d.facility_name}</TableCell>
                <TableCell align="right">
                  {canSeeStaff && d.current_staff > 0 ? (
                    <Link component={RouterLink} to={`/staff?department=${d.id}`}>
                      {d.current_staff}
                    </Link>
                  ) : (
                    d.current_staff
                  )}
                </TableCell>
                <TableCell align="right">{d.active_wards}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    color={d.status === "active" ? "success" : "default"}
                    label={d.status === "active" ? "Active" : "Inactive"}
                  />
                </TableCell>
                <TableCell align="right">
                  {hasPermissionAt(user, "departments.manage", d.facility) && (
                    <Button size="small" onClick={() => setEditing(d)} aria-label={`Edit ${d.name}`}>
                      Edit
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>
                  {status === "inactive" ? "No inactive departments." : "No departments yet."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {adding && (
        <AddDepartmentDialog
          facilities={manageable}
          initialFacility={manageable.some((f) => f.id === facilityId) ? facilityId : undefined}
          onClose={() => setAdding(false)}
        />
      )}
      {editing && (
        <EditDepartmentDialog
          key={editing.id}
          department={editing}
          onClose={() => setEditing(undefined)}
        />
      )}
    </Stack>
  );
}
