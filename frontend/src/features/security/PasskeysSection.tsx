import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useAddPasskey, usePasskeys, useRemovePasskey } from "../auth/api";
import { passkeyErrorText, passkeysSupported } from "../auth/webauthn";

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function Problem({ error }: { error: unknown }) {
  const text = passkeyErrorText(error);
  return text ? <Alert severity="warning">{text}</Alert> : <ErrorAlert error={error} />;
}

/** Passkeys as a second factor (HIMS-IAM-014): added to the authenticator app, not instead of it. */
export function PasskeysSection() {
  const passkeys = usePasskeys();
  const add = useAddPasskey();
  const remove = useRemovePasskey();
  const [name, setName] = useState("");
  const supported = passkeysSupported();

  return (
    <Stack spacing={2}>
      <Divider />
      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
        <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600 }}>
          Passkeys
        </Typography>
        <Chip size="small" label={`${passkeys.data?.length ?? 0} added`} />
      </Stack>
      <Typography variant="body2" color="text.secondary">
        Instead of typing a code, unlock this phone, laptop or security key with your fingerprint, face or PIN. A passkey
        only works on this hospital&apos;s own HIMS address, so a fake sign-in page cannot use it. Your authenticator
        app and backup codes keep working, and the admin console still asks for a code.
      </Typography>
      {passkeys.error && <ErrorAlert error={passkeys.error} />}
      {!!passkeys.data?.length && (
        <List dense aria-label="Your passkeys" disablePadding>
          {passkeys.data.map((passkey) => (
            <ListItem
              key={passkey.id}
              disableGutters
              secondaryAction={
                <Button
                  size="small"
                  color="error"
                  disabled={remove.isPending}
                  aria-label={`Remove passkey ${passkey.name}`}
                  onClick={() => remove.mutate(passkey.id)}
                >
                  Remove
                </Button>
              }
            >
              <ListItemText
                primary={passkey.name}
                secondary={`Added ${when.format(new Date(passkey.created_at))}${
                  passkey.last_used_at ? `, last used ${when.format(new Date(passkey.last_used_at))}` : ", not used yet"
                }${passkey.backed_up ? " · synced to your account" : ""}`}
              />
            </ListItem>
          ))}
        </List>
      )}
      {remove.error && <ErrorAlert error={remove.error} />}
      {supported ? (
        <Box
          component="form"
          onSubmit={(event: React.FormEvent) => {
            event.preventDefault();
            add.mutate(name.trim(), { onSuccess: () => setName("") });
          }}
        >
          <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
            <TextField
              size="small"
              label="Name for this passkey"
              value={name}
              onChange={(event) => setName(event.target.value)}
              helperText='e.g. "Work laptop", so you know which one to remove if it is lost'
              slotProps={{ htmlInput: { maxLength: 60 } }}
            />
            <Button type="submit" variant="outlined" disabled={add.isPending || !name.trim()}>
              Add a passkey
            </Button>
          </Stack>
        </Box>
      ) : (
        <Alert severity="info">This browser cannot use passkeys. Use the code from your authenticator app.</Alert>
      )}
      {add.error ? <Problem error={add.error} /> : null}
      {add.isSuccess && <Alert severity="success">Passkey added. Next time, choose "Use a passkey" after your password.</Alert>}
    </Stack>
  );
}
