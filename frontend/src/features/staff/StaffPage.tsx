import {
  LinearProgress,
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

import { ErrorAlert } from "../../components/ErrorAlert";
import { useStaff } from "./api";

export function StaffPage() {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const { data, isFetching, error } = useStaff(deferredSearch);

  return (
    <Stack spacing={2}>
      <Typography variant="h5" component="h1">
        Staff
      </Typography>
      <TextField
        label="Search by name or employee number"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        sx={{ maxWidth: 420 }}
      />
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isFetching && <LinearProgress />}
        <Table size="small" aria-label="Staff">
          <TableHead>
            <TableRow>
              <TableCell>Employee no.</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Joined</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((member) => (
              <TableRow key={member.id}>
                <TableCell>{member.employee_number}</TableCell>
                <TableCell>
                  {member.given_name} {member.family_name}
                </TableCell>
                <TableCell>{member.staff_type}</TableCell>
                <TableCell>{member.employment_status}</TableCell>
                <TableCell>{member.joined_on}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>No staff found.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}
