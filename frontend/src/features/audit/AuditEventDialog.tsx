import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import type { AuditEvent } from "../../api/types";
import { OUTCOME, who } from "./labels";

type Changes = { before?: Record<string, unknown>; after?: Record<string, unknown> };

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ display: "flex", gap: 2 }}>
      <Typography variant="body2" sx={{ minWidth: 150, color: "text.secondary" }}>
        {label}
      </Typography>
      <Typography variant="body2" component="div" sx={{ wordBreak: "break-word" }}>
        {children}
      </Typography>
    </Box>
  );
}

/** Everything recorded about one event, including before/after values. */
export function AuditEventDialog({ event, onClose }: { event: AuditEvent; onClose: () => void }) {
  const changes = (event.changes ?? {}) as Changes;
  const fields = [...new Set([...Object.keys(changes.before ?? {}), ...Object.keys(changes.after ?? {})])];
  const metadata = Object.entries(event.metadata ?? {});
  const outcome = OUTCOME[event.outcome] ?? { label: event.outcome, color: "default" as const };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>
        {event.action_label}{" "}
        <Chip size="small" color={outcome.color} label={outcome.label} sx={{ ml: 1 }} />
      </DialogTitle>
      <DialogContent>
        <Stack spacing={1}>
          <Row label="When">{new Date(event.occurred_at).toLocaleString()}</Row>
          <Row label="Who">{who(event)}</Row>
          <Row label="Facility">{event.facility_name ?? "—"}</Row>
          <Row label="Record">
            {event.resource_type} {event.resource_id && <code>{event.resource_id}</code>}
          </Row>
          <Row label="Reason">{event.reason || "—"}</Row>
          <Row label="Reference number">
            {event.request_id ? <code>{event.request_id}</code> : "—"}
          </Row>
          <Row label="IP address">{event.ip_address ?? "—"}</Row>
          <Row label="Event code">
            <code>{event.action}</code>
          </Row>
        </Stack>
        {fields.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2">What changed</Typography>
            <Table size="small" aria-label="What changed">
              <TableHead>
                <TableRow>
                  <TableCell>Field</TableCell>
                  <TableCell>Before</TableCell>
                  <TableCell>After</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {fields.map((field) => (
                  <TableRow key={field}>
                    <TableCell>{field}</TableCell>
                    <TableCell>{show(changes.before?.[field])}</TableCell>
                    <TableCell>{show(changes.after?.[field])}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
        {metadata.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2">More details</Typography>
            <Stack spacing={0.5} sx={{ mt: 0.5 }}>
              {metadata.map(([key, value]) => (
                <Row key={key} label={key}>
                  {show(value)}
                </Row>
              ))}
            </Stack>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
