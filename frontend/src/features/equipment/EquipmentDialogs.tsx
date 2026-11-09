import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type {
  Equipment,
  EquipmentCategoryEnum,
  EquipmentCreateRequest,
  EquipmentServiceKindEnum,
  EquipmentStatusEnum,
  Facility,
  TreeBuilding,
} from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { localDate } from "../../components/dates";
import { useDepartments, useFacilityLocations } from "../locations/api";
import {
  useChangeEquipmentStatus,
  useCreateEquipment,
  useEquipmentHistory,
  useRecordVisit,
  useUpdateEquipment,
} from "./api";

export const CATEGORIES: Record<EquipmentCategoryEnum, string> = {
  monitoring: "Patient monitoring",
  life_support: "Life support (ventilator, defibrillator)",
  infusion: "Infusion and syringe pumps",
  oxygen: "Oxygen and gases",
  imaging: "Imaging",
  laboratory: "Laboratory",
  surgical: "Operating theatre and surgical",
  sterilization: "Sterilization",
  mobility: "Wheelchairs and stretchers",
  other: "Other",
};

export const STATUSES: Record<EquipmentStatusEnum, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  in_service: { label: "In service", color: "success" },
  maintenance: { label: "Under maintenance", color: "warning" },
  out_of_service: { label: "Out of service", color: "error" },
  retired: { label: "Retired", color: "default" },
};

const KINDS: Record<EquipmentServiceKindEnum, string> = {
  service: "Service",
  repair: "Repair",
  calibration: "Calibration",
};

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

export function day(value: string | null | undefined): string {
  return value ? when.format(new Date(`${value}T00:00:00`)) : "—";
}

interface Values {
  facility: string;
  asset_tag: string;
  name: string;
  category: EquipmentCategoryEnum;
  department: string;
  ward: string;
  room: string;
  location_note: string;
  manufacturer: string;
  model_name: string;
  serial_number: string;
  purchased_on: string;
  warranty_until: string;
  last_service_on: string;
  next_service_due: string;
  last_calibrated_on: string;
  next_calibration_due: string;
  notes: string;
}

const DATE_FIELDS = [
  ["purchased_on", "Bought on"],
  ["warranty_until", "Warranty until"],
  ["last_service_on", "Last service"],
  ["next_service_due", "Next service due"],
  ["last_calibrated_on", "Last calibration"],
  ["next_calibration_due", "Next calibration due"],
] as const;

function startingValues(item: Equipment | undefined, facilityId: string): Values {
  return {
    facility: item?.facility ?? facilityId,
    asset_tag: item?.asset_tag ?? "",
    name: item?.name ?? "",
    category: item?.category ?? "other",
    department: item?.department ?? "",
    ward: item?.ward ?? "",
    room: item?.room ?? "",
    location_note: item?.location_note ?? "",
    manufacturer: item?.manufacturer ?? "",
    model_name: item?.model_name ?? "",
    serial_number: item?.serial_number ?? "",
    purchased_on: item?.purchased_on ?? "",
    warranty_until: item?.warranty_until ?? "",
    last_service_on: item?.last_service_on ?? "",
    next_service_due: item?.next_service_due ?? "",
    last_calibrated_on: item?.last_calibrated_on ?? "",
    next_calibration_due: item?.next_calibration_due ?? "",
    notes: item?.notes ?? "",
  };
}

function wardsOf(buildings: TreeBuilding[] | undefined) {
  return (buildings ?? []).flatMap((building) => building.floors.flatMap((floor) => floor.wards));
}

export function EquipmentFormDialog({
  item,
  facilities,
  onClose,
}: {
  item?: Equipment;
  facilities: Pick<Facility, "id" | "name">[];
  onClose: () => void;
}) {
  // One key per dialog session: a double-click or network retry cannot add it twice.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const create = useCreateEquipment(idempotencyKey);
  const update = useUpdateEquipment(item?.id ?? "");
  const save = item ? update : create;
  const [values, setValues] = useState<Values>(() => startingValues(item, ""));
  // The list of facilities may still be loading when the dialog opens.
  const facilityId = values.facility || facilities[0]?.id || "";
  const departments = useDepartments(facilityId || undefined);
  const locations = useFacilityLocations(facilityId || undefined);
  const wards = wardsOf(locations.data?.buildings);
  const rooms = wards.find((ward) => ward.id === values.ward)?.rooms ?? [];
  const errors = fieldErrors(save.error);
  const set = (name: keyof Values, value: string) => setValues((current) => ({ ...current, [name]: value }));
  const text = (name: keyof Values, label: string, helperText?: string) => (
    <TextField
      label={label}
      value={values[name]}
      onChange={(event) => set(name, event.target.value)}
      error={!!errors[name]}
      helperText={errors[name] ?? helperText}
    />
  );

  const submit = () => {
    const { facility, asset_tag, ...rest } = values;
    const body = {
      ...rest,
      department: rest.department || null,
      ward: rest.ward || null,
      room: rest.room || null,
      purchased_on: rest.purchased_on || null,
      warranty_until: rest.warranty_until || null,
      last_service_on: rest.last_service_on || null,
      next_service_due: rest.next_service_due || null,
      last_calibrated_on: rest.last_calibrated_on || null,
      next_calibration_due: rest.next_calibration_due || null,
    };
    if (item) update.mutate({ version: item.version, ...body }, { onSuccess: onClose });
    else create.mutate({ facility: facility || facilityId, asset_tag, ...body } as EquipmentCreateRequest, { onSuccess: onClose });
  };

  return (
    <FormDialog
      title={item ? `Edit ${item.asset_tag}` : "Add equipment"}
      error={save.error}
      fields={Object.keys(values)}
      submitLabel={item ? "Save" : "Add"}
      submitDisabled={!values.name.trim() || (!item && (!values.asset_tag.trim() || !facilityId))}
      pending={save.isPending}
      onClose={onClose}
      onSubmit={submit}
    >
      {!item && facilities.length > 1 && (
        <TextField
          select
          label="Facility"
          required
          value={facilityId}
          onChange={(event) => setValues({ ...values, facility: event.target.value, department: "", ward: "", room: "" })}
          error={!!errors.facility}
          helperText={errors.facility}
        >
          {facilities.map((facility) => (
            <MenuItem key={facility.id} value={facility.id}>
              {facility.name}
            </MenuItem>
          ))}
        </TextField>
      )}
      {!item && (
        <TextField
          label="Asset tag"
          required
          value={values.asset_tag}
          onChange={(event) => set("asset_tag", event.target.value)}
          error={!!errors.asset_tag}
          helperText={errors.asset_tag ?? "The hospital's number on the label, e.g. ICU-VENT-01. It cannot change later."}
        />
      )}
      <TextField
        label="Name"
        required
        value={values.name}
        onChange={(event) => set("name", event.target.value)}
        error={!!errors.name}
        helperText={errors.name ?? "e.g. Ventilator"}
      />
      <TextField
        select
        label="Category"
        value={values.category}
        onChange={(event) => set("category", event.target.value)}
      >
        {Object.entries(CATEGORIES).map(([value, label]) => (
          <MenuItem key={value} value={value}>
            {label}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Department"
        value={values.department}
        onChange={(event) => set("department", event.target.value)}
        error={!!errors.department}
        helperText={errors.department}
      >
        <MenuItem value="">None</MenuItem>
        {departments.data?.results.map((department) => (
          <MenuItem key={department.id} value={department.id}>
            {department.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Ward"
        value={values.ward}
        onChange={(event) => setValues({ ...values, ward: event.target.value, room: "" })}
        error={!!errors.ward}
        helperText={errors.ward}
      >
        <MenuItem value="">None</MenuItem>
        {wards.map((ward) => (
          <MenuItem key={ward.id} value={ward.id}>
            {ward.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Room"
        value={values.room}
        onChange={(event) => set("room", event.target.value)}
        disabled={!values.ward}
        error={!!errors.room}
        helperText={errors.room}
      >
        <MenuItem value="">None</MenuItem>
        {rooms.map((room) => (
          <MenuItem key={room.id} value={room.id}>
            {room.name}
          </MenuItem>
        ))}
      </TextField>
      {text("location_note", "More about where it is", "e.g. Store 2, top shelf")}
      {text("manufacturer", "Made by")}
      {text("model_name", "Model")}
      {text("serial_number", "Serial number")}
      {DATE_FIELDS.map(([name, label]) => (
        <TextField
          key={name}
          type="date"
          label={label}
          value={values[name]}
          onChange={(event) => set(name, event.target.value)}
          error={!!errors[name]}
          helperText={errors[name]}
          slotProps={{ inputLabel: { shrink: true } }}
        />
      ))}
      <TextField
        label="Notes"
        multiline
        minRows={2}
        value={values.notes}
        onChange={(event) => set("notes", event.target.value)}
        error={!!errors.notes}
        helperText={errors.notes ?? "No patient details."}
      />
    </FormDialog>
  );
}

function StatusDialog({ item, onClose }: { item: Equipment; onClose: () => void }) {
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const change = useChangeEquipmentStatus(item.id, idempotencyKey);
  const [status, setStatus] = useState<EquipmentStatusEnum>(item.status);
  const [reason, setReason] = useState(item.status_reason);
  const reasonNeeded = status !== "in_service";
  const errors = fieldErrors(change.error);
  return (
    <FormDialog
      title={`Status of ${item.asset_tag}`}
      error={change.error}
      fields={["status", "reason"]}
      submitDisabled={reasonNeeded && !reason.trim()}
      pending={change.isPending}
      onClose={onClose}
      maxWidth="xs"
      onSubmit={() =>
        change.mutate(
          { version: item.version, status, reason: reasonNeeded ? reason.trim() : "" },
          { onSuccess: onClose },
        )
      }
    >
      <TextField
        select
        label="Status"
        value={status}
        onChange={(event) => setStatus(event.target.value as EquipmentStatusEnum)}
      >
        {Object.entries(STATUSES).map(([value, info]) => (
          <MenuItem key={value} value={value}>
            {info.label}
          </MenuItem>
        ))}
      </TextField>
      {reasonNeeded && (
        <TextField
          label="Reason"
          required
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          error={!!errors.reason}
          helperText={errors.reason ?? "Why it cannot be used, e.g. Battery fault. No patient details."}
        />
      )}
    </FormDialog>
  );
}

function VisitDialog({ item, onClose }: { item: Equipment; onClose: () => void }) {
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const record = useRecordVisit(item.id, idempotencyKey);
  const [kind, setKind] = useState<EquipmentServiceKindEnum>("service");
  const [performedOn, setPerformedOn] = useState(localDate());
  const [performedBy, setPerformedBy] = useState("");
  const [nextDue, setNextDue] = useState("");
  const [notes, setNotes] = useState("");
  const errors = fieldErrors(record.error);
  return (
    <FormDialog
      title={`Record a visit for ${item.asset_tag}`}
      error={record.error}
      fields={["kind", "performed_on", "performed_by", "next_due", "notes"]}
      submitDisabled={!performedOn}
      pending={record.isPending}
      onClose={onClose}
      onSubmit={() =>
        record.mutate(
          {
            kind,
            performed_on: performedOn,
            performed_by: performedBy.trim(),
            notes: notes.trim(),
            next_due: nextDue || null,
          },
          { onSuccess: onClose },
        )
      }
    >
      <TextField
        select
        label="Kind of visit"
        value={kind}
        onChange={(event) => setKind(event.target.value as EquipmentServiceKindEnum)}
      >
        {Object.entries(KINDS).map(([value, label]) => (
          <MenuItem key={value} value={value}>
            {label}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        type="date"
        label="Done on"
        required
        value={performedOn}
        onChange={(event) => setPerformedOn(event.target.value)}
        error={!!errors.performed_on}
        helperText={errors.performed_on}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <TextField
        label="Done by"
        value={performedBy}
        onChange={(event) => setPerformedBy(event.target.value)}
        helperText="The technician or company"
      />
      <TextField
        type="date"
        label="Next one due"
        value={nextDue}
        onChange={(event) => setNextDue(event.target.value)}
        error={!!errors.next_due}
        helperText={errors.next_due ?? "Leave empty if it is not known."}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <TextField
        label="Notes"
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        error={!!errors.notes}
        helperText={errors.notes ?? "What was done. No patient details."}
      />
      <Alert severity="info">A visit cannot be changed once saved. To correct a mistake, add another one.</Alert>
    </FormDialog>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", gap: 2 }}>
      <Typography variant="body2" sx={{ minWidth: 150, color: "text.secondary" }}>
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Box>
  );
}

export function whereIs(item: Equipment): string {
  return (
    [item.department_name, item.ward_name, item.room_name, item.location_note].filter(Boolean).join(" · ") ||
    "Not recorded"
  );
}

export function EquipmentDetailsDialog({
  item,
  canManage,
  showFacility,
  onClose,
}: {
  item: Equipment;
  canManage: boolean;
  showFacility: boolean;
  onClose: () => void;
}) {
  const history = useEquipmentHistory(item.id);
  const [open, setOpen] = useState<"edit" | "status" | "visit">();
  const status = STATUSES[item.status];
  const retired = item.status === "retired";
  return (
    <>
      <Dialog open onClose={onClose} fullWidth maxWidth="sm">
        <DialogTitle>
          {item.asset_tag} · {item.name}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={0.5}>
            <Box>
              <Chip size="small" color={status.color} label={status.label} />
            </Box>
            {item.status_reason && <Alert severity="warning">{item.status_reason}</Alert>}
            <Fact label="Category" value={item.category_label} />
            {showFacility && <Fact label="Facility" value={item.facility_name} />}
            <Fact label="Where" value={whereIs(item)} />
            <Fact label="Made by" value={[item.manufacturer, item.model_name].filter(Boolean).join(" ") || "—"} />
            <Fact label="Serial number" value={item.serial_number || "—"} />
            <Fact label="Bought on" value={day(item.purchased_on)} />
            <Fact label="Warranty until" value={day(item.warranty_until)} />
            <Fact label="Last service" value={day(item.last_service_on)} />
            <Fact label="Next service due" value={day(item.next_service_due)} />
            <Fact label="Last calibration" value={day(item.last_calibrated_on)} />
            <Fact label="Next calibration due" value={day(item.next_calibration_due)} />
            {item.notes && <Fact label="Notes" value={item.notes} />}
            <Typography variant="subtitle2" component="h2" sx={{ pt: 1 }}>
              Visits
            </Typography>
            {history.isLoading && <LinearProgress aria-label="Loading visits" />}
            {history.error && <ErrorAlert error={history.error} />}
            {history.data?.length === 0 && <Typography variant="body2">No visits recorded yet.</Typography>}
            {!!history.data?.length && (
              <List dense aria-label="Visits">
                {history.data.map((visit) => (
                  <ListItem key={visit.id} disableGutters>
                    <ListItemText
                      primary={`${visit.kind_label} on ${day(visit.performed_on)}${visit.performed_by ? `, ${visit.performed_by}` : ""}`}
                      secondary={[
                        visit.notes,
                        visit.next_due ? `Next due ${day(visit.next_due)}` : "",
                        visit.recorded_by_name ? `Recorded by ${visit.recorded_by_name}` : "",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    />
                  </ListItem>
                ))}
              </List>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          {canManage && <Button onClick={() => setOpen("edit")}>Edit</Button>}
          {canManage && <Button onClick={() => setOpen("status")}>Change status</Button>}
          {canManage && !retired && <Button onClick={() => setOpen("visit")}>Record a visit</Button>}
          <Button onClick={onClose}>Close</Button>
        </DialogActions>
      </Dialog>
      {open === "edit" && <EquipmentFormDialog item={item} facilities={[]} onClose={() => setOpen(undefined)} />}
      {open === "status" && <StatusDialog item={item} onClose={() => setOpen(undefined)} />}
      {open === "visit" && <VisitDialog item={item} onClose={() => setOpen(undefined)} />}
    </>
  );
}
