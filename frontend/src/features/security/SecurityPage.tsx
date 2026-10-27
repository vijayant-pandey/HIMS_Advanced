import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { MfaSetup } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import {
  useConfirmMfaSetup,
  useCurrentUser,
  useDisableMfa,
  useLogout,
  useRegenerateRecoveryCodes,
  useStartMfaSetup,
} from "../auth/api";
import { RecoveryCodes } from "./RecoveryCodes";

function QrCode({ value }: { value: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    QRCode.toDataURL(value, { margin: 1, width: 200 }).then(
      (url) => active && setSrc(url),
      () => active && setSrc(null),
    );
    return () => {
      active = false;
    };
  }, [value]);
  return src ? (
    <Box component="img" src={src} alt="QR code for your authenticator app" sx={{ width: 200, height: 200 }} />
  ) : null;
}

function CodeField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <TextField
      label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      autoComplete="one-time-code"
      slotProps={{ htmlInput: { inputMode: "numeric", pattern: "[0-9]*", maxLength: 6 } }}
      sx={{ maxWidth: 220 }}
    />
  );
}

/** Two-factor setup: scan, confirm, save backup codes (HIMS-IAM-005). */
function SetupFlow() {
  const start = useStartMfaSetup();
  const confirm = useConfirmMfaSetup();
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const navigate = useNavigate();

  if (codes) {
    return <RecoveryCodes codes={codes} onDone={() => navigate("/", { replace: true })} />;
  }

  if (!setup) {
    return (
      <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
        <Typography>
          You need an authenticator app on your phone, such as Google Authenticator, Microsoft
          Authenticator or Authy.
        </Typography>
        {start.error && <ErrorAlert error={start.error} />}
        <Button variant="contained" disabled={start.isPending} onClick={() => start.mutate(undefined, { onSuccess: setSetup })}>
          Set up two-factor sign-in
        </Button>
      </Stack>
    );
  }

  return (
    <Stack spacing={2}>
      <Typography>
        <strong>1.</strong> In your authenticator app, add an account and scan this QR code.
      </Typography>
      <QrCode value={setup.otpauth_uri} />
      <Typography variant="body2" color="text.secondary">
        Can't scan? Enter this key instead:{" "}
        <Box component="span" sx={{ fontFamily: "monospace", wordBreak: "break-all" }} data-testid="manual-key">
          {setup.secret.match(/.{1,4}/g)?.join(" ")}
        </Box>
      </Typography>
      <Typography>
        <strong>2.</strong> Enter the 6-digit code the app shows.
      </Typography>
      {confirm.error && <ErrorAlert error={confirm.error} />}
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          confirm.mutate({ code }, { onSuccess: (data) => setCodes(data.recovery_codes) });
        }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
          <CodeField label="6-digit code" value={code} onChange={setCode} />
          <Button type="submit" variant="contained" disabled={confirm.isPending || code.trim().length < 6} sx={{ mt: "2px" }}>
            Turn on
          </Button>
        </Stack>
      </form>
    </Stack>
  );
}

function ManageEnabled({ required }: { required: boolean }) {
  const regenerate = useRegenerateRecoveryCodes();
  const disable = useDisableMfa();
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);

  if (codes) return <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />;

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        To get new backup codes{required ? "" : " or turn two-factor off"}, enter a current code
        from your authenticator app.
      </Typography>
      {(regenerate.error || disable.error) && <ErrorAlert error={regenerate.error ?? disable.error} />}
      <CodeField label="6-digit code" value={code} onChange={setCode} />
      <Stack direction="row" spacing={1}>
        <Button
          variant="outlined"
          disabled={regenerate.isPending || code.trim().length < 6}
          onClick={() =>
            regenerate.mutate({ code }, { onSuccess: (data) => { setCode(""); setCodes(data.recovery_codes); } })
          }
        >
          Get new backup codes
        </Button>
        {!required && (
          <Button
            color="error"
            variant="outlined"
            disabled={disable.isPending || code.trim().length < 6}
            onClick={() => disable.mutate({ code }, { onSuccess: () => setCode("") })}
          >
            Turn off
          </Button>
        )}
      </Stack>
    </Stack>
  );
}

export function SecurityPage() {
  const { data: user } = useCurrentUser();
  const logout = useLogout();
  const navigate = useNavigate();
  if (!user) return null;
  const { mfa } = user;

  return (
    <Box sx={{ maxWidth: 640 }}>
      <Typography variant="h5" component="h1" sx={{ mb: 2 }}>
        Security
      </Typography>
      <Paper sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Typography variant="h6" component="h2">
              Two-factor sign-in
            </Typography>
            <Chip label={mfa.enabled ? "On" : "Off"} color={mfa.enabled ? "success" : "default"} />
            {mfa.required && <Chip label="Required for your role" variant="outlined" />}
          </Stack>
          <Typography variant="body2" color="text.secondary">
            After your password, HIMS asks for a 6-digit code from an app on your phone. Someone
            who learns your password still cannot sign in.
          </Typography>
          <Divider />
          {mfa.required && !mfa.enabled && (
            <Alert severity="warning">
              Your role can change important hospital settings, so two-factor sign-in is required
              before you can continue.
            </Alert>
          )}
          {mfa.enabled && !mfa.verified ? (
            <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
              <Alert severity="info">
                Two-factor is on for your account, but this session started without it. Sign out
                and sign in again with your code.
              </Alert>
              <Button
                variant="contained"
                onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
              >
                Sign out
              </Button>
            </Stack>
          ) : mfa.enabled ? (
            <>
              <Typography>
                Backup codes left: <strong>{mfa.recovery_codes_remaining}</strong>
              </Typography>
              <ManageEnabled required={mfa.required} />
            </>
          ) : (
            <SetupFlow />
          )}
        </Stack>
      </Paper>
    </Box>
  );
}
