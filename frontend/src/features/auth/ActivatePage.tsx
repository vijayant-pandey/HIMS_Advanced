import { Alert, Box, Button, CircularProgress, Typography } from "@mui/material";
import { useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useAcceptInvitation, useInvitationDetails } from "./api";
import { AuthCard } from "./AuthCard";
import { takeLinkTokenFromUrl } from "./linkToken";
import { NewPasswordForm } from "./NewPasswordForm";

/** Landing page for the activation link in the invitation email (HIMS-IAM-003). */
export function ActivatePage() {
  const navigate = useNavigate();
  const [token] = useState(takeLinkTokenFromUrl);
  const details = useInvitationDetails(token);
  const accept = useAcceptInvitation();

  return (
    <AuthCard title="Activate your account">
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
            <Alert severity="error">This page needs the full link from your invitation email.</Alert>
          )}
          <Button component={RouterLink} to="/login" variant="outlined">
            Go to sign in
          </Button>
        </>
      )}

      {details.data && token && (
        <NewPasswordForm
          intro={
            <Typography>
              Welcome, <strong>{details.data.display_name}</strong>. Choose a password for{" "}
              <strong>{details.data.email}</strong> at {details.data.organization_name}.
            </Typography>
          }
          submitLabel="Activate and sign in"
          pending={accept.isPending}
          error={accept.error}
          onSubmit={(password) =>
            accept.mutate({ token, password }, { onSuccess: () => navigate("/", { replace: true }) })
          }
        />
      )}
    </AuthCard>
  );
}
