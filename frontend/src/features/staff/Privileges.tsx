import {
  Button,
  Chip,
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

import type { ClinicalPrivilege, StaffMemberDetail, StaffPrivilege } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { localDate } from "../../components/dates";
import { useCatalog, useEndPrivilege, useGrantPrivilege } from "./api";

function GrantDialog({ staff, onClose }: { staff: StaffMemberDetail; onClose: () => void }) {
  const grant = useGrantPrivilege(staff.id, useState(() => crypto.randomUUID())[0]);
  const catalog = useCatalog<ClinicalPrivilege>("clinical-privileges");
  const choices = (catalog.data ?? []).filter((item) => item.is_active);
  const postings = staff.department_assignments.filter((a) => a.is_current);
  const [privilege, setPrivilege] = useState("");
  const [department, setDepartment] = useState("");
  const [validFrom, setValidFrom] = useState(localDate());
  const [validUntil, setValidUntil] = useState("");
  const [note, setNote] = useState("");
  const errors = fieldErrors(grant.error);
  return (
    <FormDialog
      title={`Give a clinical privilege · ${staff.given_name} ${staff.family_name}`}
      error={grant.error}
      fields={["privilege", "department", "valid_from", "valid_until", "note"]}
      submitLabel="Give"
      submitDisabled={!privilege || !validFrom}
      pending={grant.isPending}
      onClose={onClose}
      onSubmit={() =>
        grant.mutate(
          {
            privilege,
            department: department || null,
            valid_from: validFrom,
            valid_until: validUntil || null,
            note: note.trim(),
          },
          { onSuccess: onClose },
        )
      }
    >
      {catalog.error && <ErrorAlert error={catalog.error} />}
      <TextField
        select
        label="Privilege"
        required
        value={privilege}
        onChange={(event) => setPrivilege(event.target.value)}
        error={!!errors.privilege}
        helperText={
          errors.privilege ??
          (catalog.data && choices.length === 0
            ? "The list is empty: add your hospital's privileges under Job titles & catalogs."
            : undefined)
        }
      >
        {choices.map((item) => (
          <MenuItem key={item.id} value={item.id}>
            {item.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Where"
        value={department}
        onChange={(event) => setDepartment(event.target.value)}
        error={!!errors.department}
        helperText={errors.department}
      >
        <MenuItem value="">Wherever this person works</MenuItem>
        {postings.map((posting) => (
          <MenuItem key={posting.id} value={posting.department}>
            Only in {posting.department_name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        type="date"
        label="From"
        required
        value={validFrom}
        onChange={(event) => setValidFrom(event.target.value)}
        error={!!errors.valid_from}
        helperText={errors.valid_from}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <TextField
        type="date"
        label="Review date"
        value={validUntil}
        onChange={(event) => setValidUntil(event.target.value)}
        error={!!errors.valid_until}
        helperText={errors.valid_until ?? "It stops applying after this day. Leave empty for no end date."}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: validFrom } }}
      />
      <TextField
        label="Note (optional)"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        error={!!errors.note}
        helperText={errors.note ?? "e.g. who approved it. No patient details."}
      />
    </FormDialog>
  );
}

function EndDialog({ grant, onClose }: { grant: StaffPrivilege; onClose: () => void }) {
  const end = useEndPrivilege(grant.id);
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`End privilege · ${grant.privilege_name}`}
      error={end.error}
      fields={["reason"]}
      submitLabel="End privilege"
      submitColor="error"
      submitDisabled={!reason.trim()}
      pending={end.isPending}
      onClose={onClose}
      onSubmit={() => end.mutate({ version: grant.version, reason: reason.trim() }, { onSuccess: onClose })}
    >
      <Typography variant="body2">It stays on record as ended. To change it, end it and give it again.</Typography>
      <TextField label="Why?" required value={reason} onChange={(event) => setReason(event.target.value)} />
    </FormDialog>
  );
}

function state(grant: StaffPrivilege): { label: string; color: "success" | "warning" | "default" } {
  if (grant.status === "ended") return { label: "Ended", color: "default" };
  if (grant.is_current) return { label: "Current", color: "success" };
  return { label: grant.valid_until ? "Past its review date" : "Not started yet", color: "warning" };
}

/** What this person may perform, kept by the hospital (HIMS-STAFF-016; spec 4.3). */
export function PrivilegesSection({
  staff,
  canManage,
  isSelf,
}: {
  staff: StaffMemberDetail;
  canManage: boolean;
  isSelf: boolean;
}) {
  const [giving, setGiving] = useState(false);
  const [ending, setEnding] = useState<StaffPrivilege>();
  return (
    <Stack spacing={1}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
          Clinical privileges
        </Typography>
        {canManage && !isSelf && (
          <Button size="small" variant="contained" onClick={() => setGiving(true)}>
            Give a privilege
          </Button>
        )}
      </Stack>
      <Typography variant="body2">
        What the hospital allows this person to perform. Separate from degrees, job title and specialty.
      </Typography>
      <TableContainer component={Paper}>
        <Table size="small" aria-label="Clinical privileges">
          <TableHead>
            <TableRow>
              <TableCell>Privilege</TableCell>
              <TableCell>Where</TableCell>
              <TableCell>From</TableCell>
              <TableCell>Review date</TableCell>
              <TableCell>Status</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {staff.privileges.map((grant) => {
              const shown = state(grant);
              return (
                <TableRow key={grant.id} sx={{ opacity: grant.status === "ended" ? 0.6 : 1 }}>
                  <TableCell>
                    {grant.privilege_name}
                    {grant.note && (
                      <Typography variant="caption" component="p">
                        {grant.note}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>{grant.department_name ?? "Wherever this person works"}</TableCell>
                  <TableCell>{grant.valid_from}</TableCell>
                  <TableCell>{grant.valid_until ?? "—"}</TableCell>
                  <TableCell>
                    <Chip size="small" color={shown.color} label={shown.label} />
                    {grant.granted_by_name && (
                      <Typography variant="caption" component="p">
                        by {grant.granted_by_name}
                      </Typography>
                    )}
                    {grant.end_reason && (
                      <Typography variant="caption" component="p">
                        {grant.end_reason}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell align="right">
                    {canManage && !isSelf && grant.status === "active" && (
                      <Button
                        size="small"
                        aria-label={`End ${grant.privilege_name}`}
                        onClick={() => setEnding(grant)}
                      >
                        End
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {staff.privileges.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>No clinical privileges recorded.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {giving && <GrantDialog staff={staff} onClose={() => setGiving(false)} />}
      {ending && <EndDialog grant={ending} onClose={() => setEnding(undefined)} />}
    </Stack>
  );
}
