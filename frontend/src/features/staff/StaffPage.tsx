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

import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { useStaff } from "./api";
import { EMPLOYMENT_STATUSES, STATUS_COLOR, options } from "./labels";
import { AddStaffDialog } from "./StaffDialogs";

export function StaffPage() {
  const navigate = useNavigate();
  const { data: user } = useCurrentUser();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const { data, isFetching, error } = useStaff(deferredSearch, status);
  const [adding, setAdding] = useState(false);
  // Hint only: the API checks staff.manage (staff records are hospital-wide).
  const canAdd = hasOrganizationWidePermission(user, "staff.manage");

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}>
        <Typography variant="h5" component="h1">
          Staff
        </Typography>
        {canAdd && (
          <Button variant="contained" onClick={() => setAdding(true)}>
            Add staff member
          </Button>
        )}
      </Box>
      <Stack direction="row" spacing={2}>
        <TextField
          label="Search by name or employee number"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          sx={{ maxWidth: 420, flex: 1 }}
        />
        <TextField
          select
          label="Status"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">All</MenuItem>
          {options(EMPLOYMENT_STATUSES).map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
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
              <TableRow
                key={member.id}
                hover
                onClick={() => navigate(`/staff/${member.id}`)}
                sx={{ cursor: "pointer" }}
              >
                <TableCell>{member.employee_number}</TableCell>
                <TableCell>
                  <Typography
                    component="a"
                    href={`/staff/${member.id}`}
                    variant="body2"
                    onClick={(event) => {
                      event.preventDefault();
                      navigate(`/staff/${member.id}`);
                    }}
                    sx={{ color: "primary.main", textDecoration: "none", fontWeight: 600 }}
                  >
                    {member.given_name} {member.family_name}
                  </Typography>
                </TableCell>
                <TableCell>{member.staff_type_label}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    color={STATUS_COLOR[member.employment_status]}
                    label={member.employment_status_label}
                  />
                </TableCell>
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
      {adding && <AddStaffDialog onClose={() => setAdding(false)} />}
    </Stack>
  );
}
