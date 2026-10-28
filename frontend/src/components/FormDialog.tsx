import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
} from "@mui/material";
import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import { ErrorAlert } from "./ErrorAlert";

/** Server field messages by field name, e.g. {"code": "This code is already used."}. */
export function fieldErrors(error: unknown): Record<string, string> {
  const result: Record<string, string> = {};
  if (error instanceof ApiError) {
    for (const item of error.problem.errors ?? []) {
      if (item.field) result[item.field] = item.message;
    }
  }
  return result;
}

interface Props {
  title: string;
  /** The save request's error: field messages go next to fields, anything else at the top. */
  error: unknown;
  /** Fields shown in this form; server messages for other fields are shown at the top. */
  fields?: string[];
  submitLabel?: string;
  submitDisabled?: boolean;
  submitColor?: "primary" | "error";
  pending: boolean;
  onSubmit: () => void;
  onClose: () => void;
  maxWidth?: "xs" | "sm" | "md";
  children: ReactNode;
}

/** The standard add/edit dialog: title, errors, fields, Cancel and Save. */
export function FormDialog({
  title,
  error,
  fields = [],
  submitLabel = "Save",
  submitDisabled = false,
  submitColor = "primary",
  pending,
  onSubmit,
  onClose,
  maxWidth = "sm",
  children,
}: Props) {
  const byField = fieldErrors(error);
  const elsewhere = Object.keys(byField).some((name) => !fields.includes(name));
  const showTop = !!error && (Object.keys(byField).length === 0 || elsewhere);
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth={maxWidth}>
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <DialogTitle>{title}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {showTop && <ErrorAlert error={error} />}
            {children}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            type="submit"
            variant="contained"
            color={submitColor}
            disabled={pending || submitDisabled}
          >
            {submitLabel}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
