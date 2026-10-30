import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, api } from "../../api/client";
import type { Notification, PaginatedNotificationList, TestMessageRequest } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";

const key = ["notifications"] as const;
const PAGE_SIZE = 50;
const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

const STATUS: Record<Notification["status"], { label: string; color: "success" | "error" | "warning" | "default" | "info" }> = {
  sent: { label: "Sent", color: "success" },
  pending: { label: "Waiting", color: "info" },
  failed: { label: "Failed, will retry", color: "warning" },
  gave_up: { label: "Failed", color: "error" },
  skipped: { label: "Not sent", color: "default" },
};

function useNotifications(filters: { status: string; channel: string; search: string }, page: number) {
  return useQuery<PaginatedNotificationList, ApiError>({
    queryKey: [...key, filters, page],
    queryFn: ({ signal }) =>
      api.get<PaginatedNotificationList>("/notifications/", { query: { ...filters, page, page_size: PAGE_SIZE }, signal }),
    placeholderData: keepPreviousData,
  });
}

function useSendAgain(id: string) {
  const queryClient = useQueryClient();
  return useMutation<Notification, ApiError, void>({
    mutationFn: () => api.post<Notification>(`/notifications/${id}/send-again/`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}

function useSendTest() {
  const queryClient = useQueryClient();
  return useMutation<Notification, ApiError, TestMessageRequest>({
    mutationFn: (body) => api.post<Notification>("/notifications/test/", body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}

function MessageDialog({ message, canManage, onClose }: { message: Notification; canManage: boolean; onClose: () => void }) {
  const sendAgain = useSendAgain(message.id);
  const shown = sendAgain.data ?? message;
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{shown.subject || `${shown.channel_label} message`}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5}>
          <Typography variant="body2">
            {shown.channel_label} to {shown.recipients.join(", ") || "—"} · {when.format(new Date(shown.created_at))} ·{" "}
            <Chip size="small" color={STATUS[shown.status].color} label={STATUS[shown.status].label} /> · attempts{" "}
            {shown.attempts}
          </Typography>
          {shown.last_error && <Alert severity="warning">Last error: {shown.last_error}</Alert>}
          {shown.skip_reason && <Alert severity="info">{shown.skip_reason}</Alert>}
          <Typography variant="caption" color="text.secondary">
            Sign-in links and other secrets are hidden in this copy; the person received the real message.
          </Typography>
          <Box component="pre" sx={{ m: 0, p: 1.5, bgcolor: "background.default", borderRadius: 1, whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: "0.8125rem" }}>
            {shown.body}
          </Box>
          {sendAgain.error && <ErrorAlert error={sendAgain.error} />}
        </Stack>
      </DialogContent>
      <DialogActions>
        {canManage && shown.can_send_again && (
          <Button variant="contained" onClick={() => sendAgain.mutate()} disabled={sendAgain.isPending}>
            Send again now
          </Button>
        )}
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

function TestDialog({ onClose }: { onClose: () => void }) {
  const send = useSendTest();
  const [channel, setChannel] = useState<"email" | "sms">("email");
  const [to, setTo] = useState("");
  return (
    <FormDialog
      title="Send a test message"
      error={send.error}
      fields={["channel", "to"]}
      submitLabel="Send test"
      submitDisabled={!to.trim()}
      pending={send.isPending}
      onClose={onClose}
      onSubmit={() => send.mutate({ channel, to: to.trim() })}
    >
      <Typography variant="body2">
        Checks that HIMS can send email or SMS. The message contains no personal or medical information.
      </Typography>
      <TextField select label="Channel" value={channel} onChange={(e) => setChannel(e.target.value as "email" | "sms")}>
        <MenuItem value="email">Email</MenuItem>
        <MenuItem value="sms">SMS</MenuItem>
      </TextField>
      <TextField
        label={channel === "email" ? "Email address" : "Mobile number"}
        value={to}
        onChange={(e) => setTo(e.target.value)}
        helperText={channel === "sms" ? "With country code, e.g. +919876543210" : undefined}
      />
      {send.data && (
        <Alert severity={send.data.status === "sent" ? "success" : "warning"}>
          {send.data.status === "sent" ? "Sent." : `${STATUS[send.data.status].label}. ${send.data.last_error || send.data.skip_reason}`}
        </Alert>
      )}
    </FormDialog>
  );
}

/** Every email and SMS HIMS sent, and whether it arrived (HIMS-NOTIF-001). */
export function NotificationsPage() {
  const { data: me } = useCurrentUser();
  const canManage = hasOrganizationWidePermission(me, "notifications.manage");
  const [filters, setFilters] = useState({ status: "", channel: "", search: "" });
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<Notification>();
  const [testing, setTesting] = useState(false);
  const { data, isFetching, error } = useNotifications(filters, page + 1);
  const set = (name: keyof typeof filters, value: string) => {
    setFilters((current) => ({ ...current, [name]: value }));
    setPage(0);
  };

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
        <Box>
          <Typography variant="h5" component="h1">
            Messages
          </Typography>
          <Typography variant="body2">
            Every email and SMS HIMS has sent. Failed messages are retried automatically for a few hours.
          </Typography>
        </Box>
        {canManage && (
          <Button variant="contained" onClick={() => setTesting(true)}>
            Send a test message
          </Button>
        )}
      </Box>
      <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", rowGap: 2 }}>
        <TextField size="small" label="Search" value={filters.search} onChange={(e) => set("search", e.target.value)} helperText="Subject, message name or recipient" />
        <TextField select size="small" label="Status" value={filters.status} onChange={(e) => set("status", e.target.value)} sx={{ minWidth: 180 }}>
          <MenuItem value="">Any</MenuItem>
          {Object.entries(STATUS).map(([value, s]) => (
            <MenuItem key={value} value={value}>
              {s.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField select size="small" label="Channel" value={filters.channel} onChange={(e) => set("channel", e.target.value)} sx={{ minWidth: 140 }}>
          <MenuItem value="">Any</MenuItem>
          <MenuItem value="email">Email</MenuItem>
          <MenuItem value="sms">SMS</MenuItem>
        </TextField>
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isFetching && <LinearProgress />}
        <Table size="small" aria-label="Messages">
          <TableHead>
            <TableRow>
              <TableCell>When</TableCell>
              <TableCell>Channel</TableCell>
              <TableCell>To</TableCell>
              <TableCell>Subject</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((message) => (
              <TableRow key={message.id} hover onClick={() => setOpen(message)} sx={{ cursor: "pointer" }}>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{when.format(new Date(message.created_at))}</TableCell>
                <TableCell>{message.channel_label}</TableCell>
                <TableCell>{message.recipients.join(", ") || "—"}</TableCell>
                <TableCell>
                  <Button variant="text" size="small" sx={{ p: 0, minWidth: 0, textAlign: "left" }} onClick={() => setOpen(message)}>
                    {message.subject || message.template}
                  </Button>
                </TableCell>
                <TableCell>
                  <Chip size="small" color={STATUS[message.status].color} label={STATUS[message.status].label} />
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>No messages match.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {data && data.count > PAGE_SIZE && (
          <TablePagination component="div" count={data.count} page={page} rowsPerPage={PAGE_SIZE} rowsPerPageOptions={[PAGE_SIZE]} onPageChange={(_, value: number) => setPage(value)} />
        )}
      </TableContainer>
      {open && <MessageDialog message={open} canManage={canManage} onClose={() => setOpen(undefined)} />}
      {testing && <TestDialog onClose={() => setTesting(false)} />}
    </Stack>
  );
}
