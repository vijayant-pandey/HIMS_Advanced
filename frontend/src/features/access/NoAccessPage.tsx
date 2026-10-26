import { Alert, Box, Button, Paper, Stack, Typography } from "@mui/material";
import { useEffect, useRef } from "react";

import { useCurrentUser, useReportNoAccess } from "../auth/api";

/**
 * Shown to signed-in users who hold no role yet (HIMS-UI-002), instead of a red
 * "Permission denied". The visit is recorded in the audit log as `access.none_assigned`; the
 * reference shown here is that event's request ID, so an administrator can find it.
 */
export function NoAccessPage() {
  const { data: user, refetch, isFetching } = useCurrentUser();
  const report = useReportNoAccess();
  const reported = useRef(false);

  useEffect(() => {
    // Once per visit (React StrictMode runs effects twice in development).
    if (reported.current) return;
    reported.current = true;
    report.mutate({ page: window.location.pathname });
  }, [report]);

  return (
    <Box sx={{ display: "grid", placeItems: "center", py: 6 }}>
      <Paper sx={{ p: 4, maxWidth: 520, width: "100%" }}>
        <Stack spacing={2}>
          <Typography variant="h5" component="h1">
            Welcome{user ? `, ${user.display_name}` : ""}
          </Typography>
          <Typography>
            Your account is active, but you don't have access to any area of HIMS yet.
          </Typography>
          <Alert severity="info">
            Please ask your hospital administrator to assign you a role. Give them the reference
            below so they can find this request in the audit log.
          </Alert>
          <Box
            sx={{
              border: 1,
              borderColor: "divider",
              borderRadius: 1,
              px: 1.5,
              py: 1,
              bgcolor: "background.default",
            }}
          >
            <Typography variant="caption" color="text.secondary" component="div">
              Reference
            </Typography>
            <Typography variant="body2" sx={{ fontFamily: "monospace" }} data-testid="reference">
              {report.data?.reference ?? (report.isError ? "Not available" : "Recording…")}
            </Typography>
          </Box>
          <Box>
            <Button variant="contained" onClick={() => refetch()} disabled={isFetching}>
              I've been given access, check again
            </Button>
          </Box>
        </Stack>
      </Paper>
    </Box>
  );
}
