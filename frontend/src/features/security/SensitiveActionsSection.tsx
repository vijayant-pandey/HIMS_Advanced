import { Alert, Button, Paper, Stack, Typography } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useEndIdentityConfirmation, useIdentityConfirmation, confirmIdentityKey } from "../auth/api";
import { useEnsureConfirmed } from "../auth/ConfirmIdentity";

const time = new Intl.DateTimeFormat(undefined, { timeStyle: "short" });

/** "Confirm it's you": when it is asked for, whether it is in force now, and a way to end it. */
export function SensitiveActionsSection() {
  const status = useIdentityConfirmation();
  const end = useEndIdentityConfirmation();
  const ensure = useEnsureConfirmed();
  const queryClient = useQueryClient();
  if (status.error) return <ErrorAlert error={status.error} />;
  if (!status.data) return null;
  const { enabled, confirmed_until: until, window_minutes: minutes } = status.data;
  return (
    <Paper sx={{ p: 3, mt: 2 }}>
      <Stack spacing={2}>
        <Typography variant="h6" component="h2">
          Sensitive actions
        </Typography>
        {!enabled ? (
          <Alert severity="warning">
            Your hospital has turned this off, so sensitive actions do not ask you to confirm it's you. An administrator
            can turn it on under Features.
          </Alert>
        ) : (
          <>
            <Typography variant="body2">
              You are asked for your password, and your authenticator code if you use one, before changing roles or
              cover, switching an account on or off, resetting someone's two-factor or signing them out, suspending or
              terminating staff, deciding access reviews, changing Features, and downloading the audit log or an access
              review. Once you confirm, you are not asked again for {minutes} minutes.
            </Typography>
            {until ? (
              <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
                <Typography variant="body2">
                  <strong>Confirmed until {time.format(new Date(until))}.</strong>
                </Typography>
                <Button disabled={end.isPending} onClick={() => end.mutate()}>
                  End now
                </Button>
              </Stack>
            ) : (
              <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
                <Typography variant="body2">
                  <strong>Not confirmed.</strong> You will be asked at the next sensitive action.
                </Typography>
                <Button
                  onClick={() => {
                    void ensure().finally(() => queryClient.invalidateQueries({ queryKey: confirmIdentityKey }));
                  }}
                >
                  Confirm now
                </Button>
              </Stack>
            )}
          </>
        )}
        {end.error && <ErrorAlert error={end.error} />}
      </Stack>
    </Paper>
  );
}
