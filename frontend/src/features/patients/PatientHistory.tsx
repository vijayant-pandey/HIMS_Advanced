import {
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from "@mui/material";
import { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { PAGE_SIZE, usePatientHistory } from "./api";
import { dayTime } from "./labels";

/**
 * The chart's History tab (HIMS-PAT-005), for medical records (`patients.history`): who opened
 * the record and who changed what, and when, newest first. Corrections name the fields, never
 * their values. Viewing this list is itself in the audit log.
 */
export function PatientHistory({ patientId }: { patientId: string }) {
  const [page, setPage] = useState(0);
  const { data, isFetching, error } = usePatientHistory(patientId, page + 1);

  return (
    <Stack spacing={1}>
      <Typography variant="body2">
        Everyone who opened this record or changed it. The old and new values stay in the audit log. Viewing this list is
        recorded too.
      </Typography>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper} variant="outlined">
        {isFetching && <LinearProgress aria-label="Loading history" />}
        <Table size="small" aria-label="Record history">
          <TableHead>
            <TableRow>
              <TableCell>When</TableCell>
              <TableCell>Who</TableCell>
              <TableCell>Where</TableCell>
              <TableCell>What</TableCell>
              <TableCell>Fields changed</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((event) => (
              <TableRow key={event.id}>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{dayTime(event.occurred_at)}</TableCell>
                <TableCell>{event.actor_name ?? "HIMS"}</TableCell>
                <TableCell>{event.facility_name ?? "—"}</TableCell>
                <TableCell>
                  {event.action_label}
                  {event.outcome !== "success" ? ` (${event.outcome})` : ""}
                  {event.reason && (
                    <Typography variant="caption" component="div" color="text.secondary">
                      Reason: {event.reason}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>{event.changed.join(", ") || "—"}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>Nothing recorded yet.</TableCell>
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
