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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, api } from "../../api/client";
import type { MessagePreview, MessageTemplate } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { fieldErrors } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";

const key = ["message-templates"] as const;

function useMessageTemplates() {
  return useQuery<MessageTemplate[], ApiError>({
    queryKey: key,
    queryFn: ({ signal }) => api.get<MessageTemplate[]>("/message-templates/", { signal }),
  });
}

function WordingDialog({
  template,
  canChange,
  onClose,
}: {
  template: MessageTemplate;
  canChange: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });
  const [subject, setSubject] = useState(template.subject);
  const [body, setBody] = useState(template.body);
  const save = useMutation<MessageTemplate, ApiError, void>({
    mutationFn: () =>
      api.patch<MessageTemplate>(`/message-templates/${template.id}/`, { version: template.version, subject, body }),
    onSettled: refresh,
  });
  const reset = useMutation<MessageTemplate, ApiError, void>({
    mutationFn: () => api.post<MessageTemplate>(`/message-templates/${template.id}/reset/`, { version: template.version }),
    onSettled: refresh,
  });
  const preview = useMutation<MessagePreview, ApiError, void>({
    mutationFn: () => api.post<MessagePreview>(`/message-templates/${template.id}/preview/`, { subject, body }),
  });
  const errors = { ...fieldErrors(preview.error), ...fieldErrors(save.error) };
  const otherError = [save.error, reset.error, preview.error].find(
    (error) => error && Object.keys(fieldErrors(error)).length === 0,
  );

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{template.name}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2">Sent when: {template.when}</Typography>
          {otherError && <ErrorAlert error={otherError} />}
          <TextField
            label="Subject"
            value={subject}
            onChange={(event) => {
              setSubject(event.target.value);
              preview.reset();
            }}
            disabled={!canChange}
            error={!!errors.subject}
            helperText={errors.subject}
          />
          <TextField
            label="Message"
            multiline
            minRows={8}
            value={body}
            onChange={(event) => {
              setBody(event.target.value);
              preview.reset();
            }}
            disabled={!canChange}
            error={!!errors.body}
            helperText={errors.body ?? "Plain text. No patient details."}
          />
          <Box>
            <Typography variant="subtitle2" component="h2">
              Placeholders you can use
            </Typography>
            <Box component="ul" aria-label="Placeholders" sx={{ m: 0, pl: 2.5 }}>
              {template.variables.map((variable) => (
                <Typography key={variable.name} component="li" variant="body2">
                  <code>{`{{${variable.name}}}`}</code>: {variable.description}
                  {variable.required ? " (must stay)" : ""}
                </Typography>
              ))}
            </Box>
          </Box>
          {preview.data && (
            <Paper variant="outlined" sx={{ p: 2 }} component="section" aria-label="Preview">
              <Typography variant="subtitle2" component="h2">
                Preview, with made-up details
              </Typography>
              <Typography variant="body2">Subject: {preview.data.subject}</Typography>
              <Box component="pre" sx={{ m: 0, mt: 1, whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: "0.875rem" }}>
                {preview.data.body}
              </Box>
            </Paper>
          )}
          {canChange && (
            <Alert severity="info">Changes apply to the next message sent. Each change is in the audit log.</Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        {canChange && template.is_customised && (
          <Button onClick={() => reset.mutate(undefined, { onSuccess: onClose })} disabled={reset.isPending}>
            Use the standard wording
          </Button>
        )}
        <Button onClick={() => preview.mutate()} disabled={preview.isPending}>
          Preview
        </Button>
        <Button onClick={onClose}>{canChange ? "Cancel" : "Close"}</Button>
        {canChange && (
          <Button
            variant="contained"
            onClick={() => save.mutate(undefined, { onSuccess: onClose })}
            disabled={save.isPending || !subject.trim() || !body.trim()}
          >
            Save
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

/** The wording of every message HIMS sends (HIMS-NOTIF-003; spec 4.1, 4.23). */
export function MessageTemplatesPage() {
  const { data: me } = useCurrentUser();
  const canChange = hasOrganizationWidePermission(me, "notifications.templates.manage");
  const { data, isPending, error } = useMessageTemplates();
  const [openId, setOpenId] = useState<string>();
  const open = data?.find((template) => template.id === openId);

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Message wording
        </Typography>
        <Typography variant="body2">
          The words of every email HIMS sends. {canChange ? "Change them to suit your hospital; " : ""}
          the standard wording is always kept and can be used again.
        </Typography>
      </Box>
      {isPending && <LinearProgress aria-label="Loading message wording" />}
      {error && <ErrorAlert error={error} />}
      {data && (
        <TableContainer component={Paper}>
          <Table size="small" aria-label="Message wording">
            <TableHead>
              <TableRow>
                <TableCell>Message</TableCell>
                <TableCell>Sent when</TableCell>
                <TableCell>Wording</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.map((template) => (
                <TableRow key={template.id} hover>
                  <TableCell>
                    <Button variant="text" size="small" sx={{ p: 0, minWidth: 0, textAlign: "left" }} onClick={() => setOpenId(template.id)}>
                      {template.name}
                    </Button>
                  </TableCell>
                  <TableCell>{template.when}</TableCell>
                  <TableCell>
                    {template.is_customised ? (
                      <Chip size="small" color="primary" label="Changed" />
                    ) : (
                      <Chip size="small" variant="outlined" label="Standard" />
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      {open && <WordingDialog key={open.version} template={open} canChange={canChange} onClose={() => setOpenId(undefined)} />}
    </Stack>
  );
}
