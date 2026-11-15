import {
  Box,
  Button,
  Chip,
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

import { localDate } from "../../components/dates";
import { ErrorAlert } from "../../components/ErrorAlert";
import { addDays, formatDay, mondayOf } from "../rosters/labels";
import { useMyOpdWeek } from "./api";
import { SESSION_STATUS, offText } from "./labels";

/** Your own OPD sessions over a week, in every department (HIMS-OPD-001), on My schedule.
 * Shown when you hold sessions this week; its buttons show the other weeks. */
export function MyOpdSessions() {
  const [start, setStart] = useState(() => mondayOf(localDate()));
  const { data, error } = useMyOpdWeek(start);
  if (error) return <ErrorAlert error={error} />;
  if (!data?.has_staff_record) return null;
  const days = data.days.filter((day) => day.sessions.length > 0);
  const thisWeek = start === mondayOf(localDate());
  if (days.length === 0 && thisWeek) return null; // not a doctor holding OPD sessions
  return (
    <>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
        <Typography variant="h6" component="h2" sx={{ flexGrow: 1 }}>
          My OPD sessions, week of {formatDay(start)}
        </Typography>
        <Button onClick={() => setStart(addDays(start, -7))}>Previous week</Button>
        <Button onClick={() => setStart(mondayOf(localDate()))}>This week</Button>
        <Button onClick={() => setStart(addDays(start, 7))}>Next week</Button>
      </Stack>
      <TableContainer component={Paper}>
        <Table size="small" aria-label="My OPD sessions">
          <TableHead>
            <TableRow>
              <TableCell>Day</TableCell>
              <TableCell>Hours</TableCell>
              <TableCell>Department</TableCell>
              <TableCell>Slots</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {days.flatMap((day) =>
              day.sessions.map((session) => (
                <TableRow key={`${session.source}-${session.schedule_id ?? session.exception_id}-${day.day}`}>
                  <TableCell>{formatDay(day.day)}</TableCell>
                  <TableCell>
                    {session.hours}
                    {session.source === "extra" && <Chip size="small" label="Extra" sx={{ ml: 1 }} />}
                  </TableCell>
                  <TableCell>{session.department_name}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      color={SESSION_STATUS[session.status].color}
                      label={
                        session.status === "off"
                          ? SESSION_STATUS.off.label
                          : `${session.open_slots} × ${session.slot_minutes} min`
                      }
                    />
                    {session.off.length > 0 && (
                      <Box component="span" sx={{ ml: 1 }}>
                        <Typography variant="caption">{offText(session)}</Typography>
                      </Box>
                    )}
                  </TableCell>
                </TableRow>
              )),
            )}
            {days.length === 0 && (
              <TableRow>
                <TableCell colSpan={4}>No OPD sessions this week.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}
