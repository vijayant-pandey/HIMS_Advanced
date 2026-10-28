import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  LinearProgress,
  Link,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { UserAccessPanel } from "../accessControl/UserAccessPanel";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { AccountActionDialog } from "./AccountDialogs";
import { accountState } from "./AccountsPage";
import { type AccountAction, useAccount } from "./api";

export function AccountDetailPage() {
  const { id } = useParams();
  const { data: me } = useCurrentUser();
  const { data: account, isPending, error } = useAccount(id);
  const [action, setAction] = useState<AccountAction>();
  // Hint only: the API checks accounts.manage and the safety rules.
  const canManage = hasOrganizationWidePermission(me, "accounts.manage");

  if (isPending) return <LinearProgress />;
  if (error || !account) return <ErrorAlert error={error} />;
  const isSelf = me?.id === account.id;
  const isStaff = !!account.staff_member_id;
  const state = accountState(account);
  const button = (name: AccountAction, label: string, show: boolean, color: "primary" | "error" = "primary") =>
    show && (
      <Button size="small" variant="outlined" color={color} onClick={() => setAction(name)}>
        {label}
      </Button>
    );

  return (
    <Stack spacing={2}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/accounts" underline="hover">
          Accounts
        </Link>
        <Typography>{account.display_name}</Typography>
      </Breadcrumbs>
      <Box>
        <Typography variant="h5" component="h1">
          {account.display_name}
        </Typography>
        <Stack direction="row" spacing={1} sx={{ mt: 0.5, alignItems: "center" }}>
          <Typography variant="body2">
            {account.email} · {isStaff ? "Staff" : "Not staff"} · two-factor{" "}
            {account.two_factor_enabled ? "on" : "off"} · last sign-in{" "}
            {account.last_login ? new Date(account.last_login).toLocaleString() : "never"}
          </Typography>
          <Chip size="small" color={state.color} label={state.label} />
        </Stack>
      </Box>

      {isStaff && (
        <Alert severity="info">
          This account belongs to a staff member, so it follows their employment status (suspended
          or terminated staff cannot sign in).{" "}
          <Link component={RouterLink} to={`/staff/${account.staff_member_id}`}>
            Open their staff page
          </Link>
        </Alert>
      )}
      {isSelf && (
        <Alert severity="info">
          This is your own account. Another administrator has to change it.
        </Alert>
      )}
      {canManage && !isSelf && (
        <Paper sx={{ p: 1.5 }}>
          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", rowGap: 1 }}>
            {button(
              "invitation",
              account.invitation_expires_at ? "Resend invitation" : "Send invitation",
              account.is_active && !account.activated,
            )}
            {button("reset-two-factor", "Reset two-factor", account.two_factor_enabled, "error")}
            {button("sign-out-everywhere", "Sign out of all devices", account.is_active)}
            {button("deactivate", "Switch account off", !isStaff && account.is_active, "error")}
            {button("reactivate", "Switch account on", !isStaff && !account.is_active)}
          </Stack>
        </Paper>
      )}

      <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
        Access to HIMS
      </Typography>
      <UserAccessPanel userId={account.id} personName={account.display_name} />

      {action && (
        <AccountActionDialog account={account} action={action} onClose={() => setAction(undefined)} />
      )}
    </Stack>
  );
}
