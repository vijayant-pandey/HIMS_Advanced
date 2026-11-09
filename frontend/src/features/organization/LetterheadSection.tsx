import { Alert, Box, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { ApiError, api } from "../../api/client";
import type { Organization, OrganizationUpdateRequest } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { HIDE_WHEN_PRINTING, LetterheadView, letterheadKey, useLetterhead } from "../../components/Letterhead";

const ACCEPT = ".png,.jpg,.jpeg,image/png,image/jpeg";
const MAX_BYTES = 2 * 1024 * 1024; // same limit as the server (it checks again)

function useRefreshHospital() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["organization"] });
    void queryClient.invalidateQueries({ queryKey: letterheadKey });
  };
}

const FIELDS = [
  ["letterhead_phone", "Phone", ""],
  ["letterhead_email", "Email", ""],
  ["letterhead_website", "Website", ""],
  ["letterhead_registration", "Registration or tax number", "Shown as you type it, e.g. Reg. no. MH-1234"],
  ["letterhead_footer", "Last line", "e.g. a helpline"],
] as const;

function LetterheadDialog({ organization, onClose }: { organization: Organization; onClose: () => void }) {
  const refresh = useRefreshHospital();
  const save = useMutation<Organization, ApiError, OrganizationUpdateRequest>({
    mutationFn: (body) => api.patch<Organization>("/organization/", body),
    onSettled: refresh,
  });
  const [values, setValues] = useState({
    letterhead_address: organization.letterhead_address,
    letterhead_phone: organization.letterhead_phone,
    letterhead_email: organization.letterhead_email,
    letterhead_website: organization.letterhead_website,
    letterhead_registration: organization.letterhead_registration,
    letterhead_footer: organization.letterhead_footer,
  });
  const errors = fieldErrors(save.error);
  return (
    <FormDialog
      title="Edit letterhead"
      error={save.error}
      fields={Object.keys(values)}
      pending={save.isPending}
      onClose={onClose}
      onSubmit={() => save.mutate({ version: organization.version, ...values }, { onSuccess: onClose })}
    >
      <TextField
        label="Address"
        multiline
        minRows={3}
        value={values.letterhead_address}
        onChange={(event) => setValues({ ...values, letterhead_address: event.target.value })}
        error={!!errors.letterhead_address}
        helperText={errors.letterhead_address}
      />
      {FIELDS.map(([name, label, help]) => (
        <TextField
          key={name}
          label={label}
          value={values[name]}
          onChange={(event) => setValues({ ...values, [name]: event.target.value })}
          error={!!errors[name]}
          helperText={errors[name] ?? help}
        />
      ))}
    </FormDialog>
  );
}

/** Logo and letterhead for printouts and emails (HIMS-ORG-006; spec 4.1). */
export function LetterheadSection({ organization, canEdit }: { organization: Organization; canEdit: boolean }) {
  const refresh = useRefreshHospital();
  const letterhead = useLetterhead();
  const [editing, setEditing] = useState(false);
  const [tooBig, setTooBig] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation<Organization, ApiError, File>({
    mutationFn: (file) => {
      const form = new FormData();
      form.append("file", file);
      return api.post<Organization>("/organization/logo/", form);
    },
    onSettled: refresh,
  });
  const remove = useMutation<Organization, ApiError, void>({
    mutationFn: () => api.post<Organization>("/organization/logo/remove/"),
    onSettled: refresh,
  });
  const uploadError = fieldErrors(upload.error).file;

  const choose = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // choosing the same file again still counts
    if (!file) return;
    setTooBig(file.size > MAX_BYTES);
    if (file.size <= MAX_BYTES) upload.mutate(file);
  };

  return (
    <Paper component="section" aria-label="Letterhead" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Box sx={HIDE_WHEN_PRINTING}>
          <Typography variant="h6" component="h2">
            Letterhead
          </Typography>
          <Typography variant="body2">
            Appears at the top of printouts, and on the emails HIMS sends. Text messages stay plain.
          </Typography>
        </Box>
        {letterhead.error && <ErrorAlert error={letterhead.error} />}
        {letterhead.data && <LetterheadView letterhead={letterhead.data} />}
        {tooBig && <Alert severity="error">The logo is too large; the limit is 2 MB.</Alert>}
        {uploadError && <Alert severity="error">{uploadError}</Alert>}
        {upload.error && !uploadError && <ErrorAlert error={upload.error} />}
        {remove.error && <ErrorAlert error={remove.error} />}
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", ...HIDE_WHEN_PRINTING }}>
          {canEdit && (
            <>
              <input
                ref={input}
                type="file"
                accept={ACCEPT}
                aria-label="Logo file"
                onChange={choose}
                style={{ display: "none" }}
              />
              <Button onClick={() => input.current?.click()} disabled={upload.isPending}>
                {organization.has_logo ? "Replace logo" : "Upload logo"}
              </Button>
              {organization.has_logo && (
                <Button onClick={() => remove.mutate()} disabled={remove.isPending}>
                  Remove logo
                </Button>
              )}
              <Button onClick={() => setEditing(true)}>Edit letterhead</Button>
            </>
          )}
          <Button onClick={() => window.print()}>Print a sample</Button>
        </Stack>
        {canEdit && (
          <Typography variant="caption" sx={HIDE_WHEN_PRINTING}>
            Logo: a PNG or JPG picture, up to 2 MB.
          </Typography>
        )}
      </Stack>
      {editing && <LetterheadDialog organization={organization} onClose={() => setEditing(false)} />}
    </Paper>
  );
}
