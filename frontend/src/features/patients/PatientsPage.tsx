import {
  Alert,
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
import { MATCHED_ON, SEX, SEX_SHORT, dayTime } from "./labels";

const NO_SEARCH = { search: "", sex: "", age: "" };

/**
 * Patients (HIMS-PAT-001, HIMS-PAT-002; spec 4.5): one search box for the MRN, a phone number, an
 * ID number or a name (similar spelling, any order, earlier names too), with sex and age to
 * narrow it. Without a search: newest registrations first. Results show only the minimum (name,
 * MRN, age and sex, the phone's last digits); every search and every record opened is audited.
 */
export function PatientsPage() {
  const { data: user } = useCurrentUser();
  const [facility, setFacility] = useState("");
  const [draft, setDraft] = useState(NO_SEARCH);
  const [asked, setAsked] = useState(NO_SEARCH);
  const [page, setPage] = useState(0);
  const { data, isFetching, error } = usePatients({ facility, ...asked }, page + 1);
  const facilities = useFacilities().data?.results ?? [];
  const canRegister = hasPermission(user, "patients.register");
  const searching = asked.search !== "";
  const shown = data?.results.length ?? 0;
  const tooMany = searching && !!data && data.count > shown;

  function clear() {
    setDraft(NO_SEARCH);
    setAsked(NO_SEARCH);
    setPage(0);
  }

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
        <Box>
          <Typography variant="h5" component="h1">
            Patients
          </Typography>
          <Typography variant="body2">
            Search first, so nobody is registered twice. Type the MRN, a phone number, an ID number or the name (any
            spelling, any order; add the age, e.g. “sunita 45”). Every search and every record you open is recorded
            in the audit log.
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
        role="search"
        aria-label="Patient search"
        onSubmit={(event) => {
          event.preventDefault();
          setAsked({ ...draft, search: draft.search.trim() });
          setPage(0);
        }}
      >
        <TextField
          size="small"
          label="Search"
          value={draft.search}
          onChange={(event) => setDraft({ ...draft, search: event.target.value })}
          helperText="MRN, phone, ID number or name (+ age)"
          sx={{ minWidth: 300 }}
        />
        <TextField
          select
          size="small"
          label="Sex"
          value={draft.sex}
          onChange={(event) => setDraft({ ...draft, sex: event.target.value })}
          sx={{ minWidth: 120 }}
        >
          <MenuItem value="">Any</MenuItem>
          {Object.entries(SEX).map(([value, label]) => (
            <MenuItem key={value} value={value}>
              {label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="Age (years)"
          type="number"
          value={draft.age}
          onChange={(event) => setDraft({ ...draft, age: event.target.value })}
          helperText="Give or take 1 year"
          slotProps={{ htmlInput: { min: 0, max: 130 } }}
          sx={{ width: 140 }}
        />
        <Button type="submit" variant="outlined" disabled={draft.search.trim() === ""}>
          Search
        </Button>
        {(searching || draft.search) && <Button onClick={clear}>Clear</Button>}
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
      {tooMany && (
        <Alert severity="info">
          {data.count} patients match; the best {shown} are shown. Add the age, the sex or more of the name.
        </Alert>
      )}
      <Typography variant="subtitle2" component="h2">
        {searching ? "Search results" : "Newest registrations"}
      </Typography>
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
              {searching ? <TableCell>Found by</TableCell> : <TableCell>Registered</TableCell>}
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
                  {patient.status === "merged" && <Chip size="small" label="Merged" sx={{ ml: 1 }} />}
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  {patient.birth_date_estimated ? "~" : ""}
                  {patient.age} {SEX_SHORT[patient.sex]}
                </TableCell>
                <TableCell>{patient.phone_last4 || "—"}</TableCell>
                <TableCell>{patient.registered_facility_name}</TableCell>
                {searching ? (
                  <TableCell>{MATCHED_ON[patient.matched_on ?? ""] ?? "—"}</TableCell>
                ) : (
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{dayTime(patient.created_at)}</TableCell>
                )}
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  {searching ? (
                    <>
                      No patient found. Check the spelling, or search by MRN, phone or ID number.
                      {canRegister && (
                        <>
                          {" "}
                          Still not found?{" "}
                          <RouterLink to="/patients/register">Register new patient</RouterLink>.
                        </>
                      )}
                    </>
                  ) : (
                    "No patients registered yet."
                  )}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {!searching && data && data.count > PAGE_SIZE && (
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
