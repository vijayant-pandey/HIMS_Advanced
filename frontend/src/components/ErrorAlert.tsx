import { Alert, AlertTitle } from "@mui/material";

import { ApiError } from "../api/client";

/** Shows a safe, user-facing error with the request ID support needs to trace it. */
export function ErrorAlert({ error }: { error: unknown }) {
  if (error instanceof ApiError) {
    return (
      <Alert severity="error">
        <AlertTitle>{error.problem.title}</AlertTitle>
        {error.problem.detail}
        {error.problem.request_id && (
          <div style={{ fontSize: "0.75rem", marginTop: 4 }}>
            Reference: {error.problem.request_id}
          </div>
        )}
      </Alert>
    );
  }
  return <Alert severity="error">Something went wrong. Please try again.</Alert>;
}
