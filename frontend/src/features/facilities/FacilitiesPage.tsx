import {
  Box,
  Button,
  Chip,
  LinearProgress,
  Link,
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
import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import type { Facility } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission, hasPermission, hasPermissionAt } from "../auth/grants";
import { useFacilities } from "./api";
import { CreateFacilityDialog } from "./CreateFacilityDialog";
import { EditFacilityDialog } from "./SetupDialogs";

export function FacilitiesPage() {
  const { data: user } = useCurrentUser();
  const { data, isPending, error } = useFacilities();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Facility>();
  const canSeeDepartments = hasPermission(user, "departments.view");

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="h5" component="h1">
          Facilities
        </Typography>
        {hasOrganizationWidePermission(user, "facilities.manage") && (
          <Button variant="contained" onClick={() => setCreating(true)}>
            New facility
          </Button>
        )}
      </Box>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Facilities">
          <TableHead>
            <TableRow>
              <TableCell>Code</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>City</TableCell>
              <TableCell>Time zone</TableCell>
              <TableCell align="right">Departments</TableCell>
              <TableCell>Status</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((facility) => (
              <TableRow key={facility.id}>
                <TableCell>{facility.code}</TableCell>
                <TableCell>{facility.name}</TableCell>
                <TableCell>{facility.facility_type_label}</TableCell>
                <TableCell>{facility.city}</TableCell>
                <TableCell>{facility.timezone}</TableCell>
                <TableCell align="right">
                  {canSeeDepartments ? (
                    <Link component={RouterLink} to={`/departments?facility=${facility.id}`}>
                      {facility.active_departments}
                    </Link>
                  ) : (
                    facility.active_departments
                  )}
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={facility.status === "active" ? "Active" : "Inactive"}
                    color={facility.status === "active" ? "success" : "default"}
                  />
                </TableCell>
                <TableCell align="right">
                  {hasPermissionAt(user, "facilities.manage", facility.id) && (
                    <Button
                      size="small"
                      onClick={() => setEditing(facility)}
                      aria-label={`Edit ${facility.name}`}
                    >
                      Edit
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={8}>No facilities yet.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <CreateFacilityDialog open={creating} onClose={() => setCreating(false)} />
      {editing && (
        <EditFacilityDialog key={editing.id} facility={editing} onClose={() => setEditing(undefined)} />
      )}
    </Stack>
  );
}
