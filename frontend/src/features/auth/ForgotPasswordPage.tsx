import { zodResolver } from "@hookform/resolvers/zod";
import { Alert, Button, Link, Stack, TextField, Typography } from "@mui/material";
import { useForm } from "react-hook-form";
import { Link as RouterLink } from "react-router-dom";
import { z } from "zod";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useRequestPasswordReset } from "./api";
import { AuthCard } from "./AuthCard";

const schema = z.object({ email: z.email("Enter a valid email address") });
type FormValues = z.infer<typeof schema>;

/** "Forgot password?" (HIMS-IAM-004). The answer never reveals whether an account exists. */
export function ForgotPasswordPage() {
  const request = useRequestPasswordReset();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  return (
    <AuthCard title="Reset your password">
      {request.data ? (
        <Alert severity="success">{request.data.detail}</Alert>
      ) : (
        <form onSubmit={handleSubmit((values) => request.mutate(values))} noValidate>
          <Stack spacing={2}>
            <Typography>
              Enter the email you use to sign in. If it belongs to an active account, we'll email
              you a link to choose a new password.
            </Typography>
            {request.error && <ErrorAlert error={request.error} />}
            <TextField
              label="Email"
              type="email"
              autoComplete="username"
              autoFocus
              error={!!errors.email}
              helperText={errors.email?.message}
              {...register("email")}
            />
            <Button type="submit" variant="contained" disabled={request.isPending}>
              Send reset link
            </Button>
          </Stack>
        </form>
      )}
      <Link component={RouterLink} to="/login" variant="body2">
        Back to sign in
      </Link>
    </AuthCard>
  );
}
