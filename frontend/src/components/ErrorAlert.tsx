import { Alert, AlertTitle, Box } from "@mui/material";

import { ApiError } from "../api/client";

function Reference({ value }: { value: string | null | undefined }) {
  if (!value) return null;
  return (
    <Box component="div" sx={{ fontSize: "0.75rem", mt: 0.5, opacity: 0.85 }}>
      Reference: <span style={{ fontFamily: "monospace" }}>{value}</span>
    </Box>
  );
}

/**
 * Shows a safe, user-facing error with the reference (request ID) support needs to trace it.
 * The same reference is stored in the audit log for permission denials (`access.denied`).
 */
export function ErrorAlert({ error }: { error: unknown }) {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return (
        <Alert severity="warning">
          <AlertTitle>You don't have access to this</AlertTitle>
          Ask your hospital administrator if you need it, and give them the reference below.
          <Reference value={error.problem.request_id} />
        </Alert>
      );
    }
    return (
      <Alert severity="error">
        <AlertTitle>{error.problem.title}</AlertTitle>
        {error.problem.detail}
        <Reference value={error.problem.request_id} />
      </Alert>
    );
  }
  return <Alert severity="error">Something went wrong. Please try again.</Alert>;
}
