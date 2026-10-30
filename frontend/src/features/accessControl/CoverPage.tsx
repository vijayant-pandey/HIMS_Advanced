import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  FormGroup,
  LinearProgress,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { AccessDelegation, AccessDelegationCreated, Account } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { useAccounts } from "../accounts/api";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import {
  type CoverFilter,
  useArrangeCover,
  useCoverArrangements,
  useDelegableAccess,
  useEndCover,
} from "./delegationsApi";

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
export const formatWhen = (value?: string | null) => (value ? when.format(new Date(value)) : "—");

export const COVER_STATUS: Record<
  AccessDelegation["status"],
  { label: string; color: "success" | "info" | "default" | "warning" }
> = {
  active: { label: "Active now", color: "success" },
  scheduled: { label: "Starts later", color: "info" },
  finished: { label: "Finished", color: "default" },
  ended_early: { label: "Ended early", color: "warning" },
};

/** Up to 30 days (HIMS_DELEGATION_MAX_DAYS on the server, which has the final say). */
const MAX_DAYS = 30;

function localDate(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function PersonPicker({
  label,
  value,
  onChange,
  excludeId,
}: {
  label: string;
  value: Account | null;
  onChange: (person: Account | null) => void;
  excludeId?: string;
}) {
  const [search, setSearch] = useState("");
  const accounts = useAccounts({ search, kind: "", status: "active" });
  const options = (accounts.data?.results ?? []).filter((a) => a.id !== excludeId);
  return (
    <Autocomplete
      options={options}
      value={value}
      onChange={(_, person) => onChange(person)}
      onInputChange={(_, text, reason) => reason === "input" && setSearch(text)}
      getOptionLabel={(a) => `${a.display_name} (${a.email})`}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      filterOptions={(list) => list}
      loading={accounts.isFetching}
      renderInput={(params) => <TextField {...params} label={label} required helperText="Type part of a name or email" />}
    />
  );
}

function ArrangeCoverDialog({ onClose, onDone }: { onClose: () => void; onDone: (result: AccessDelegationCreated) => void }) {
  const arrange = useArrangeCover(useState(() => crypto.randomUUID())[0]);
  const [delegator, setDelegator] = useState<Account | null>(null);
  const [delegate, setDelegate] = useState<Account | null>(null);
  const [startsLater, setStartsLater] = useState(false);
  const [startsOn, setStartsOn] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [reason, setReason] = useState("");
  // Everything that can be lent is ticked unless unticked here (reset for another person).
  const [unticked, setUnticked] = useState<string[]>([]);
  const lendable = useDelegableAccess(delegator?.id ?? "");
  const chosen = (lendable.data ?? []).filter((a) => a.can_lend && !unticked.includes(a.id)).map((a) => a.id);
  const [{ today, maxEnd }] = useState(() => {
    const now = new Date();
    return { today: localDate(now), maxEnd: localDate(new Date(now.getTime() + MAX_DAYS * 86_400_000)) };
  });
  const ready =
    !!delegator && !!delegate && !!endsOn && !!reason.trim() && chosen.length > 0 && (!startsLater || !!startsOn);

  return (
    <FormDialog
      title="Arrange cover"
      error={arrange.error}
      fields={["delegator", "delegate", "starts_at", "ends_at", "reason", "assignments"]}
      submitLabel="Arrange cover"
      submitDisabled={!ready}
      pending={arrange.isPending}
      onClose={onClose}
      maxWidth="md"
      onSubmit={() =>
        arrange.mutate(
          {
            delegator: delegator!.id,
            delegate: delegate!.id,
            starts_at: startsLater ? new Date(`${startsOn}T00:00:00`).toISOString() : null,
            ends_at: new Date(`${endsOn}T23:59:59`).toISOString(),
            reason: reason.trim(),
            assignments: chosen,
          },
          { onSuccess: onDone },
        )
      }
    >
      <Typography variant="body2">
        For a limited time, one person works with some or all of another person&apos;s access, e.g. during leave.
        Everything they do is still recorded under their own name. The access ends by itself.
      </Typography>
      <PersonPicker
        label="Person being covered"
        value={delegator}
        onChange={(person) => {
          setDelegator(person);
          setUnticked([]);
        }}
        excludeId={delegate?.id}
      />
      <PersonPicker label="Person covering" value={delegate} onChange={setDelegate} excludeId={delegator?.id} />
      {delegator && (
        <Box>
          <Typography variant="body2" sx={{ mb: 0.5 }}>
            Access to lend
          </Typography>
          {lendable.isPending && <LinearProgress />}
          {lendable.error && <ErrorAlert error={lendable.error} />}
          {lendable.data?.length === 0 && (
            <Typography variant="body2">{delegator.display_name} has no access at the moment.</Typography>
          )}
          <FormGroup>
            {lendable.data?.map((a) => (
              <FormControlLabel
                key={a.id}
                disabled={!a.can_lend}
                control={
                  <Checkbox
                    checked={chosen.includes(a.id)}
                    onChange={(e) =>
                      setUnticked((current) =>
                        e.target.checked ? current.filter((id) => id !== a.id) : [...current, a.id],
                      )
                    }
                  />
                }
                label={
                  <span>
                    {a.role_name} · {a.scope}
                    {!a.can_lend && (
                      <Typography variant="caption" component="span" sx={{ display: "block" }}>
                        {a.why_not}
                      </Typography>
                    )}
                  </span>
                }
              />
            ))}
          </FormGroup>
        </Box>
      )}
      <FormControlLabel
        control={<Checkbox checked={startsLater} onChange={(e) => setStartsLater(e.target.checked)} />}
        label="Starts on a later day (otherwise it starts now)"
      />
      <Stack direction="row" spacing={2}>
        {startsLater && (
          <TextField
            type="date"
            label="Starts on"
            required
            value={startsOn}
            onChange={(e) => setStartsOn(e.target.value)}
            slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: today, max: maxEnd } }}
            fullWidth
          />
        )}
        <TextField
          type="date"
          label="Ends on (end of that day)"
          required
          value={endsOn}
          onChange={(e) => setEndsOn(e.target.value)}
          helperText={`At most ${MAX_DAYS} days`}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: startsOn || today, max: maxEnd } }}
          fullWidth
        />
      </Stack>
      <TextField
        label="Reason"
        required
        multiline
        minRows={2}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        helperText="e.g. Annual leave 4–15 November"
      />
    </FormDialog>
  );
}

function EndCoverDialog({ cover, onClose }: { cover: AccessDelegation; onClose: () => void }) {
  const end = useEndCover(cover.id);
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`End cover now · ${cover.delegate.display_name}`}
      error={end.error}
      fields={["reason"]}
      submitLabel="End cover now"
      submitColor="error"
      submitDisabled={!reason.trim()}
      pending={end.isPending}
      onClose={onClose}
      onSubmit={() => end.mutate({ version: cover.version, reason: reason.trim() }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        {cover.delegate.display_name} loses the access lent from {cover.delegator.display_name} at once. Both are
        emailed.
      </Typography>
      <TextField
        label="Why is it ending early?"
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        helperText="e.g. Back from leave early"
      />
    </FormDialog>
  );
}

export function CoverStatusChip({ cover }: { cover: AccessDelegation }) {
  const status = COVER_STATUS[cover.status];
  return <Chip size="small" color={status.color} label={status.label} />;
}

export function LentAccessList({ cover }: { cover: AccessDelegation }) {
  return (
    <>
      {cover.lent_access.map((a) => (
        <Typography key={a.id} variant="caption" component="p" sx={{ textDecoration: a.revoked_at ? "line-through" : "none" }}>
          {a.role_name} · {a.scope}
          {a.revoked_at ? ` (removed: ${a.revocation_reason})` : ""}
        </Typography>
      ))}
    </>
  );
}

export function CoverPage() {
  const { data: me } = useCurrentUser();
  const canManage = hasOrganizationWidePermission(me, "access.assignments.manage");
  const [tab, setTab] = useState<CoverFilter>("current");
  const { data, isPending, error } = useCoverArrangements(tab);
  const [arranging, setArranging] = useState(false);
  const [ending, setEnding] = useState<AccessDelegation>();
  const [result, setResult] = useState<AccessDelegationCreated>();

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
        <Box>
          <Typography variant="h5" component="h1">
            Cover arrangements
          </Typography>
          <Typography variant="body2">
            Lend a person&apos;s access to a colleague for a limited time, e.g. during leave. It ends by itself, or
            when either account is switched off.
          </Typography>
        </Box>
        {canManage && (
          <Button variant="contained" onClick={() => setArranging(true)}>
            Arrange cover
          </Button>
        )}
      </Box>

      {result && (
        <Alert severity={result.skipped.length ? "warning" : "success"} onClose={() => setResult(undefined)}>
          {result.delegate.display_name} covers for {result.delegator.display_name} until {formatWhen(result.ends_at)}.
          {result.skipped.map((s) => (
            <Typography key={`${s.role_name}-${s.scope}`} variant="body2">
              Not lent: {s.role_name} · {s.scope}: {s.why}
            </Typography>
          ))}
        </Alert>
      )}

      <Tabs value={tab} onChange={(_, value: CoverFilter) => setTab(value)}>
        <Tab value="current" label="Current and upcoming" />
        <Tab value="past" label="Past" />
      </Tabs>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Cover arrangements">
          <TableHead>
            <TableRow>
              <TableCell>Who covers</TableCell>
              <TableCell>For whom</TableCell>
              <TableCell>When</TableCell>
              <TableCell>Access lent</TableCell>
              <TableCell>Status</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.map((cover) => (
              <TableRow key={cover.id}>
                <TableCell>{cover.delegate.display_name}</TableCell>
                <TableCell>
                  {cover.delegator.display_name}
                  <Typography variant="caption" component="p">
                    {cover.reason}
                  </Typography>
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  {formatWhen(cover.starts_at)}
                  <Typography variant="caption" component="p">
                    to {formatWhen(cover.ends_at)}
                  </Typography>
                </TableCell>
                <TableCell>
                  <LentAccessList cover={cover} />
                </TableCell>
                <TableCell>
                  <CoverStatusChip cover={cover} />
                  {cover.ended_at && (
                    <Typography variant="caption" component="p">
                      {cover.end_reason}
                      {cover.ended_by_name ? ` (${cover.ended_by_name})` : ""}
                    </Typography>
                  )}
                </TableCell>
                <TableCell align="right">
                  {canManage && (cover.status === "active" || cover.status === "scheduled") && (
                    <Button
                      size="small"
                      color="error"
                      onClick={() => setEnding(cover)}
                      aria-label={`End cover by ${cover.delegate.display_name} for ${cover.delegator.display_name}`}
                    >
                      End now
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>{tab === "current" ? "No cover arranged at the moment." : "No past cover."}</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {arranging && (
        <ArrangeCoverDialog
          onClose={() => setArranging(false)}
          onDone={(created) => {
            setArranging(false);
            setResult(created);
          }}
        />
      )}
      {ending && <EndCoverDialog cover={ending} onClose={() => setEnding(undefined)} />}
    </Stack>
  );
}
