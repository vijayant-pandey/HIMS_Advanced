import { Alert, Box, Button, CircularProgress, Typography } from "@mui/material";
import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useConfirmPasswordReset, usePasswordResetDetails } from "./api";
import { AuthCard } from "./AuthCard";
import { takeLinkTokenFromUrl } from "./linkToken";
import { NewPasswordForm } from "./NewPasswordForm";

/** Landing page for the link in the password-reset email (HIMS-IAM-004). */
export function ResetPasswordPage() {
  const [token] = useState(takeLinkTokenFromUrl);
  const details = usePasswordResetDetails(token);
  const confirm = useConfirmPasswordReset();

  return (
    <AuthCard title="Choose a new password">
      {confirm.isSuccess ? (
        <>
          <Alert severity="success">
            Your password was changed. For your safety, every device that was signed in has been
            signed out.
          </Alert>
          <Button component={RouterLink} to="/login" variant="contained">
            Sign in with your new password
          </Button>
        </>
      ) : (
        <>
          {details.isPending && token && (
            <Box sx={{ display: "grid", placeItems: "center", py: 3 }}>
              <CircularProgress aria-label="Checking your link" />
            </Box>
          )}

          {(!token || details.isError) && (
            <>
              {details.error ? (
                <ErrorAlert error={details.error} />
              ) : (
                <Alert severity="error">This page needs the full link from your email.</Alert>
              )}
              <Button component={RouterLink} to="/forgot-password" variant="outlined">
                Request a new link
              </Button>
            </>
          )}

          {details.data && token && (
            <NewPasswordForm
              intro={
                <Typography>
                  Choose a new password for <strong>{details.data.email}</strong>.
                </Typography>
              }
              submitLabel="Change password"
              pending={confirm.isPending}
              error={confirm.error}
              onSubmit={(password) => confirm.mutate({ token, password })}
            />
          )}
        </>
      )}
    </AuthCard>
  );
}
