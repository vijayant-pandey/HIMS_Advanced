import { zodResolver } from "@hookform/resolvers/zod";
import { Box, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser, useLogin } from "./api";

const schema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: user } = useCurrentUser();
  const login = useLogin();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const redirectTo = (location.state as { from?: string } | null)?.from ?? "/";
  if (user) return <Navigate to={redirectTo} replace />;

  const onSubmit = handleSubmit((values) =>
    login.mutate(values, { onSuccess: () => navigate(redirectTo, { replace: true }) }),
  );

  return (
    <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh", px: 2 }}>
      <Paper component="form" onSubmit={onSubmit} noValidate sx={{ p: 4, width: "100%", maxWidth: 400 }}>
        <Stack spacing={2}>
          <Typography variant="h5" component="h1">
            Sign in to HIMS
          </Typography>
          {login.error && <ErrorAlert error={login.error} />}
          <TextField
            label="Email"
            type="email"
            autoComplete="username"
            autoFocus
            error={!!errors.email}
            helperText={errors.email?.message}
            {...register("email")}
          />
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            error={!!errors.password}
            helperText={errors.password?.message}
            {...register("password")}
          />
          <Button type="submit" variant="contained" size="large" disabled={login.isPending}>
            Sign in
          </Button>
        </Stack>
      </Paper>
    </Box>
  );
}
