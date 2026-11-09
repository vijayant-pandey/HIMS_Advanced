import {
  Alert,
  Box,
  Button,
  ButtonBase,
  Chip,
  FormControlLabel,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { BoardBed, BoardWard } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { BOARD_REFRESH_MS, useBedBoard, useBedHistory } from "./api";
import { BedStatusDialog } from "./BedStatusDialog";
import { BED_STATUS, statusInfo } from "./bedStatus";
import { AGE_GROUPS, BED_TYPES, GENDER_RESTRICTIONS } from "./choices";

const time = new Intl.DateTimeFormat(undefined, { timeStyle: "short" });
const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function typeLabel(bedType: string): string {
  return (BED_TYPES as Record<string, string>)[bedType] ?? bedType;
}

/** "for 5 min", "for 3 h", "for 2 days": how long the bed has had its status. */
export function since(changedAt: string, now = Date.now()): string {
  const minutes = Math.max(0, Math.floor((now - new Date(changedAt).getTime()) / 60_000));
  if (minutes < 60) return `for ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `for ${hours} h`;
  return `for ${Math.floor(hours / 24)} days`;
}

function BedHistoryList({ bedId }: { bedId: string }) {
  const history = useBedHistory(bedId);
  if (history.isLoading) return <LinearProgress aria-label="Loading status history" />;
  if (history.error) return <ErrorAlert error={history.error} />;
  if (!history.data?.length) return <Typography variant="body2">No status changes yet.</Typography>;
  return (
    <Box>
      <Typography variant="subtitle2" component="h3">
        Status history
      </Typography>
      <List dense aria-label="Status history">
        {history.data.map((change) => (
          <ListItem key={change.id} disableGutters>
            <ListItemText
              primary={`${statusInfo(change.from_status).label} → ${statusInfo(change.to_status).label}${
                change.reason ? `: ${change.reason}` : ""
              }`}
              secondary={`${when.format(new Date(change.changed_at))}${
                change.changed_by_name ? `, ${change.changed_by_name}` : ""
              }`}
            />
          </ListItem>
        ))}
      </List>
    </Box>
  );
}

function BedTile({ bed, onOpen }: { bed: BoardBed; onOpen: () => void }) {
  const info = statusInfo(bed.status);
  return (
    <ButtonBase
      onClick={onOpen}
      sx={{ display: "block", textAlign: "left", borderRadius: 1 }}
    >
      <Paper variant="outlined" sx={{ p: 1, height: "100%" }}>
        <Typography variant="subtitle2" component="span" sx={{ display: "block" }}>
          Bed {bed.code.toUpperCase()}
        </Typography>
        <Typography variant="caption" component="span" sx={{ display: "block" }}>
          {typeLabel(bed.bed_type)} · Room {bed.room_code.toUpperCase()}
          {bed.is_isolation_capable ? " · Isolation" : ""}
        </Typography>
        <Chip size="small" color={info.color} label={info.label} sx={{ mt: 0.5 }} />
        <Typography variant="caption" component="span" sx={{ display: "block" }}>
          {since(bed.status_changed_at)}
        </Typography>
      </Paper>
    </ButtonBase>
  );
}

function countsText(counts: Record<string, number>): string {
  const parts = Object.keys(BED_STATUS)
    .filter((status) => counts[status])
    .map((status) => `${counts[status]} ${statusInfo(status).label.toLowerCase()}`);
  return parts.length ? parts.join(" · ") : "No beds";
}

/** Bed board (HIMS-FAC-008; spec 4.10 "real-time availability board", 15.1 "ward board"): every ward's beds and
 * their status on one screen. No patients yet: admissions fill beds in Phase 3. */
export function BedBoardPage() {
  const [facilityId, setFacilityId] = useState<string>();
  const board = useBedBoard(facilityId);
  const [status, setStatus] = useState("all");
  const [bedType, setBedType] = useState("all");
  const [wardId, setWardId] = useState("all");
  const [isolationOnly, setIsolationOnly] = useState(false);
  const [open, setOpen] = useState<{ bed: BoardBed; ward: BoardWard } | null>(null);

  const data = board.data;
  const keep = (bed: BoardBed) =>
    (status === "all" || bed.status === status) &&
    (bedType === "all" || bed.bed_type === bedType) &&
    (!isolationOnly || bed.is_isolation_capable);
  const wards = (data?.wards ?? [])
    .filter((ward) => wardId === "all" || ward.id === wardId)
    .map((ward) => ({ ward, beds: ward.beds.filter(keep) }))
    .filter(({ beds }) => beds.length > 0);
  const bedTypes = [...new Set((data?.wards ?? []).flatMap((ward) => ward.beds.map((bed) => bed.bed_type)))];

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Bed board
        </Typography>
        <Typography variant="body2">
          Every ward's beds and their status. No patients yet: admissions fill beds later. Select a bed to see why it is
          unavailable and its history{data?.wards.some((w) => w.can_change_status) ? ", or to change its status" : ""}.
        </Typography>
      </Box>
      {board.isLoading && <LinearProgress aria-label="Loading bed board" />}
      {board.error && <ErrorAlert error={board.error} />}
      {data && data.facilities.length === 0 && (
        <Alert severity="info">No facility to show: none is active, or Locations is switched off.</Alert>
      )}
      {data && data.facility && (
        <>
          <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
            {data.facilities.length > 1 && (
              <TextField
                select
                size="small"
                label="Facility"
                value={data.facility}
                onChange={(event) => {
                  setFacilityId(event.target.value);
                  setWardId("all");
                }}
                sx={{ minWidth: 220 }}
              >
                {data.facilities.map((facility) => (
                  <MenuItem key={facility.id} value={facility.id}>
                    {facility.name}
                  </MenuItem>
                ))}
              </TextField>
            )}
            <TextField
              select
              size="small"
              label="Ward"
              value={wardId}
              onChange={(event) => setWardId(event.target.value)}
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="all">All wards</MenuItem>
              {data.wards.map((ward) => (
                <MenuItem key={ward.id} value={ward.id}>
                  {ward.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              size="small"
              label="Bed type"
              value={bedType}
              onChange={(event) => setBedType(event.target.value)}
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="all">All types</MenuItem>
              {bedTypes.map((value) => (
                <MenuItem key={value} value={value}>
                  {typeLabel(value)}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={<Switch checked={isolationOnly} onChange={(event) => setIsolationOnly(event.target.checked)} />}
              label="Isolation rooms only"
            />
            <Typography variant="body2" aria-live="polite">
              Updated {time.format(new Date(data.generated_at))}
            </Typography>
            <Button size="small" onClick={() => board.refetch()} disabled={board.isFetching}>
              Refresh now
            </Button>
          </Stack>
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }} role="group" aria-label="Filter by status">
            <Chip
              label={`All: ${Object.values(data.bed_counts).reduce((a, b) => a + b, 0)}`}
              color={status === "all" ? "primary" : "default"}
              onClick={() => setStatus("all")}
              aria-pressed={status === "all"}
            />
            {Object.keys(BED_STATUS)
              .filter((value) => data.bed_counts[value])
              .map((value) => (
                <Chip
                  key={value}
                  label={`${statusInfo(value).label}: ${data.bed_counts[value]}`}
                  color={status === value ? statusInfo(value).color : "default"}
                  variant={status === value ? "filled" : "outlined"}
                  onClick={() => setStatus(value)}
                  aria-pressed={status === value}
                />
              ))}
          </Stack>
          <Typography variant="body2">
            Available now:{" "}
            {Object.keys(data.available_by_type).length
              ? Object.entries(data.available_by_type)
                  .map(([value, count]) => `${typeLabel(value)} ${count}`)
                  .join(" · ")
              : "none"}
            . The board refreshes every {BOARD_REFRESH_MS / 1000} seconds.
          </Typography>
          {data.wards.length === 0 && <Alert severity="info">No wards with active beds to show here.</Alert>}
          {data.wards.length > 0 && wards.length === 0 && (
            <Alert severity="info">No beds match these filters.</Alert>
          )}
          {wards.map(({ ward, beds }) => (
            <Paper key={ward.id} variant="outlined" sx={{ p: 2 }} component="section" aria-label={ward.name}>
              <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "baseline" }}>
                <Typography variant="h6" component="h2">
                  {ward.name} ({ward.code.toUpperCase()})
                </Typography>
                <Typography variant="body2">
                  {ward.building_name} · {ward.floor_name} · {ward.department_name ?? "No department"}
                </Typography>
                {ward.gender_restriction !== "any" && (
                  <Chip
                    size="small"
                    label={(GENDER_RESTRICTIONS as Record<string, string>)[ward.gender_restriction] ?? ward.gender_restriction}
                  />
                )}
                {ward.age_group !== "any" && (
                  <Chip size="small" label={(AGE_GROUPS as Record<string, string>)[ward.age_group] ?? ward.age_group} />
                )}
              </Stack>
              <Typography variant="body2" sx={{ mb: 1 }}>
                {countsText(ward.bed_counts)}
              </Typography>
              <Box
                sx={{ display: "grid", gap: 1, gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))" }}
              >
                {beds.map((bed) => (
                  <BedTile key={bed.id} bed={bed} onOpen={() => setOpen({ bed, ward })} />
                ))}
              </Box>
            </Paper>
          ))}
        </>
      )}
      {open && (
        <BedStatusDialog
          bed={open.bed}
          wardName={open.ward.name}
          readOnly={!open.ward.can_change_status}
          onClose={() => setOpen(null)}
        >
          <BedHistoryList bedId={open.bed.id} />
        </BedStatusDialog>
      )}
    </Stack>
  );
}
