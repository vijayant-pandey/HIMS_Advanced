import {
  Alert,
  Box,
  Button,
  Chip,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { TreeBed, TreeRoom, TreeWard } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasPermissionAt } from "../auth/grants";
import { useFacilities } from "../facilities/api";
import { AddBedsDialog } from "./AddBedsDialog";
import { type LocationKind, useFacilityLocations } from "./api";
import { BedStatusDialog } from "./BedStatusDialog";
import { statusInfo } from "./bedStatus";
import { WARD_TYPES } from "./choices";
import { type ExistingLocation, LocationDialog } from "./LocationDialog";

/** Which dialog is open. */
type Action =
  | { type: "create"; kind: LocationKind; parentId: string; context: string }
  | { type: "edit"; kind: LocationKind; existing: ExistingLocation; context: string }
  | { type: "beds"; room: TreeRoom; takenCodes: string[] }
  | { type: "status"; bed: TreeBed; ward: TreeWard };

interface Managers {
  canManage: boolean;
  canChangeStatus: boolean;
  open: (action: Action) => void;
}

function CountChips({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (entries.length === 0) return <Typography variant="body2">No beds</Typography>;
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

/** Small text buttons next to a heading, shown only to people who may change the layout. */
function NodeActions({
  show,
  label,
  onEdit,
  addLabel,
  onAdd,
  canAdd = true,
}: {
  show: boolean;
  label: string;
  onEdit: () => void;
  addLabel?: string;
  onAdd?: () => void;
  canAdd?: boolean;
}) {
  if (!show) return null;
  return (
    <Stack direction="row" spacing={0.5} sx={{ display: "inline-flex", ml: 1 }}>
      <Button size="small" onClick={onEdit} aria-label={`Edit ${label}`}>
        Edit
      </Button>
      {addLabel && onAdd && canAdd && (
        <Button size="small" onClick={onAdd}>
          {addLabel}
        </Button>
      )}
    </Stack>
  );
}

function RoomRow({ room, ward, managers }: { room: TreeRoom; ward: TreeWard; managers: Managers }) {
  const { canManage, canChangeStatus, open } = managers;
  const takenCodes = ward.rooms.flatMap((r) => r.beds.map((b) => b.code));
  return (
    <Box sx={{ mt: 1, opacity: room.is_active ? 1 : 0.6 }}>
      <Typography variant="caption" component="p">
        {room.name}
        {room.is_isolation_capable && " · isolation-capable"}
        {!room.is_active && " · inactive"}
        <NodeActions
          show={canManage}
          label={room.name}
          onEdit={() =>
            open({ type: "edit", kind: "room", existing: room, context: `· ${room.name}` })
          }
          addLabel="Add beds"
          canAdd={room.is_active}
          onAdd={() => open({ type: "beds", room, takenCodes })}
        />
      </Typography>
      <Stack direction="row" sx={{ gap: 0.5, flexWrap: "wrap", mt: 0.5 }}>
        {room.beds.map((bed) => {
          const info = statusInfo(bed.status);
          const clickable = canChangeStatus || canManage;
          return (
            <Chip
              key={bed.id}
              size="small"
              color={info.color}
              label={bed.code.toUpperCase()}
              title={`${info.label}${bed.status_reason ? `: ${bed.status_reason}` : ""}`}
              aria-label={`Bed ${bed.code.toUpperCase()}, ${info.label}`}
              onClick={
                !clickable
                  ? undefined
                  : canChangeStatus
                    ? () => open({ type: "status", bed, ward })
                    : () =>
                        open({
                          type: "edit",
                          kind: "bed",
                          existing: bed,
                          context: `${bed.code.toUpperCase()} · ${ward.name}`,
                        })
              }
            />
          );
        })}
        {room.beds.length === 0 && <Typography variant="caption">No beds</Typography>}
      </Stack>
    </Box>
  );
}

function WardCard({ ward, managers }: { ward: TreeWard; managers: Managers }) {
  const { canManage, open } = managers;
  return (
    <Paper variant="outlined" sx={{ p: 1.5, opacity: ward.is_active ? 1 : 0.6 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1, flexWrap: "wrap" }}>
        <Typography variant="subtitle2" component="h4">
          {ward.name}{" "}
          <Typography component="span" variant="caption">
            ({ward.code} · {WARD_TYPES[ward.ward_type as keyof typeof WARD_TYPES] ?? ward.ward_type}
            {ward.department_name && ` · ${ward.department_name}`})
          </Typography>
          {!ward.is_active && " · inactive"}
          <NodeActions
            show={canManage}
            label={ward.name}
            onEdit={() =>
              open({ type: "edit", kind: "ward", existing: ward, context: `· ${ward.name}` })
            }
            addLabel="Add room"
            canAdd={ward.is_active}
            onAdd={() =>
              open({ type: "create", kind: "room", parentId: ward.id, context: `in ${ward.name}` })
            }
          />
        </Typography>
        <CountChips counts={ward.bed_counts} />
      </Box>
      {ward.rooms.map((room) => (
        <RoomRow key={room.id} room={room} ward={ward} managers={managers} />
      ))}
      {ward.rooms.length === 0 && (
        <Typography variant="body2" sx={{ mt: 1 }}>
          No rooms yet.
        </Typography>
      )}
    </Paper>
  );
}

export function LocationsPage() {
  const { data: user } = useCurrentUser();
  const facilities = useFacilities();
  const [chosen, setChosen] = useState<string>();
  const facilityId = chosen ?? facilities.data?.results[0]?.id;
  const facilityName = facilities.data?.results.find((f) => f.id === facilityId)?.name ?? "";
  const locations = useFacilityLocations(facilityId);
  const [action, setAction] = useState<Action>();
  const [hideInactive, setHideInactive] = useState(false);
  const close = () => setAction(undefined);

  // Hints only: the API checks each permission at the item's facility.
  const managers: Managers = {
    canManage: hasPermissionAt(user, "locations.manage", facilityId),
    canChangeStatus: hasPermissionAt(user, "beds.status.manage", facilityId),
    open: setAction,
  };
  const { canManage } = managers;
  const visible = <T extends { is_active: boolean }>(items: T[]) =>
    hideInactive ? items.filter((item) => item.is_active) : items;
  const tree = locations.data;

  return (
    <Stack spacing={2}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <Typography variant="h5" component="h1">
          Locations and beds
        </Typography>
        <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
          <FormControlLabel
            label="Hide inactive"
            control={
              <Switch checked={hideInactive} onChange={(e) => setHideInactive(e.target.checked)} />
            }
          />
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
          {canManage && facilityId && (
            <Button
              variant="contained"
              onClick={() =>
                setAction({
                  type: "create",
                  kind: "building",
                  parentId: facilityId,
                  context: `in ${facilityName}`,
                })
              }
            >
              Add building
            </Button>
          )}
        </Stack>
      </Box>
      {(facilities.isPending || locations.isFetching) && <LinearProgress />}
      {facilities.error && <ErrorAlert error={facilities.error} />}
      {locations.error?.problem.code === "FEATURE_DISABLED" ? (
        <Alert severity="info">
          {locations.error.problem.detail}
          {hasPermissionAt(user, "features.manage", facilityId) && " (menu → Features)"}
        </Alert>
      ) : (
        locations.error && <ErrorAlert error={locations.error} />
      )}
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
              {canManage
                ? "No buildings yet. Start with “Add building”, then add floors, wards, rooms and beds."
                : "No buildings yet. Ask your facility administrator to set up the buildings and wards."}
            </Typography>
          )}
          {visible(tree.buildings).map((building) => (
            <Stack key={building.id} spacing={1} sx={{ opacity: building.is_active ? 1 : 0.6 }}>
              <Typography variant="h6" component="h2">
                {building.name}
                {!building.is_active && " (inactive)"}
                <NodeActions
                  show={canManage}
                  label={building.name}
                  onEdit={() =>
                    setAction({
                      type: "edit",
                      kind: "building",
                      existing: building,
                      context: `· ${building.name}`,
                    })
                  }
                  addLabel="Add floor"
                  canAdd={building.is_active}
                  onAdd={() =>
                    setAction({
                      type: "create",
                      kind: "floor",
                      parentId: building.id,
                      context: `in ${building.name}`,
                    })
                  }
                />
              </Typography>
              {visible(building.floors).map((floor) => (
                <Stack key={floor.id} spacing={1} sx={{ pl: 1, opacity: floor.is_active ? 1 : 0.6 }}>
                  <Typography variant="subtitle1" component="h3">
                    {floor.name} · level {floor.level}
                    {!floor.is_active && " (inactive)"}
                    <NodeActions
                      show={canManage}
                      label={floor.name}
                      onEdit={() =>
                        setAction({
                          type: "edit",
                          kind: "floor",
                          existing: floor,
                          context: `· ${building.name}, ${floor.name}`,
                        })
                      }
                      addLabel="Add ward"
                      canAdd={floor.is_active}
                      onAdd={() =>
                        setAction({
                          type: "create",
                          kind: "ward",
                          parentId: floor.id,
                          context: `on ${floor.name}`,
                        })
                      }
                    />
                  </Typography>
                  {visible(floor.wards).map((ward) => (
                    <WardCard
                      key={ward.id}
                      ward={{
                        ...ward,
                        rooms: visible(ward.rooms).map((room) => ({
                          ...room,
                          beds: visible(room.beds),
                        })),
                      }}
                      managers={managers}
                    />
                  ))}
                  {floor.wards.length === 0 && (
                    <Typography variant="body2">No wards on this floor.</Typography>
                  )}
                </Stack>
              ))}
              {building.floors.length === 0 && (
                <Typography variant="body2" sx={{ pl: 1 }}>
                  No floors yet.
                </Typography>
              )}
            </Stack>
          ))}
        </>
      )}
      {action?.type === "status" && (
        <BedStatusDialog
          key={action.bed.id}
          bed={action.bed}
          wardName={action.ward.name}
          onClose={close}
          onEditDetails={
            canManage
              ? () =>
                  setAction({
                    type: "edit",
                    kind: "bed",
                    existing: action.bed,
                    context: `${action.bed.code.toUpperCase()} · ${action.ward.name}`,
                  })
              : undefined
          }
        />
      )}
      {(action?.type === "create" || action?.type === "edit") && facilityId && (
        <LocationDialog
          key={action.type === "edit" ? action.existing.id : `${action.kind}-${action.parentId}`}
          kind={action.kind}
          facilityId={facilityId}
          parentId={action.type === "create" ? action.parentId : undefined}
          existing={action.type === "edit" ? action.existing : undefined}
          context={action.context}
          onClose={close}
        />
      )}
      {action?.type === "beds" && (
        <AddBedsDialog
          roomId={action.room.id}
          roomName={action.room.name}
          takenCodes={action.takenCodes}
          onClose={close}
        />
      )}
    </Stack>
  );
}
