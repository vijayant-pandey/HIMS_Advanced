import {
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
  TablePagination,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import type { EmergencyAccess, EmergencyAccessOutcomeEnum, EmergencyAccessStateEnum } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { PAGE_SIZE, useEmergencyAccessList, useRestrictedOpenings, useReviewEmergencyAccess } from "./api";
import { EMERGENCY_OUTCOME, EMERGENCY_STATE, OPENED_VIA, dayTime } from "./labels";

type View = EmergencyAccessStateEnum | "openings";

/**
 * Emergency access and restricted records, for medical records (HIMS-PAT-006; D14, D23;
 * `patients.records_correct`). Every emergency access is reviewed once it has ended, by someone
 * other than the person who used it; every opening of a restricted record is listed. The review
 * is weekly by habit (D14); the list keeps what is waiting.
 */
export function EmergencyAccessPage() {
  const [view, setView] = useState<View>("to_review");
  return (
    <Stack spacing={2}>
      <div>
        <Typography variant="h5" component="h1">
          Emergency access
        </Typography>
        <Typography variant="body2">
          Doctors and nurses can open a restricted record (VIP, staff) in an emergency, for 4 hours, with a reason.
          Review each one once it has ended: was it appropriate? Someone other than the person who used it must review
          it.
        </Typography>
      </div>
      <Tabs value={view} onChange={(_, value: View) => setView(value)} aria-label="Emergency access lists">
        <Tab value="to_review" label="To review" />
        <Tab value="active" label="Open now" />
        <Tab value="reviewed" label="Reviewed" />
        <Tab value="openings" label="Restricted record openings" />
      </Tabs>
      {view === "openings" ? <RestrictedOpenings /> : <AccessList state={view} />}
    </Stack>
  );
}

function AccessList({ state }: { state: EmergencyAccessStateEnum }) {
  const [page, setPage] = useState(0);
  const [reviewing, setReviewing] = useState<EmergencyAccess | null>(null);
  const { data: user } = useCurrentUser();
  const { data, isFetching, error } = useEmergencyAccessList(state, page + 1);
  return (
    <>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper} variant="outlined">
        {isFetching && <LinearProgress aria-label="Loading emergency access" />}
        <Table size="small" aria-label="Emergency access">
          <TableHead>
            <TableRow>
              <TableCell>Opened</TableCell>
              <TableCell>Patient</TableCell>
              <TableCell>Who</TableCell>
              <TableCell>Reason</TableCell>
              <TableCell>Ended</TableCell>
              <TableCell>Review</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((access) => (
              <TableRow key={access.id}>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{dayTime(access.created_at)}</TableCell>
                <TableCell>
                  <RouterLink to={`/patients/${access.patient}`}>{access.patient_mrn}</RouterLink>
                  <Typography variant="caption" component="div" color="text.secondary">
                    {access.patient_name}
                  </Typography>
                </TableCell>
                <TableCell>{access.user_name || access.user_email}</TableCell>
                <TableCell>{access.reason}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  {access.state === "active" ? `Until ${dayTime(access.expires_at)}` : dayTime(access.ends_at)}
                  {access.ended_at && (
                    <Typography variant="caption" component="div" color="text.secondary">
                      Ended early
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  {access.state === "to_review" && access.user !== user?.id && (
                    <Button size="small" variant="outlined" onClick={() => setReviewing(access)}>
                      Review
                    </Button>
                  )}
                  {access.state === "to_review" && access.user === user?.id && (
                    <Typography variant="caption">Your own: someone else reviews it</Typography>
                  )}
                  {access.state === "active" && (
                    <Chip size="small" color={EMERGENCY_STATE.active.color} label={EMERGENCY_STATE.active.label} />
                  )}
                  {access.state === "reviewed" && (
                    <>
                      <Chip
                        size="small"
                        color={access.outcome === "appropriate" ? "success" : "error"}
                        label={access.outcome_label}
                      />
                      <Typography variant="caption" component="div" color="text.secondary">
                        {access.reviewed_by_name}, {dayTime(access.reviewed_at)}
                        {access.review_note ? `: ${access.review_note}` : ""}
                      </Typography>
                    </>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>Nothing here.</TableCell>
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
      {reviewing && <ReviewDialog access={reviewing} onClose={() => setReviewing(null)} />}
    </>
  );
}

function ReviewDialog({ access, onClose }: { access: EmergencyAccess; onClose: () => void }) {
  const review = useReviewEmergencyAccess(access.id);
  const [outcome, setOutcome] = useState<EmergencyAccessOutcomeEnum>("appropriate");
  const [note, setNote] = useState("");
  const errors = fieldErrors(review.error);
  const needsNote = outcome === "not_appropriate";
  return (
    <FormDialog
      title={`Review emergency access to ${access.patient_mrn}`}
      error={review.error}
      fields={["outcome", "note"]}
      pending={review.isPending}
      submitLabel="Save review"
      submitDisabled={needsNote && note.trim() === ""}
      onClose={onClose}
      onSubmit={() => review.mutate({ outcome, note, version: access.version }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        {access.user_name} opened it on {dayTime(access.created_at)}. Reason: “{access.reason}”
      </Typography>
      <TextField
        select
        label="Outcome"
        value={outcome}
        onChange={(event) => setOutcome(event.target.value as EmergencyAccessOutcomeEnum)}
      >
        {Object.entries(EMERGENCY_OUTCOME).map(([value, label]) => (
          <MenuItem key={value} value={value}>
            {label}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        label="Note"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        multiline
        minRows={2}
        required={needsNote}
        error={!!errors.note}
        helperText={errors.note ?? (needsNote ? "Say what was wrong and what follows." : "Optional.")}
      />
    </FormDialog>
  );
}

const DAYS = [7, 30, 90];

function RestrictedOpenings() {
  const [days, setDays] = useState(7);
  const [page, setPage] = useState(0);
  const { data, isFetching, error } = useRestrictedOpenings(days, page + 1);
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
        <TextField
          select
          size="small"
          label="Period"
          value={days}
          onChange={(event) => {
            setDays(Number(event.target.value));
            setPage(0);
          }}
          sx={{ minWidth: 160 }}
        >
          {DAYS.map((value) => (
            <MenuItem key={value} value={value}>
              Last {value} days
            </MenuItem>
          ))}
        </TextField>
        <Typography variant="body2">Viewing this list is recorded in the audit log.</Typography>
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper} variant="outlined">
        {isFetching && <LinearProgress aria-label="Loading openings" />}
        <Table size="small" aria-label="Restricted record openings">
          <TableHead>
            <TableRow>
              <TableCell>When</TableCell>
              <TableCell>Patient</TableCell>
              <TableCell>Who</TableCell>
              <TableCell>Where</TableCell>
              <TableCell>How</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((event) => (
              <TableRow key={event.id}>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{dayTime(event.occurred_at)}</TableCell>
                <TableCell>
                  <RouterLink to={`/patients/${event.patient}`}>{event.patient_mrn || "—"}</RouterLink>
                </TableCell>
                <TableCell>{event.actor_name ?? "HIMS"}</TableCell>
                <TableCell>{event.facility_name ?? "—"}</TableCell>
                <TableCell>
                  {event.via === "emergency_access" ? (
                    <Chip size="small" color="warning" label={OPENED_VIA.emergency_access} />
                  ) : (
                    OPENED_VIA[event.via] ?? event.via
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>No restricted record was opened in this period.</TableCell>
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
