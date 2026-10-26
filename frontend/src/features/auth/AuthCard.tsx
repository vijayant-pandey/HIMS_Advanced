import { Box, Paper, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

import { ThemePicker } from "../../components/ThemePicker";

/** Centered card layout used by the public sign-in, activation and password pages. */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh", px: 2 }}>
      <Box sx={{ position: "fixed", top: 16, right: 16 }}>
        <ThemePicker />
      </Box>
      <Paper sx={{ p: 4, width: "100%", maxWidth: 440 }}>
        <Stack spacing={2}>
          <Typography variant="h5" component="h1">
            {title}
          </Typography>
          {children}
        </Stack>
      </Paper>
    </Box>
  );
}
