import { zodResolver } from "@hookform/resolvers/zod";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { z } from "zod";

import { ApiError } from "../../api/client";
import { ErrorAlert } from "../../components/ErrorAlert";
import { ThemePicker } from "../../components/ThemePicker";
import { useAcceptInvitation, useInvitationDetails } from "./api";
import { takeInvitationTokenFromUrl } from "./invitationToken";

const schema = z
  .object({
    password: z.string().min(12, "Use at least 12 characters"),
    confirm: z.string(),
  })
  .refine((values) => values.password === values.confirm, {
    path: ["confirm"],
    message: "Passwords do not match",
  });
type FormValues = z.infer<typeof schema>;

/** Landing page for the activation link in the invitation email (HIMS-IAM-003). */
export function ActivatePage() {
  const navigate = useNavigate();
  const [token] = useState(takeInvitationTokenFromUrl);
  const details = useInvitationDetails(token);
  const accept = useAcceptInvitation();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(({ password }) => {
    if (!token) return;
    accept.mutate(
      { token, password },
      {
        onSuccess: () => navigate("/", { replace: true }),
        onError: (error) => {
          // Server-side password rules (e.g. "too common") come back per field.
          const problem = error instanceof ApiError ? error.problem : null;
          const message = problem?.errors?.find((e) => e.field === "password")?.message;
          if (message) setError("password", { message });
        },
      },
    );
  });

  const invalidLink = !token || details.isError;

  return (
    <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh", px: 2 }}>
      <Box sx={{ position: "fixed", top: 16, right: 16 }}>
        <ThemePicker />
      </Box>
      <Paper sx={{ p: 4, width: "100%", maxWidth: 440 }}>
        <Stack spacing={2}>
          <Typography variant="h5" component="h1">
            Activate your account
          </Typography>

          {details.isPending && token && (
            <Box sx={{ display: "grid", placeItems: "center", py: 3 }}>
              <CircularProgress aria-label="Checking your link" />
            </Box>
          )}

          {invalidLink && (
            <>
              {details.error ? (
                <ErrorAlert error={details.error} />
              ) : (
                <Alert severity="error">
                  This page needs the full link from your invitation email.
                </Alert>
              )}
              <Button component={RouterLink} to="/login" variant="outlined">
                Go to sign in
              </Button>
            </>
          )}

          {details.data && (
            <Box component="form" onSubmit={onSubmit} noValidate>
              <Stack spacing={2}>
                <Typography>
                  Welcome, <strong>{details.data.display_name}</strong>. Choose a password for{" "}
                  <strong>{details.data.email}</strong> at {details.data.organization_name}.
                </Typography>
                {accept.error && !accept.error.problem.errors && (
                  <ErrorAlert error={accept.error} />
                )}
                <TextField
                  label="New password"
                  type="password"
                  autoComplete="new-password"
                  autoFocus
                  error={!!errors.password}
                  helperText={
                    errors.password?.message ??
                    "At least 12 characters. Avoid common words and your name."
                  }
                  {...register("password")}
                />
                <TextField
                  label="Confirm password"
                  type="password"
                  autoComplete="new-password"
                  error={!!errors.confirm}
                  helperText={errors.confirm?.message}
                  {...register("confirm")}
                />
                <Button
                  type="submit"
                  variant="contained"
                  size="large"
                  disabled={accept.isPending}
                >
                  Activate and sign in
                </Button>
              </Stack>
            </Box>
          )}
        </Stack>
      </Paper>
    </Box>
  );
}
