import {
  Box,
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
import { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { useFacilities } from "./api";
import { CreateFacilityDialog } from "./CreateFacilityDialog";

export function FacilitiesPage() {
  const { data: user } = useCurrentUser();
  const { data, isPending, error } = useFacilities();
  const [creating, setCreating] = useState(false);

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
              <TableCell>City</TableCell>
              <TableCell>Time zone</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((facility) => (
              <TableRow key={facility.id}>
                <TableCell>{facility.code}</TableCell>
                <TableCell>{facility.name}</TableCell>
                <TableCell>{facility.city}</TableCell>
                <TableCell>{facility.timezone}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={facility.status}
                    color={facility.status === "active" ? "success" : "default"}
                  />
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>No facilities yet.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <CreateFacilityDialog open={creating} onClose={() => setCreating(false)} />
    </Stack>
  );
}
