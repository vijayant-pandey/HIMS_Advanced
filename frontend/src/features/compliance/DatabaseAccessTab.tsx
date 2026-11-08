import { Alert, Box, Chip, LinearProgress, List, ListItem, ListItemIcon, ListItemText, Paper, Stack, Typography } from "@mui/material";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useDatabaseAccess } from "./api";

/** Database access (HIMS-OPS-007): the app runs with its own limited database user. Read-only by design: the
 * users and their rights are changed only by the owner's setup command, never from the app itself. */
export function DatabaseAccessTab() {
  const { data, error, isLoading } = useDatabaseAccess();
  return (
    <Stack spacing={2}>
      <Typography variant="body2">
        The app talks to the database with its own limited user. It can read and write records, but it cannot change
        the database's structure, and it can never change, delete or empty the audit log and other evidence, even if
        someone took over the app. Only the separate owner user (used for updates) can, and a read-only user for reports
        never sees passwords or two-factor secrets. These checks are read from the database itself.
      </Typography>
      {isLoading && <LinearProgress />}
      {error && <ErrorAlert error={error} />}
      {data && (
        <>
          {data.separated ? (
            <Alert severity="success">Database access is separated: every check passed.</Alert>
          ) : !data.set_up && data.developer_pc ? (
            <Alert severity="info">
              Not set up on this computer yet. The app still works, but it uses the owner's rights. To set it up, stop
              HIMS and run <code>python manage.py setup_database_roles --write-env</code> in the backend folder (see the
              guide “Separate database users”).
            </Alert>
          ) : (
            <Alert severity="error">
              The app's database user has more rights than it needs. Treat this as a security finding: run the setup
              command with the owner's credentials and check again.
            </Alert>
          )}
          <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: 1 }}>
            <Typography component="dt" variant="body2" color="text.secondary">
              App connects as
            </Typography>
            <Typography component="dd" variant="body2" sx={{ m: 0 }}>
              {data.connected_as}
            </Typography>
            <Typography component="dt" variant="body2" color="text.secondary">
              Users for this hospital
            </Typography>
            <Typography component="dd" variant="body2" sx={{ m: 0 }}>
              {data.app_user} (app) · {data.readonly_user} (read-only reports) · {data.breakglass_user} (break-glass,
              emergencies only)
            </Typography>
          </Box>
          <Paper>
            <List aria-label="Database access checks" dense>
              {data.checks.map((check) => (
                <ListItem key={check.key}>
                  <ListItemIcon sx={{ minWidth: 72 }}>
                    <Chip size="small" color={check.passed ? "success" : "error"} label={check.passed ? "OK" : "Failed"} />
                  </ListItemIcon>
                  <ListItemText primary={check.label} secondary={check.detail || undefined} />
                </ListItem>
              ))}
            </List>
          </Paper>
        </>
      )}
    </Stack>
  );
}
