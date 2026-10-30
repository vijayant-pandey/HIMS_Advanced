import { Alert, Box, Button, Stack, Typography } from "@mui/material";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

/** A screen file that cannot be downloaded: usually HIMS was updated while the tab was open. */
export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return /dynamically imported module|Importing a module script failed|ChunkLoadError|Failed to fetch/i.test(
    message,
  );
}

/**
 * Shown instead of a blank page when a screen fails to load or crashes (HIMS-PLAT-015).
 * No technical details or data are shown; the console keeps them for developers.
 */
export function RouteErrorPage() {
  const error = useRouteError();
  const updated = isChunkLoadError(error);
  const notFound = isRouteErrorResponse(error) && error.status === 404;

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={2} sx={{ maxWidth: 560 }}>
        <Typography variant="h5" component="h1">
          {updated ? "HIMS was updated" : notFound ? "Page not found" : "Something went wrong"}
        </Typography>
        <Alert severity={updated ? "info" : "error"}>
          {updated
            ? "A newer version of HIMS is available. Reload the page to continue; nothing you saved is lost."
            : notFound
              ? "This page does not exist."
              : "This screen could not be shown. Reload the page. If it happens again, tell your administrator what you were doing."}
        </Alert>
        <Stack direction="row" spacing={1}>
          <Button variant="contained" onClick={() => window.location.reload()}>
            Reload
          </Button>
          <Button href="/">Go to the home page</Button>
        </Stack>
      </Stack>
    </Box>
  );
}
