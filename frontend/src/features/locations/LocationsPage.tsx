import {
  Box,
  Chip,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { TreeBed, TreeWard } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasPermission } from "../auth/grants";
import { useFacilities } from "../facilities/api";
import { useFacilityLocations } from "./api";
import { BedStatusDialog } from "./BedStatusDialog";
import { statusInfo } from "./bedStatus";

function CountChips({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (entries.length === 0)
    return <Typography variant="body2">No beds</Typography>;
  return (
    <Stack direction="row" sx={{ gap: 0.5, flexWrap: "wrap" }}>
      {entries.map(([status, count]) => (
        <Chip
          key={status}
          size="small"
          variant="outlined"
          color={statusInfo(status).color}
          label={`${statusInfo(status).label}: ${count}`}
        />
      ))}
    </Stack>
  );
}

function WardCard({
  ward,
  canChangeStatus,
  onBed,
}: {
  ward: TreeWard;
  canChangeStatus: boolean;
  onBed: (bed: TreeBed, ward: TreeWard) => void;
}) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: 1.5, opacity: ward.is_active ? 1 : 0.6 }}
    >
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          gap: 1,
          flexWrap: "wrap",
        }}
      >
        <Typography variant="subtitle2" component="h4">
          {ward.name}{" "}
          <Typography component="span" variant="caption">
            ({ward.code})
          </Typography>
          {!ward.is_active && " · inactive"}
        </Typography>
        <CountChips counts={ward.bed_counts} />
      </Box>
      {ward.rooms.map((room) => (
        <Box key={room.id} sx={{ mt: 1 }}>
          <Typography variant="caption" component="p">
            {room.name}
            {room.is_isolation_capable && " · isolation-capable"}
            {!room.is_active && " · inactive"}
          </Typography>
          <Stack direction="row" sx={{ gap: 0.5, flexWrap: "wrap", mt: 0.5 }}>
            {room.beds.map((bed) => (
              <Chip
                key={bed.id}
                size="small"
                color={statusInfo(bed.status).color}
                label={bed.code.toUpperCase()}
                title={`${statusInfo(bed.status).label}${bed.status_reason ? `: ${bed.status_reason}` : ""}`}
                aria-label={`Bed ${bed.code.toUpperCase()}, ${statusInfo(bed.status).label}`}
                onClick={canChangeStatus ? () => onBed(bed, ward) : undefined}
              />
            ))}
            {room.beds.length === 0 && (
              <Typography variant="caption">No beds</Typography>
            )}
          </Stack>
        </Box>
      ))}
    </Paper>
  );
}

export function LocationsPage() {
  const { data: user } = useCurrentUser();
  const facilities = useFacilities();
  const [chosen, setChosen] = useState<string>();
  const facilityId = chosen ?? facilities.data?.results[0]?.id;
  const locations = useFacilityLocations(facilityId);
  const [selected, setSelected] = useState<{ bed: TreeBed; ward: TreeWard }>();
  // Hint only: the API checks beds.status.manage at the bed's facility.
  const canChangeStatus = hasPermission(user, "beds.status.manage");
  const tree = locations.data;

  return (
    <Stack spacing={2}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 2,
        }}
      >
        <Typography variant="h5" component="h1">
          Locations and beds
        </Typography>
        {(facilities.data?.results.length ?? 0) > 1 && (
          <TextField
            select
            size="small"
            label="Facility"
            value={facilityId ?? ""}
            onChange={(event) => setChosen(event.target.value)}
            sx={{ minWidth: 220 }}
          >
            {facilities.data?.results.map((facility) => (
              <MenuItem key={facility.id} value={facility.id}>
                {facility.name}
              </MenuItem>
            ))}
          </TextField>
        )}
      </Box>
      {(facilities.isPending || locations.isFetching) && <LinearProgress />}
      {facilities.error && <ErrorAlert error={facilities.error} />}
      {locations.error && <ErrorAlert error={locations.error} />}
      {tree && (
        <>
          <Paper sx={{ p: 1.5 }}>
            <Typography variant="subtitle2" component="h2" sx={{ mb: 0.5 }}>
              Beds in this facility
            </Typography>
            <CountChips counts={tree.bed_counts} />
          </Paper>
          {tree.buildings.length === 0 && (
            <Typography>
              No buildings yet. An administrator can add buildings, floors,
              wards, rooms and beds in the admin console.
            </Typography>
          )}
          {tree.buildings.map((building) => (
            <Stack key={building.id} spacing={1}>
              <Typography variant="h6" component="h2">
                {building.name}
                {!building.is_active && " (inactive)"}
              </Typography>
              {building.floors.map((floor) => (
                <Stack key={floor.id} spacing={1} sx={{ pl: 1 }}>
                  <Typography variant="subtitle1" component="h3">
                    {floor.name} · level {floor.level}
                  </Typography>
                  {floor.wards.map((ward) => (
                    <WardCard
                      key={ward.id}
                      ward={ward}
                      canChangeStatus={canChangeStatus}
                      onBed={(bed, w) => setSelected({ bed, ward: w })}
                    />
                  ))}
                  {floor.wards.length === 0 && (
                    <Typography variant="body2">
                      No wards on this floor.
                    </Typography>
                  )}
                </Stack>
              ))}
            </Stack>
          ))}
        </>
      )}
      {selected && (
        <BedStatusDialog
          key={selected.bed.id}
          bed={selected.bed}
          wardName={selected.ward.name}
          onClose={() => setSelected(undefined)}
        />
      )}
    </Stack>
  );
}
