import { Box, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { API_BASE, ApiError, api } from "../api/client";
import type { Letterhead as LetterheadData } from "../api/types";

export const letterheadKey = ["letterhead"] as const;

/** For controls on a page that is printed: buttons, filters and so on stay off the paper. */
export const HIDE_WHEN_PRINTING = { "@media print": { display: "none" } };
const ONLY_WHEN_PRINTING = { display: "none", "@media print": { display: "block" } };

export function useLetterhead() {
  return useQuery<LetterheadData, ApiError>({
    queryKey: letterheadKey,
    queryFn: ({ signal }) => api.get<LetterheadData>("/organization/letterhead/", { signal }),
    staleTime: 5 * 60_000,
  });
}

/** The hospital's name, logo and details as they appear on paper (HIMS-ORG-006; spec 4.1). */
export function LetterheadView({ letterhead, title }: { letterhead: LetterheadData; title?: string }) {
  return (
    <Box>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", borderBottom: 2, borderColor: "divider", pb: 1 }}>
        {letterhead.has_logo && (
          // The hospital's name is next to it, so screen readers do not need the picture described.
          <img
            src={`${API_BASE}/organization/logo/?v=${letterhead.version}`}
            alt=""
            style={{ maxHeight: 72, maxWidth: 240 }}
          />
        )}
        <Box>
          <Typography variant="h6" component="p">
            {letterhead.display_name}
          </Typography>
          {letterhead.lines.map((line) => (
            <Typography key={line} variant="caption" component="p">
              {line}
            </Typography>
          ))}
        </Box>
      </Stack>
      {title && (
        <Typography variant="subtitle1" component="p" sx={{ mt: 1 }}>
          {title}
        </Typography>
      )}
    </Box>
  );
}

/** Goes at the top of a page that can be printed: nothing on screen, the letterhead on paper. */
export function PrintLetterhead({ title }: { title: string }) {
  const { data } = useLetterhead();
  if (!data) return null;
  return (
    <Box data-testid="print-letterhead" sx={ONLY_WHEN_PRINTING}>
      <LetterheadView letterhead={data} title={title} />
    </Box>
  );
}
