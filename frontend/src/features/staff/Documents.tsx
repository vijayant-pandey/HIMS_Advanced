import { Box, Button, Link, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";

import type { StaffDocument } from "../../api/types";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { documentUrl, useArchiveDocument, useUploadDocument } from "./api";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";
const MAX_BYTES = 10 * 1024 * 1024; // same limit as the server (it checks again)

function size(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function UploadDocumentDialog({
  staffId,
  target,
  label,
  onClose,
}: {
  staffId: string;
  target: { credential?: string; qualification?: string };
  label: string;
  onClose: () => void;
}) {
  const upload = useUploadDocument(staffId);
  const [file, setFile] = useState<File | null>(null);
  const tooBig = !!file && file.size > MAX_BYTES;
  // e.g. "Only PDF, JPG or PNG files can be uploaded." (the server reads the real file type)
  const fileError = fieldErrors(upload.error).file;
  return (
    <FormDialog
      title={`Upload document · ${label}`}
      error={upload.error}
      fields={["file"]}
      submitLabel="Upload"
      submitDisabled={!file || tooBig}
      pending={upload.isPending}
      onClose={onClose}
      maxWidth="xs"
      onSubmit={() => file && upload.mutate({ file, ...target }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        A clear scan or photo of the certificate: PDF, JPG or PNG, up to 10 MB. Only people who can
        see staff records can open it, and every opening is recorded in the audit log.
      </Typography>
      <Button variant="outlined" component="label">
        Choose file
        <input
          hidden
          type="file"
          accept={ACCEPT}
          aria-label="Document file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </Button>
      {file && (
        <Typography variant="body2" color={tooBig ? "error" : undefined}>
          {file.name} ({size(file.size)}){tooBig && " is larger than 10 MB."}
        </Typography>
      )}
      {fileError && (
        <Typography variant="body2" color="error">
          {fileError}
        </Typography>
      )}
    </FormDialog>
  );
}

function ArchiveDialog({ document, onClose }: { document: StaffDocument; onClose: () => void }) {
  const archive = useArchiveDocument(document.id);
  const [reason, setReason] = useState("");
  return (
    <FormDialog
      title={`Archive · ${document.original_name}`}
      error={archive.error}
      fields={["reason"]}
      submitLabel="Archive"
      submitColor="error"
      submitDisabled={!reason.trim()}
      pending={archive.isPending}
      onClose={onClose}
      maxWidth="xs"
      onSubmit={() => archive.mutate({ reason: reason.trim() }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        The file is kept for the record but no longer shown as current. Nothing is deleted.
      </Typography>
      <TextField
        label="Reason"
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        helperText="e.g. Wrong file, or replaced by the renewed licence"
      />
    </FormDialog>
  );
}

/** The documents of one licence or qualification, with open / download / archive / upload. */
export function DocumentCell({
  staffId,
  documents,
  target,
  label,
  canManage,
}: {
  staffId: string;
  documents: StaffDocument[];
  target: { credential?: string; qualification?: string };
  label: string;
  canManage: boolean;
}) {
  const [uploading, setUploading] = useState(false);
  const [archiving, setArchiving] = useState<StaffDocument>();
  const current = documents.filter((d) => !d.is_archived);
  const archived = documents.length - current.length;
  return (
    <Box>
      <Stack spacing={0.5}>
        {current.map((d) => (
          <Box key={d.id}>
            <Link href={documentUrl(d.id, true)} target="_blank" rel="noopener" variant="body2">
              {d.original_name}
            </Link>{" "}
            <Typography component="span" variant="caption">
              ({size(d.size_bytes)}) ·{" "}
              <Link href={documentUrl(d.id, false)} variant="caption">
                download
              </Link>
              {canManage && (
                <>
                  {" · "}
                  <Link component="button" variant="caption" onClick={() => setArchiving(d)}>
                    archive
                  </Link>
                </>
              )}
            </Typography>
          </Box>
        ))}
        {current.length === 0 && <Typography variant="caption">No document</Typography>}
        {archived > 0 && <Typography variant="caption">{archived} archived</Typography>}
      </Stack>
      {canManage && (
        <Button size="small" onClick={() => setUploading(true)} aria-label={`Upload document for ${label}`}>
          Upload
        </Button>
      )}
      {uploading && (
        <UploadDocumentDialog
          staffId={staffId}
          target={target}
          label={label}
          onClose={() => setUploading(false)}
        />
      )}
      {archiving && <ArchiveDialog document={archiving} onClose={() => setArchiving(undefined)} />}
    </Box>
  );
}
