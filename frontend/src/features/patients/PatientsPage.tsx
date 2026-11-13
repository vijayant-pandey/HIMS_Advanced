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
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasPermission } from "../auth/grants";
import { useFacilities } from "../facilities/api";
import { PAGE_SIZE, usePatients } from "./api";
import { SEX_SHORT, dayTime } from "./labels";

/**
 * Patients (HIMS-PAT-001; spec 4.5): newest registrations first, or one patient by MRN. The list
 * shows only the minimum (name, MRN, age and sex, the phone's last digits). Search by phone, ID
 * number and similar name comes with HIMS-PAT-002.
 */
export function PatientsPage() {
  const { data: user } = useCurrentUser();
  const [facility, setFacility] = useState("");
  const [mrnInput, setMrnInput] = useState("");
  const [mrn, setMrn] = useState("");
  const [page, setPage] = useState(0);
  const { data, isFetching, error } = usePatients({ facility, mrn }, page + 1);
  const facilities = useFacilities().data?.results ?? [];
  const canRegister = hasPermission(user, "patients.register");

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
        <Box>
          <Typography variant="h5" component="h1">
            Patients
          </Typography>
          <Typography variant="body2">
            Newest registrations first. Look a patient up by MRN, or open one for their details. Every record you
            open is recorded in the audit log.
          </Typography>
        </Box>
        {canRegister && (
          <Button variant="contained" component={RouterLink} to="/patients/register">
            Register new patient
          </Button>
        )}
      </Box>
      <Stack
        direction="row"
        spacing={2}
        useFlexGap
        sx={{ flexWrap: "wrap", alignItems: "flex-start" }}
        component="form"
        onSubmit={(event) => {
          event.preventDefault();
          setMrn(mrnInput.trim());
          setPage(0);
        }}
      >
        <TextField
          size="small"
          label="MRN"
          value={mrnInput}
          onChange={(event) => setMrnInput(event.target.value)}
          helperText="The whole number, e.g. MRN-00000123"
        />
        <Button type="submit" variant="outlined">
          Look up
        </Button>
        {mrn && (
          <Button
            onClick={() => {
              setMrn("");
              setMrnInput("");
            }}
          >
            Show all
          </Button>
        )}
        {facilities.length > 1 && (
          <TextField
            select
            size="small"
            label="Registered at"
            value={facility}
            onChange={(event) => {
              setFacility(event.target.value);
              setPage(0);
            }}
            sx={{ minWidth: 200 }}
          >
            <MenuItem value="">Any facility</MenuItem>
            {facilities.map((item) => (
              <MenuItem key={item.id} value={item.id}>
                {item.name}
              </MenuItem>
            ))}
          </TextField>
        )}
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isFetching && <LinearProgress aria-label="Loading patients" />}
        <Table size="small" aria-label="Patients">
          <TableHead>
            <TableRow>
              <TableCell>MRN</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Age / sex</TableCell>
              <TableCell>Phone</TableCell>
              <TableCell>Registered at</TableCell>
              <TableCell>Registered</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((patient) => (
              <TableRow key={patient.id} hover>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  <Button
                    component={RouterLink}
                    to={`/patients/${patient.id}`}
                    variant="text"
                    size="small"
                    sx={{ p: 0, minWidth: 0 }}
                  >
                    {patient.mrn}
                  </Button>
                </TableCell>
                <TableCell>
                  {patient.name}
                  {patient.is_unknown && <Chip size="small" color="warning" label="Unknown patient" sx={{ ml: 1 }} />}
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  {patient.birth_date_estimated ? "~" : ""}
                  {patient.age} {SEX_SHORT[patient.sex]}
                </TableCell>
                <TableCell>{patient.phone_last4 || "—"}</TableCell>
                <TableCell>{patient.registered_facility_name}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{dayTime(patient.created_at)}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  {mrn ? `No patient has the MRN ${mrn}.` : "No patients registered yet."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {data && data.count > PAGE_SIZE && (
          <TablePagination
            component="div"
            count={data.count}
            page={page}
            rowsPerPage={PAGE_SIZE}
            rowsPerPageOptions={[PAGE_SIZE]}
            onPageChange={(_, value: number) => setPage(value)}
          />
        )}
      </TableContainer>
    </Stack>
  );
}
