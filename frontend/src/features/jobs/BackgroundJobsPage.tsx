import {
  Alert,
  Box,
  Button,
  Chip,
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

import type { OutboxEvent } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { type Show, useDecideEvent, useJobEvents, useJobHealth } from "./api";

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const formatWhen = (value?: string | null) => (value ? when.format(new Date(value)) : "—");

const TABS: { value: Show; label: string }[] = [
  { value: "attention", label: "Needs a look" },
  { value: "failed", label: "Failed" },
  { value: "waiting", label: "Waiting" },
  { value: "dismissed", label: "Dismissed" },
];

const STATUS_COLOR: Record<OutboxEvent["status"], "default" | "warning" | "error" | "success"> = {
  pending: "warning",
  dead: "error",
  dismissed: "default",
  published: "success",
};

function DecisionDialog({
  event,
  decision,
  onClose,
}: {
  event: OutboxEvent;
  decision: "send-again" | "dismiss";
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const decide = useDecideEvent(event.id, decision);
  const sending = decision === "send-again";
  return (
    <FormDialog
      title={sending ? "Send this event again" : "Dismiss this event"}
      error={decide.error}
      fields={["reason"]}
      submitLabel={sending ? "Send again" : "Dismiss"}
      submitColor={sending ? "primary" : "error"}
      submitDisabled={!reason.trim()}
      pending={decide.isPending}
      onClose={onClose}
      onSubmit={() => decide.mutate({ reason: reason.trim() }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        <strong>{event.event_label}</strong> from {formatWhen(event.occurred_at)}, tried {event.attempts} time(s).
      </Typography>
      <Typography variant="body2">
        {sending
          ? "Only after the cause is fixed (for example the email server works again): the event gets a fresh set of retries."
          : "Only if it can never succeed (for example what it was about no longer exists). It will never be tried again."}
      </Typography>
      <TextField
        label="Reason (kept in the audit log)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        required
        multiline
        minRows={2}
        slotProps={{ htmlInput: { maxLength: 300 } }}
      />
    </FormDialog>
  );
}

export function BackgroundJobsPage() {
  const { data: me } = useCurrentUser();
  const canManage = hasOrganizationWidePermission(me, "platform.jobs.manage");
  const [show, setShow] = useState<Show>("attention");
  const [deciding, setDeciding] = useState<{ event: OutboxEvent; decision: "send-again" | "dismiss" }>();
  const health = useJobHealth();
  const events = useJobEvents(show);
  const h = health.data;

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Background jobs
        </Typography>
        <Typography variant="body2">
          Some work happens just after a change is saved, for example sending an account invitation. If it fails, HIMS
          tries again automatically ({h ? `up to ${h.max_attempts} times` : "several times"}, waiting longer each time).
          Work that still fails waits here for a person to decide. Finished work is cleaned up after{" "}
          {h ? `${h.retention_days} days` : "a while"}.
        </Typography>
      </Box>

      {health.error && <ErrorAlert error={health.error} />}
      {health.isLoading && <LinearProgress />}
      {h && (
        <>
          {h.attention.length === 0 ? (
            <Alert severity="success">Everything is flowing: nothing needs a look.</Alert>
          ) : (
            <Alert severity="warning">
              {h.attention.join(". ")}. What to do: see the runbook “Background jobs”.
            </Alert>
          )}
          <Paper sx={{ p: 2 }}>
            <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: 1 }}>
              <Typography component="dt" variant="body2" color="text.secondary">
                Waiting
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                {h.waiting} (oldest {h.oldest_waiting_minutes} minute(s); being retried: {h.retrying})
              </Typography>
              <Typography component="dt" variant="body2" color="text.secondary">
                Failed, needs a decision
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                {h.failed}
              </Typography>
              <Typography component="dt" variant="body2" color="text.secondary">
                Done in the last 24 hours
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                {h.published_last_24h}
              </Typography>
              <Typography component="dt" variant="body2" color="text.secondary">
                Last clean-up
              </Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0 }}>
                {h.last_cleanup
                  ? `${formatWhen(h.last_cleanup.at)}: ${h.last_cleanup.events_deleted} old event(s) removed`
                  : "Not run yet (it runs every day)"}
              </Typography>
            </Box>
          </Paper>
        </>
      )}

      <Tabs value={show} onChange={(_, value: Show) => setShow(value)} aria-label="Which events">
        {TABS.map((tab) => (
          <Tab key={tab.value} value={tab.value} label={tab.label} />
        ))}
      </Tabs>
      {events.error && <ErrorAlert error={events.error} />}
      <TableContainer component={Paper}>
        {events.isLoading && <LinearProgress />}
        <Table size="small" aria-label="Background events">
          <TableHead>
            <TableRow>
              <TableCell>What</TableCell>
              <TableCell>When</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Tries</TableCell>
              <TableCell>Last error</TableCell>
              <TableCell>Decision</TableCell>
              {canManage && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {events.data?.map((event) => (
              <TableRow key={event.id}>
                <TableCell>
                  {event.event_label}
                  <Typography variant="caption" component="p" sx={{ fontFamily: "monospace" }}>
                    {event.event_type} · {event.aggregate_type} {event.aggregate_id}
                  </Typography>
                </TableCell>
                <TableCell>{formatWhen(event.occurred_at)}</TableCell>
                <TableCell>
                  <Chip size="small" color={STATUS_COLOR[event.status]} label={event.status_label} />
                </TableCell>
                <TableCell align="right">{event.attempts}</TableCell>
                <TableCell>{event.last_error || "—"}</TableCell>
                <TableCell>
                  {event.resolution_note
                    ? `${event.resolution_note} (${event.resolved_by_name ?? "system"}, ${formatWhen(event.resolved_at)})`
                    : "—"}
                </TableCell>
                {canManage && (
                  <TableCell sx={{ whiteSpace: "nowrap" }}>
                    {(event.status === "dead" || event.status === "pending") && (
                      <Button
                        size="small"
                        aria-label={`Send again: ${event.event_label}`}
                        onClick={() => setDeciding({ event, decision: "send-again" })}
                      >
                        Send again
                      </Button>
                    )}
                    {event.status === "dead" && (
                      <Button
                        size="small"
                        color="error"
                        aria-label={`Dismiss: ${event.event_label}`}
                        onClick={() => setDeciding({ event, decision: "dismiss" })}
                      >
                        Dismiss
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
            {events.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={canManage ? 7 : 6}>Nothing here.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {deciding && (
        <DecisionDialog event={deciding.event} decision={deciding.decision} onClose={() => setDeciding(undefined)} />
      )}
    </Stack>
  );
}
