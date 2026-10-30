import { Paper, Stack, Typography } from "@mui/material";

import { useCurrentUser } from "../auth/api";
import { CoverStatusChip, LentAccessList, formatWhen } from "./CoverPage";
import { useMyCover } from "./delegationsApi";

/** Security page: cover arrangements the person is part of (HIMS-IAM-017). Hidden when none. */
export function MyCoverSection() {
  const { data: me } = useCurrentUser();
  const { data } = useMyCover();
  const rows = Array.isArray(data) ? data : [];
  if (rows.length === 0) return null;

  return (
    <Paper sx={{ p: 3, mt: 3 }}>
      <Stack spacing={2}>
        <Typography variant="h6" component="h2">
          Cover arrangements
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Access lent between you and a colleague for a limited time. Everything is recorded under the name of the
          person who does it. If something here is unexpected, tell your hospital administrator.
        </Typography>
        {rows.map((cover) => {
          const covering = cover.delegate.id === me?.id;
          return (
            <Stack key={cover.id} spacing={0.5}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                <Typography variant="body1">
                  {covering
                    ? `You cover for ${cover.delegator.display_name}`
                    : `${cover.delegate.display_name} covers for you`}
                </Typography>
                <CoverStatusChip cover={cover} />
              </Stack>
              <Typography variant="body2">
                {formatWhen(cover.starts_at)} to {formatWhen(cover.ends_at)} · {cover.reason}
              </Typography>
              <LentAccessList cover={cover} />
            </Stack>
          );
        })}
      </Stack>
    </Paper>
  );
}
