import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  LinearProgress,
  Link,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";

import type { AccessReview, AccessReviewItem, AccessReviewItemDecision } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import {
  reviewExportUrl,
  useAccessReview,
  useAccessReviewItems,
  useAccessReviewSchedule,
  useAccessReviews,
  useCancelAccessReview,
  useCompleteAccessReview,
  useDecideAccess,
  useStartAccessReview,
} from "./reviewsApi";

const day = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const formatDate = (value?: string | null) => (value ? day.format(new Date(value)) : "—");

const STATUS: Record<AccessReview["status"], { label: string; color: "info" | "success" | "default" }> = {
  open: { label: "In progress", color: "info" },
  completed: { label: "Completed", color: "success" },
  cancelled: { label: "Cancelled", color: "default" },
};

const DECISIONS: Record<AccessReviewItemDecision, { label: string; color: "warning" | "success" | "error" | "default" }> = {
  pending: { label: "Not reviewed yet", color: "warning" },
  keep: { label: "Keep", color: "success" },
  remove: { label: "Removed", color: "error" },
  ended: { label: "Already ended", color: "default" },
};

function useCanManage() {
  const { data: user } = useCurrentUser();
  return hasOrganizationWidePermission(user, "access.reviews.manage");
}

function progress(review: AccessReview) {
  const s = review.summary;
  const total = (s?.pending ?? 0) + (s?.keep ?? 0) + (s?.remove ?? 0) + (s?.ended ?? 0);
  return { total, decided: total - (s?.pending ?? 0) };
}

function StartDialog({ onClose }: { onClose: () => void }) {
  const start = useStartAccessReview(useState(() => crypto.randomUUID())[0]);
  const month = new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(new Date());
  const [title, setTitle] = useState(`Access review ${month}`);
  const [dueOn, setDueOn] = useState("");
  const errors = fieldErrors(start.error);
  return (
    <FormDialog
      title="Start an access review"
      error={start.error}
      fields={["title", "due_on"]}
      submitLabel="Start review"
      submitDisabled={!title.trim()}
      pending={start.isPending}
      onClose={onClose}
      onSubmit={() =>
        start.mutate({ title: title.trim(), due_on: dueOn || null }, { onSuccess: onClose })
      }
    >
      <Typography variant="body2">
        HIMS lists everyone&apos;s access as it is right now (each person, role and place). You
        and other reviewers then keep or remove each one. Nobody can decide on their own access.
      </Typography>
      <TextField
        label="Name"
        required
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        error={!!errors.title}
        helperText={errors.title}
      />
      <TextField
        label="Finish by"
        type="date"
        value={dueOn}
        onChange={(e) => setDueOn(e.target.value)}
        error={!!errors.due_on}
        helperText={errors.due_on ?? "Leave empty for 14 days from today."}
        slotProps={{ inputLabel: { shrink: true } }}
      />
    </FormDialog>
  );
}

/** HIMS-IAM-012: periodic access reviews (list and schedule). */
export function AccessReviewsPage() {
  const canManage = useCanManage();
  const { data, isPending, error } = useAccessReviews();
  const { data: plan } = useAccessReviewSchedule();
  const [starting, setStarting] = useState(false);
  const reviews = Array.isArray(data) ? data : [];
  const hasOpen = reviews.some((r) => r.status === "open");

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Access reviews
        </Typography>
        <Typography variant="body2">
          Every few months, check who can use HIMS and remove access people no longer need (for
          example after a move to another department). Each review is kept as evidence for
          auditors.
        </Typography>
      </Box>
      {plan && (
        <Alert
          severity={plan.open_review_overdue || plan.review_due ? "warning" : "info"}
          action={
            canManage && !hasOpen ? (
              <Button color="inherit" size="small" onClick={() => setStarting(true)}>
                Start a review
              </Button>
            ) : undefined
          }
        >
          {plan.open_review_overdue
            ? "The review in progress is past its finish-by date. Please finish it."
            : plan.review_due
              ? `A review is due (every ${plan.interval_days} days; due ${formatDate(plan.next_due_on)}).`
              : `Next review due by ${formatDate(plan.next_due_on)} (every ${plan.interval_days} days).`}
          {plan.last_completed_at && ` Last completed ${formatDate(plan.last_completed_at)}.`}
        </Alert>
      )}
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Access reviews">
          <TableHead>
            <TableRow>
              <TableCell>Review</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Started</TableCell>
              <TableCell>Finish by</TableCell>
              <TableCell>Decided</TableCell>
              <TableCell>Removed</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {reviews.map((r) => {
              const { total, decided } = progress(r);
              return (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link component={RouterLink} to={`/access-reviews/${r.id}`}>
                      {r.title}
                    </Link>
                    <Typography variant="caption" component="p">
                      by {r.started_by_name ?? "system"}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={STATUS[r.status]?.label ?? r.status} color={STATUS[r.status]?.color} />
                  </TableCell>
                  <TableCell>{formatDate(r.created_at)}</TableCell>
                  <TableCell>{formatDate(r.due_on)}</TableCell>
                  <TableCell>
                    {decided} of {total}
                  </TableCell>
                  <TableCell>{r.summary?.remove ?? 0}</TableCell>
                </TableRow>
              );
            })}
            {data && reviews.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>No access review has been done yet.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {starting && <StartDialog onClose={() => setStarting(false)} />}
    </Stack>
  );
}

function RemoveDialog({
  reviewId,
  items,
  onClose,
}: {
  reviewId: string;
  items: AccessReviewItem[];
  onClose: () => void;
}) {
  const decide = useDecideAccess(reviewId);
  const [comment, setComment] = useState("");
  const errors = fieldErrors(decide.error);
  return (
    <FormDialog
      title={items.length === 1 ? `Remove access · ${items[0]!.person_name}` : `Remove access for ${items.length} entries`}
      error={decide.error}
      fields={["comment"]}
      submitLabel="Remove access now"
      submitColor="error"
      submitDisabled={!comment.trim()}
      pending={decide.isPending}
      onClose={onClose}
      onSubmit={() =>
        decide.mutate(
          { items: items.map((i) => i.id), decision: "remove", comment: comment.trim() },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        {items.map((i) => `${i.person_name}: ${i.role_name} (${i.scope})`).join("; ")}
      </Typography>
      <Alert severity="warning">The access ends immediately. It can be given again later on the Access page.</Alert>
      <TextField
        label="Why is the access removed?"
        required
        multiline
        minRows={2}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        error={!!errors.comment}
        helperText={errors.comment ?? "Kept with the review and in the audit log."}
      />
    </FormDialog>
  );
}

function CloseDialog({
  review,
  mode,
  onClose,
}: {
  review: AccessReview;
  mode: "complete" | "cancel";
  onClose: () => void;
}) {
  const complete = useCompleteAccessReview(review.id);
  const cancel = useCancelAccessReview(review.id);
  const mutation = mode === "complete" ? complete : cancel;
  const [text, setText] = useState("");
  return (
    <FormDialog
      title={mode === "complete" ? `Complete · ${review.title}` : `Cancel · ${review.title}`}
      error={mutation.error}
      fields={mode === "complete" ? ["notes"] : ["reason"]}
      submitLabel={mode === "complete" ? "Complete review" : "Cancel review"}
      submitColor={mode === "complete" ? "primary" : "error"}
      submitDisabled={mode === "cancel" && !text.trim()}
      pending={mutation.isPending}
      onClose={onClose}
      onSubmit={() =>
        mode === "complete"
          ? complete.mutate({ version: review.version, notes: text.trim() }, { onSuccess: onClose })
          : cancel.mutate({ version: review.version, reason: text.trim() }, { onSuccess: onClose })
      }
    >
      <Typography variant="body2">
        {mode === "complete"
          ? "Completing locks the review. It stays as evidence and can be downloaded."
          : "Decisions already made, including removed access, stay as they are."}
      </Typography>
      <TextField
        label={mode === "complete" ? "Summary (optional)" : "Why is the review cancelled?"}
        required={mode === "cancel"}
        multiline
        minRows={2}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </FormDialog>
  );
}

/** One access review: keep or remove each person's access, then complete it. */
export function AccessReviewDetailPage() {
  const { id = "" } = useParams();
  const canManage = useCanManage();
  const { data: review, error } = useAccessReview(id);
  const [decision, setDecision] = useState("");
  const [search, setSearch] = useState("");
  const items = useAccessReviewItems(id, { decision, search: search.trim() });
  const decide = useDecideAccess(id);
  const [selected, setSelected] = useState<string[]>([]);
  const [removing, setRemoving] = useState<AccessReviewItem[]>();
  const [closing, setClosing] = useState<"complete" | "cancel">();

  if (error) return <ErrorAlert error={error} />;
  if (!review) return <LinearProgress />;

  const open = review.status === "open";
  const rows = Array.isArray(items.data) ? items.data : [];
  const decidable = (i: AccessReviewItem) =>
    canManage && open && !i.is_own && (i.decision === "pending" || i.decision === "keep");
  const choosable = rows.filter(decidable);
  const chosen = rows.filter((i) => selected.includes(i.id) && decidable(i));
  const { total, decided } = progress(review);
  const toggle = (itemId: string) =>
    setSelected((current) =>
      current.includes(itemId) ? current.filter((x) => x !== itemId) : [...current, itemId],
    );
  const keep = (list: AccessReviewItem[]) =>
    decide.mutate(
      { items: list.map((i) => i.id), decision: "keep", comment: "" },
      { onSuccess: () => setSelected([]) },
    );

  return (
    <Stack spacing={2}>
      <Box>
        <Link component={RouterLink} to="/access-reviews" variant="body2">
          ← Access reviews
        </Link>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="h5" component="h1">
            {review.title}
          </Typography>
          <Chip size="small" label={STATUS[review.status]?.label ?? review.status} color={STATUS[review.status]?.color} />
        </Stack>
        <Typography variant="body2">
          Started {formatDate(review.created_at)} by {review.started_by_name ?? "system"} · finish by{" "}
          {formatDate(review.due_on)} · {decided} of {total} decided ({review.summary?.keep ?? 0} kept,{" "}
          {review.summary?.remove ?? 0} removed, {review.summary?.ended ?? 0} already ended)
          {review.completed_at && ` · completed ${formatDate(review.completed_at)} by ${review.completed_by_name ?? "—"}`}
        </Typography>
        {review.notes && <Typography variant="body2">Note: {review.notes}</Typography>}
      </Box>
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", rowGap: 1 }}>
        <Button component="a" href={reviewExportUrl(review.id)} variant="outlined" size="small">
          Download (CSV)
        </Button>
        {canManage && open && (
          <>
            <Button
              variant="contained"
              size="small"
              disabled={(review.summary?.pending ?? 0) > 0}
              onClick={() => setClosing("complete")}
            >
              Complete review
            </Button>
            <Button color="error" size="small" onClick={() => setClosing("cancel")}>
              Cancel review
            </Button>
          </>
        )}
      </Stack>
      {canManage && open && (review.summary?.pending ?? 0) > 0 && (
        <Alert severity="info">
          Keep or remove each entry. &quot;Complete review&quot; becomes available when nothing is left to
          review. Your own access is decided by another reviewer.
        </Alert>
      )}
      {decide.error && <ErrorAlert error={decide.error} />}
      {items.error && <ErrorAlert error={items.error} />}
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
        <TextField size="small" label="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
        <TextField
          select
          size="small"
          label="Decision"
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">All</MenuItem>
          {Object.entries(DECISIONS).map(([value, d]) => (
            <MenuItem key={value} value={value}>
              {d.label}
            </MenuItem>
          ))}
        </TextField>
        <Box sx={{ flex: 1 }} />
        {chosen.length > 0 && (
          <>
            <Button size="small" variant="outlined" disabled={decide.isPending} onClick={() => keep(chosen)}>
              Keep selected ({chosen.length})
            </Button>
            <Button size="small" color="error" variant="outlined" onClick={() => setRemoving(chosen)}>
              Remove selected ({chosen.length})
            </Button>
          </>
        )}
      </Stack>
      <TableContainer component={Paper}>
        {items.isFetching && <LinearProgress />}
        <Table size="small" aria-label="Access in this review">
          <TableHead>
            <TableRow>
              {canManage && open && (
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={choosable.length > 0 && chosen.length === choosable.length}
                    indeterminate={chosen.length > 0 && chosen.length < choosable.length}
                    disabled={choosable.length === 0}
                    onChange={(e) => setSelected(e.target.checked ? choosable.map((i) => i.id) : [])}
                    slotProps={{ input: { "aria-label": "Select all" } }}
                  />
                </TableCell>
              )}
              <TableCell>Person</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Where</TableCell>
              <TableCell>Last signed in</TableCell>
              <TableCell>Decision</TableCell>
              {canManage && open && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((i) => (
              <TableRow key={i.id}>
                {canManage && open && (
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={selected.includes(i.id)}
                      disabled={!decidable(i)}
                      onChange={() => toggle(i.id)}
                      slotProps={{ input: { "aria-label": `Select ${i.person_name} ${i.role_name} ${i.scope}` } }}
                    />
                  </TableCell>
                )}
                <TableCell>
                  {i.person_name}
                  <Typography variant="caption" component="p">
                    {i.person_email}
                  </Typography>
                  {!i.account_active && <Chip size="small" color="warning" label="Account switched off" />}
                </TableCell>
                <TableCell>{i.role_name}</TableCell>
                <TableCell>{i.scope}</TableCell>
                <TableCell>{i.last_signed_in_at ? formatDate(i.last_signed_in_at) : "Never"}</TableCell>
                <TableCell>
                  <Chip size="small" label={DECISIONS[i.decision]?.label ?? i.decision} color={DECISIONS[i.decision]?.color} />
                  {i.decided_by_name && (
                    <Typography variant="caption" component="p">
                      {i.decided_by_name}, {formatDate(i.decided_at)}
                      {i.comment && ` — ${i.comment}`}
                    </Typography>
                  )}
                </TableCell>
                {canManage && open && (
                  <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                    {i.is_own ? (
                      <Typography variant="caption">Your own access: another reviewer decides</Typography>
                    ) : (
                      decidable(i) && (
                        <>
                          {i.decision === "pending" && (
                            <Button
                              size="small"
                              disabled={decide.isPending}
                              onClick={() => keep([i])}
                              aria-label={`Keep ${i.person_name} ${i.role_name} ${i.scope}`}
                            >
                              Keep
                            </Button>
                          )}
                          <Button
                            size="small"
                            color="error"
                            onClick={() => setRemoving([i])}
                            aria-label={`Remove ${i.person_name} ${i.role_name} ${i.scope}`}
                          >
                            Remove
                          </Button>
                        </>
                      )
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
            {items.data && rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>Nothing matches.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {removing && (
        <RemoveDialog
          reviewId={review.id}
          items={removing}
          onClose={() => {
            setRemoving(undefined);
            setSelected([]);
          }}
        />
      )}
      {closing && <CloseDialog review={review} mode={closing} onClose={() => setClosing(undefined)} />}
    </Stack>
  );
}
