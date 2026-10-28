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
import { useSearchParams } from "react-router-dom";

import type { AuditEvent } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import {
  type AuditFilters,
  EMPTY_FILTERS,
  PAGE_SIZE,
  exportUrl,
  useAuditActions,
  useAuditSearch,
} from "./api";
import { AuditEventDialog } from "./AuditEventDialog";
import { CATEGORIES, OUTCOME, who } from "./labels";

export function AuditLogPage() {
  // A reference number can be opened directly, e.g. /audit?request_id=... from a support ticket.
  const [params] = useSearchParams();
  const initialReference = params.get("request_id") ?? "";
  const [form, setForm] = useState<AuditFilters>({ ...EMPTY_FILTERS, request_id: initialReference });
  const [applied, setApplied] = useState<AuditFilters | null>(
    initialReference ? { ...EMPTY_FILTERS, request_id: initialReference } : null,
  );
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<AuditEvent>();
  const actions = useAuditActions();
  const { data, isFetching, error } = useAuditSearch(applied, page + 1);

  const set = (name: keyof AuditFilters, value: string) =>
    setForm((current) => ({
      ...current,
      [name]: value,
      // a new category clears an event type from another category
      ...(name === "category" ? { action: "" } : {}),
    }));
  const search = () => {
    setPage(0);
    setApplied({ ...form });
  };
  const clear = () => {
    setForm(EMPTY_FILTERS);
    setApplied(null);
    setPage(0);
  };
  const eventChoices = (actions.data ?? []).filter(
    (a) => !form.category || a.action.startsWith(`${form.category}.`),
  );

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Audit log
        </Typography>
        <Typography variant="body2">
          Who did what, when and where. Records cannot be changed or deleted. Your searches and
          downloads are recorded too.
        </Typography>
      </Box>

      <Paper
        component="form"
        sx={{ p: 2 }}
        onSubmit={(event) => {
          event.preventDefault();
          search();
        }}
      >
        <Stack spacing={2}>
          <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", rowGap: 2 }}>
            <TextField
              size="small"
              label="Reference number"
              value={form.request_id}
              onChange={(e) => set("request_id", e.target.value)}
              helperText="From a 'no access' or error screen"
              sx={{ minWidth: 260 }}
            />
            <TextField
              size="small"
              label="Person"
              value={form.person}
              onChange={(e) => set("person", e.target.value)}
              helperText="Part of a name or email"
              sx={{ minWidth: 220 }}
            />
            <TextField
              size="small"
              type="date"
              label="From"
              value={form.date_from}
              onChange={(e) => set("date_from", e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              size="small"
              type="date"
              label="To"
              value={form.date_to}
              onChange={(e) => set("date_to", e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
            />
          </Stack>
          <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", rowGap: 2 }}>
            <TextField
              select
              size="small"
              label="Area"
              value={form.category}
              onChange={(e) => set("category", e.target.value)}
              sx={{ minWidth: 220 }}
            >
              <MenuItem value="">All areas</MenuItem>
              {CATEGORIES.map((c) => (
                <MenuItem key={c.value} value={c.value}>
                  {c.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              size="small"
              label="Event"
              value={form.action}
              onChange={(e) => set("action", e.target.value)}
              sx={{ minWidth: 300 }}
            >
              <MenuItem value="">All events</MenuItem>
              {eventChoices.map((a) => (
                <MenuItem key={a.action} value={a.action}>
                  {a.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              size="small"
              label="Outcome"
              value={form.outcome}
              onChange={(e) => set("outcome", e.target.value)}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="">Any</MenuItem>
              {Object.entries(OUTCOME).map(([value, o]) => (
                <MenuItem key={value} value={value}>
                  {o.label}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <Stack direction="row" spacing={1}>
            <Button type="submit" variant="contained">
              Search
            </Button>
            <Button onClick={clear}>Clear</Button>
            <Box sx={{ flex: 1 }} />
            {applied && (
              <Button component="a" href={exportUrl(applied)} variant="outlined">
                Download CSV
              </Button>
            )}
          </Stack>
        </Stack>
      </Paper>

      {error && <ErrorAlert error={error} />}
      {!applied && (
        <Typography variant="body2">
          Choose filters and press Search. Leave everything empty to see the latest events.
        </Typography>
      )}
      {applied && (
        <TableContainer component={Paper}>
          {isFetching && <LinearProgress />}
          <Table size="small" aria-label="Audit events">
            <TableHead>
              <TableRow>
                <TableCell>When</TableCell>
                <TableCell>What happened</TableCell>
                <TableCell>Who</TableCell>
                <TableCell>Facility</TableCell>
                <TableCell>Reference</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data?.results.map((event) => {
                const outcome = OUTCOME[event.outcome];
                return (
                  <TableRow
                    key={event.id}
                    hover
                    onClick={() => setOpen(event)}
                    sx={{ cursor: "pointer" }}
                  >
                    <TableCell sx={{ whiteSpace: "nowrap" }}>
                      {new Date(event.occurred_at).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      {event.action_label}
                      {outcome && event.outcome !== "success" && (
                        <Chip size="small" color={outcome.color} label={outcome.label} sx={{ ml: 1 }} />
                      )}
                      {event.reason && (
                        <Typography variant="caption" component="p">
                          {event.reason}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>{who(event)}</TableCell>
                    <TableCell>{event.facility_name ?? "—"}</TableCell>
                    <TableCell sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
                      {event.request_id ? event.request_id.slice(0, 13) : "—"}
                    </TableCell>
                  </TableRow>
                );
              })}
              {data?.results.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5}>No events match these filters.</TableCell>
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
      )}
      {open && <AuditEventDialog event={open} onClose={() => setOpen(undefined)} />}
    </Stack>
  );
}
