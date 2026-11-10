import { Button, type ButtonProps, TextField, Typography } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ApiError, api, isUnauthenticated, setIdentityConfirmer } from "../../api/client";
import type { ConfirmIdentityStatus } from "../../api/types";
import { FormDialog } from "../../components/FormDialog";
import { confirmIdentityKey, useCurrentUser, useIdentityConfirmation } from "./api";
import { answerWithPasskey, passkeyErrorText, passkeysSupported } from "./webauthn";

function ConfirmIdentityDialog({ onDone }: { onDone: (confirmed: boolean) => void }) {
  const { data: user } = useCurrentUser();
  const { data: status } = useIdentityConfirmation();
  const queryClient = useQueryClient();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const needsCode = status?.needs_code ?? user?.mfa.enabled ?? false;
  const canUsePasskey = needsCode && !!status?.passkey_available && passkeysSupported();
  const [passkeyProblem, setPasskeyProblem] = useState<string | null>(null);
  const confirm = useMutation<ConfirmIdentityStatus, ApiError, { withPasskey?: boolean } | void>({
    mutationFn: async (how) => {
      if (how && how.withPasskey) {
        const options = await api.post<{ public_key: Record<string, unknown> }>("/auth/confirm-identity/passkey-options/");
        let passkey: Record<string, unknown>;
        try {
          passkey = await answerWithPasskey(options.public_key);
        } catch (error) {
          setPasskeyProblem(passkeyErrorText(error) ?? "The passkey could not be used.");
          throw error;
        }
        return api.post<ConfirmIdentityStatus>("/auth/confirm-identity/", { password, passkey });
      }
      return api.post<ConfirmIdentityStatus>("/auth/confirm-identity/", { password, code });
    },
    onSuccess: (result) => {
      queryClient.setQueryData(confirmIdentityKey, result);
      onDone(true);
    },
    onError: (error) => {
      setCode(""); // a used or wrong code is no good for the next try
      if (isUnauthenticated(error)) onDone(false); // too many wrong tries: back to sign-in
    },
    onMutate: () => setPasskeyProblem(null),
  });
  return (
    <FormDialog
      title="Confirm it's you"
      error={confirm.error instanceof ApiError ? confirm.error : null}
      fields={["password", "code"]}
      submitLabel="Confirm"
      submitDisabled={!password || (needsCode && !code)}
      pending={confirm.isPending}
      onSubmit={() => confirm.mutate()}
      onClose={() => onDone(false)}
      maxWidth="xs"
    >
      <Typography variant="body2">
        This is a sensitive action. Enter your password{needsCode ? " and the code from your authenticator app" : ""} to
        continue.
        {status ? ` You won't be asked again for ${status.window_minutes} minutes.` : ""}
      </Typography>
      <TextField
        label="Your password"
        type="password"
        autoComplete="current-password"
        autoFocus
        value={password}
        onChange={(event) => setPassword(event.target.value)}
      />
      {passkeyProblem && <Typography variant="body2" color="warning.main">{passkeyProblem}</Typography>}
      {canUsePasskey && (
        <Button
          variant="outlined"
          disabled={!password || confirm.isPending}
          onClick={() => confirm.mutate({ withPasskey: true })}
        >
          Confirm with a passkey instead of the code
        </Button>
      )}
      {needsCode && (
        <TextField
          label="Authenticator code"
          helperText="A backup code also works."
          autoComplete="one-time-code"
          slotProps={{ htmlInput: { inputMode: "numeric", maxLength: 32 } }}
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />
      )}
    </FormDialog>
  );
}

const EnsureConfirmed = createContext<() => Promise<boolean>>(async () => true);

/** Resolves true once the person is confirmed, asking them first if needed. */
export const useEnsureConfirmed = () => useContext(EnsureConfirmed);

/**
 * Sensitive requests refused with REAUTH_REQUIRED open this dialog from anywhere in the app, and the
 * API client then repeats the request (HIMS-IAM-007), so no screen needs its own handling.
 */
export function ConfirmIdentityProvider({ children }: { children: ReactNode }) {
  const [asking, setAsking] = useState(false);
  const waiting = useRef<{ promise: Promise<boolean>; resolve: (confirmed: boolean) => void } | null>(null);

  const ask = useCallback(() => {
    if (waiting.current) return waiting.current.promise; // several requests share one dialog
    let resolve: (confirmed: boolean) => void = () => {};
    const promise = new Promise<boolean>((done) => {
      resolve = done;
    });
    waiting.current = { promise, resolve };
    setAsking(true);
    return promise;
  }, []);

  const finish = useCallback((confirmed: boolean) => {
    waiting.current?.resolve(confirmed);
    waiting.current = null;
    setAsking(false);
  }, []);

  useEffect(() => {
    setIdentityConfirmer(ask);
    return () => setIdentityConfirmer(null);
  }, [ask]);

  const ensure = useMemo(
    () => async () => {
      const status = await api.get<ConfirmIdentityStatus>("/auth/confirm-identity/");
      return status.confirmed || ask();
    },
    [ask],
  );

  return (
    <EnsureConfirmed.Provider value={ensure}>
      {children}
      {asking && <ConfirmIdentityDialog onDone={finish} />}
    </EnsureConfirmed.Provider>
  );
}

/**
 * A download link for a sensitive export. A plain link cannot react to the server's refusal, so this
 * confirms first and then follows the link. If the check itself fails, the server still decides.
 */
export function ConfirmedDownloadButton({
  href,
  children,
  variant,
  size,
}: {
  href: string;
  children: ReactNode;
  variant?: ButtonProps["variant"];
  size?: ButtonProps["size"];
}) {
  const ensure = useEnsureConfirmed();
  return (
    <Button
      component="a"
      href={href}
      variant={variant}
      size={size}
      onClick={(event: React.MouseEvent) => {
        event.preventDefault();
        ensure()
          .catch(() => true)
          .then((go) => {
            if (go) window.location.assign(href);
          });
      }}
    >
      {children}
    </Button>
  );
}
