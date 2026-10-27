import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Link, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, Link as RouterLink, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { ErrorAlert } from "../../components/ErrorAlert";
import { FEATURE, useFeatureOn } from "../featureFlags/api";
import { isMfaChallenge, useCurrentUser, useLogin, useVerifyLogin } from "./api";
import { AuthCard } from "./AuthCard";

const schema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
type FormValues = z.infer<typeof schema>;

/** Step 2 of sign-in for accounts with two-factor on (HIMS-IAM-005). */
function CodeStep({ onDone, onRestart }: { onDone: () => void; onRestart: () => void }) {
  const verify = useVerifyLogin();
  const [useBackup, setUseBackup] = useState(false);
  const [code, setCode] = useState("");
  const expired = verify.error?.code === "MFA_CHALLENGE_EXPIRED";

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        verify.mutate({ code }, { onSuccess: onDone });
      }}
    >
      <Stack spacing={2}>
        <Typography>
          {useBackup
            ? "Enter one of your backup codes (each works once)."
            : "Open your authenticator app and enter the 6-digit code for HIMS."}
        </Typography>
        {verify.error && <ErrorAlert error={verify.error} />}
        {expired ? (
          <Button variant="contained" onClick={onRestart}>
            Start again
          </Button>
        ) : (
          <>
            <TextField
              label={useBackup ? "Backup code" : "Authentication code"}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              autoFocus
              autoComplete="one-time-code"
              slotProps={{
                htmlInput: useBackup
                  ? { maxLength: 11 }
                  : { inputMode: "numeric", pattern: "[0-9]*", maxLength: 6 },
              }}
            />
            <Button type="submit" variant="contained" disabled={verify.isPending || !code.trim()}>
              Verify and sign in
            </Button>
          </>
        )}
        <Stack direction="row" sx={{ justifyContent: "space-between" }}>
          <Link component="button" type="button" variant="body2" onClick={() => setUseBackup(!useBackup)}>
            {useBackup ? "Use the authenticator app" : "Lost your phone? Use a backup code"}
          </Link>
          <Link component="button" type="button" variant="body2" onClick={onRestart}>
            Back
          </Link>
        </Stack>
      </Stack>
    </form>
  );
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: user } = useCurrentUser();
  const login = useLogin();
  // The hospital may turn self-service resets off (Features page); the server enforces it too.
  const selfServiceReset = useFeatureOn(FEATURE.selfServicePasswordReset);
  const [needsCode, setNeedsCode] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const redirectTo = (location.state as { from?: string } | null)?.from ?? "/";
  if (user) return <Navigate to={redirectTo} replace />;

  const done = () => navigate(redirectTo, { replace: true });
  const onSubmit = handleSubmit((values) =>
    login.mutate(values, {
      onSuccess: (result) => (isMfaChallenge(result) ? setNeedsCode(true) : done()),
    }),
  );

  if (needsCode) {
    return (
      <AuthCard title="Two-factor sign-in">
        <CodeStep
          onDone={done}
          onRestart={() => {
            login.reset();
            setNeedsCode(false);
          }}
        />
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Sign in to HIMS">
      <form onSubmit={onSubmit} noValidate>
        <Stack spacing={2}>
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
          <Button type="submit" variant="contained" disabled={login.isPending}>
            Sign in
          </Button>
          {selfServiceReset && (
            <Link component={RouterLink} to="/forgot-password" variant="body2" sx={{ alignSelf: "center" }}>
              Forgot password?
            </Link>
          )}
        </Stack>
      </form>
    </AuthCard>
  );
}
