import { Alert, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { Account } from "../../api/types";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { type AccountAction, useAccountAction, useCreateAccount } from "./api";

export function AddAccountDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const create = useCreateAccount(useState(() => crypto.randomUUID())[0]);
  const [values, setValues] = useState({ display_name: "", email: "", reason: "" });
  const errors = fieldErrors(create.error);
  const set = (name: keyof typeof values, value: string) =>
    setValues((current) => ({ ...current, [name]: value }));

  return (
    <FormDialog
      title="Add account (not staff)"
      error={create.error}
      fields={Object.keys(values)}
      submitLabel="Add and send invitation"
      submitDisabled={!values.display_name.trim() || !values.email.trim() || !values.reason.trim()}
      pending={create.isPending}
      onClose={onClose}
      onSubmit={() =>
        create.mutate(values, { onSuccess: (account) => navigate(`/accounts/${account.id}`) })
      }
    >
      <Typography variant="body2">
        For people who need to sign in but are not on the staff list, e.g. an external auditor or
        IT support. Staff get their account from the Staff page instead.
      </Typography>
      <TextField
        label="Full name"
        required
        value={values.display_name}
        onChange={(e) => set("display_name", e.target.value)}
        error={!!errors.display_name}
        helperText={errors.display_name}
      />
      <TextField
        label="Email"
        type="email"
        required
        value={values.email}
        onChange={(e) => set("email", e.target.value)}
        error={!!errors.email}
        helperText={errors.email ?? "The invitation to choose a password is sent here."}
      />
      <TextField
        label="Reason"
        required
        value={values.reason}
        onChange={(e) => set("reason", e.target.value)}
        error={!!errors.reason}
        helperText={errors.reason ?? "e.g. External auditor for FY 26-27. Kept in the audit log."}
      />
      <Alert severity="info">
        The account has no access until you give it a role on its page.
      </Alert>
    </FormDialog>
  );
}

const ACTION_TEXT: Record<
  AccountAction,
  { title: string; button: string; body: string; reason: boolean; danger?: boolean }
> = {
  deactivate: {
    title: "Switch account off",
    button: "Switch off",
    body: "The person is signed out everywhere and cannot sign in until the account is switched on again.",
    reason: true,
    danger: true,
  },
  reactivate: {
    title: "Switch account back on",
    button: "Switch on",
    body: "The person can sign in again with their roles as they are now.",
    reason: true,
  },
  invitation: {
    title: "Send invitation",
    button: "Send",
    body: "Emails a link to choose a password. Any earlier link stops working.",
    reason: false,
  },
  "reset-two-factor": {
    title: "Reset two-factor (lost phone)",
    button: "Reset",
    body: "Removes the authenticator and signs the person out everywhere. They set it up again at their next sign-in.",
    reason: false,
    danger: true,
  },
  "sign-out-everywhere": {
    title: "Sign out of all devices",
    button: "Sign out",
    body: "Ends every open session of this person (e.g. a lost laptop).",
    reason: false,
  },
};

export function AccountActionDialog({
  account,
  action,
  onClose,
}: {
  account: Account;
  action: AccountAction;
  onClose: () => void;
}) {
  const run = useAccountAction(account.id, action);
  const [reason, setReason] = useState("");
  const text = ACTION_TEXT[action];
  return (
    <FormDialog
      title={`${text.title} · ${account.display_name}`}
      error={run.error}
      fields={["reason"]}
      submitLabel={text.button}
      submitColor={text.danger ? "error" : "primary"}
      submitDisabled={text.reason && !reason.trim()}
      pending={run.isPending}
      onClose={onClose}
      maxWidth="xs"
      onSubmit={() =>
        run.mutate(text.reason ? { reason: reason.trim() } : {}, { onSuccess: onClose })
      }
    >
      <Typography variant="body2">{text.body}</Typography>
      {text.reason && (
        <TextField
          label="Reason"
          required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          helperText="Kept in the audit log."
        />
      )}
    </FormDialog>
  );
}
