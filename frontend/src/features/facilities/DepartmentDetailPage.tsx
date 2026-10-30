import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  FormControlLabel,
  IconButton,
  LinearProgress,
  Link,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { type ReactNode, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";

import type { DepartmentDetail, DepartmentService, HoursSession } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasPermissionAt } from "../auth/grants";
import {
  useAddService,
  useDepartment,
  useHeadCandidates,
  useSetHours,
  useUpdateDepartment,
  useUpdateService,
} from "./api";
import { EditDepartmentDialog } from "./SetupDialogs";

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        {action}
      </Box>
      {children}
    </Paper>
  );
}

// --- Head of department ---------------------------------------------------------------------

function HeadDialog({ department, onClose }: { department: DepartmentDetail; onClose: () => void }) {
  const candidates = useHeadCandidates(department.id, true);
  const update = useUpdateDepartment(department.id);
  const [head, setHead] = useState(department.head ?? "");
  return (
    <FormDialog
      title={`Head of department · ${department.name}`}
      error={update.error}
      fields={["head"]}
      pending={update.isPending}
      onClose={onClose}
      maxWidth="xs"
      onSubmit={() => update.mutate({ version: department.version, head: head || null }, { onSuccess: onClose })}
    >
      <Typography variant="body2">
        Choose from working staff currently posted in this department. Being head does not give
        extra access by itself; give the "Head of department" role on the Access page if needed.
      </Typography>
      <TextField
        select
        label="Head"
        value={head}
        onChange={(e) => setHead(e.target.value)}
        error={!!fieldErrors(update.error).head}
        helperText={
          fieldErrors(update.error).head ??
          (candidates.data?.length === 0 ? "Nobody is posted here yet: add a posting on the Staff page." : undefined)
        }
      >
        <MenuItem value="">— No head —</MenuItem>
        {(candidates.data ?? []).map((c) => (
          <MenuItem key={c.id} value={c.id}>
            {c.name}
            {c.designation && ` (${c.designation})`}
          </MenuItem>
        ))}
      </TextField>
    </FormDialog>
  );
}

// --- Opening hours --------------------------------------------------------------------------

type EditableSession = { weekday: number; opens_at: string; closes_at: string };

export function hoursByDay(sessions: HoursSession[]): string[] {
  return WEEKDAYS.map((_, day) => {
    const list = sessions.filter((s) => Number(s.weekday) === day);
    return list.length ? list.map((s) => `${s.opens_at}–${s.closes_at}`).join(", ") : "Closed";
  });
}

function HoursDialog({ department, onClose }: { department: DepartmentDetail; onClose: () => void }) {
  const save = useSetHours(department.id);
  const [open24, setOpen24] = useState(department.open_24_hours);
  const [sessions, setSessions] = useState<EditableSession[]>(
    department.hours.map((h) => ({ weekday: Number(h.weekday), opens_at: h.opens_at, closes_at: h.closes_at })),
  );
  const problems = fieldErrors(save.error).sessions;
  const update = (index: number, change: Partial<EditableSession>) =>
    setSessions((list) => list.map((s, i) => (i === index ? { ...s, ...change } : s)));
  const copyMondayToWeekdays = () => {
    const monday = sessions.filter((s) => s.weekday === 0);
    setSessions([
      ...sessions.filter((s) => s.weekday === 0 || s.weekday > 4),
      ...[1, 2, 3, 4].flatMap((day) => monday.map((s) => ({ ...s, weekday: day }))),
    ]);
  };

  return (
    <FormDialog
      title={`Opening hours · ${department.name}`}
      error={save.error}
      fields={["sessions"]}
      pending={save.isPending}
      onClose={onClose}
      maxWidth="md"
      onSubmit={() =>
        save.mutate(
          {
            version: department.version,
            open_24_hours: open24,
            sessions: sessions.map((s) => ({ ...s, weekday: s.weekday as HoursSession["weekday"] })),
          },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        Times are in the facility&apos;s time zone ({department.timezone}). A day without sessions is
        closed. Add two sessions for split hours (e.g. morning and evening OPD).
      </Typography>
      <FormControlLabel
        label="Open 24 hours, every day (e.g. Emergency, ICU)"
        control={<Switch checked={open24} onChange={(e) => setOpen24(e.target.checked)} />}
      />
      {problems && <Alert severity="error">{problems}</Alert>}
      {!open24 && (
        <Stack spacing={1}>
          {WEEKDAYS.map((name, day) => (
            <Box key={name} sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
              <Typography variant="body2" sx={{ width: 100 }}>
                {name}
              </Typography>
              {sessions.map((s, index) =>
                s.weekday === day ? (
                  <Box key={index} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                    <TextField
                      size="small"
                      type="time"
                      value={s.opens_at}
                      onChange={(e) => update(index, { opens_at: e.target.value })}
                      slotProps={{ htmlInput: { "aria-label": `${name} opens` } }}
                    />
                    –
                    <TextField
                      size="small"
                      type="time"
                      value={s.closes_at}
                      onChange={(e) => update(index, { closes_at: e.target.value })}
                      slotProps={{ htmlInput: { "aria-label": `${name} closes` } }}
                    />
                    <IconButton
                      size="small"
                      aria-label={`Remove ${name} ${s.opens_at}–${s.closes_at}`}
                      onClick={() => setSessions((list) => list.filter((_, i) => i !== index))}
                    >
                      ×
                    </IconButton>
                  </Box>
                ) : null,
              )}
              <Button
                size="small"
                onClick={() => setSessions((list) => [...list, { weekday: day, opens_at: "09:00", closes_at: "17:00" }])}
                aria-label={`Add ${name} session`}
              >
                + Add
              </Button>
            </Box>
          ))}
          <Box>
            <Button size="small" onClick={copyMondayToWeekdays}>
              Copy Monday to Tuesday–Friday
            </Button>
          </Box>
        </Stack>
      )}
    </FormDialog>
  );
}

// --- Services -------------------------------------------------------------------------------

function ServiceDialog({
  departmentId,
  service,
  onClose,
}: {
  departmentId: string;
  service?: DepartmentService;
  onClose: () => void;
}) {
  const add = useAddService(departmentId, useState(() => crypto.randomUUID())[0]);
  const update = useUpdateService(service?.id ?? "");
  const mutation = service ? update : add;
  const [name, setName] = useState(service?.name ?? "");
  const [description, setDescription] = useState(service?.description ?? "");
  const errors = fieldErrors(mutation.error);
  return (
    <FormDialog
      title={service ? `Edit service · ${service.name}` : "Add service"}
      error={mutation.error}
      fields={["name", "description"]}
      submitDisabled={!name.trim()}
      pending={mutation.isPending}
      onClose={onClose}
      maxWidth="xs"
      onSubmit={() =>
        service
          ? update.mutate({ version: service.version, name: name.trim(), description }, { onSuccess: onClose })
          : add.mutate({ name: name.trim(), description }, { onSuccess: onClose })
      }
    >
      <TextField
        label="Service name"
        required
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={!!errors.name || !!errors.non_field_errors}
        helperText={errors.name ?? errors.non_field_errors ?? "e.g. Echocardiography, OPD consultation"}
      />
      <TextField
        label="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        multiline
        minRows={2}
      />
    </FormDialog>
  );
}

function ServiceRow({ service, canManage, onEdit }: { service: DepartmentService; canManage: boolean; onEdit: () => void }) {
  const toggle = useUpdateService(service.id);
  return (
    <TableRow sx={{ opacity: service.is_active ? 1 : 0.6 }}>
      <TableCell>{service.name}</TableCell>
      <TableCell>{service.description || "—"}</TableCell>
      <TableCell>
        <Chip size="small" color={service.is_active ? "success" : "default"} label={service.is_active ? "Offered" : "Not offered"} />
      </TableCell>
      <TableCell align="right">
        {canManage && (
          <>
            <Button size="small" onClick={onEdit} aria-label={`Edit ${service.name}`}>
              Edit
            </Button>
            <Button
              size="small"
              disabled={toggle.isPending}
              onClick={() => toggle.mutate({ version: service.version, is_active: !service.is_active })}
            >
              {service.is_active ? "Switch off" : "Switch on"}
            </Button>
          </>
        )}
      </TableCell>
    </TableRow>
  );
}

// --- Page -----------------------------------------------------------------------------------

type Dialog = "edit" | "head" | "hours" | "service" | { service: DepartmentService };

/** HIMS-FAC-007: one department with its head, services and opening hours. */
export function DepartmentDetailPage() {
  const { id } = useParams();
  const { data: user } = useCurrentUser();
  const { data: department, isPending, error } = useDepartment(id);
  const [dialog, setDialog] = useState<Dialog>();
  const close = () => setDialog(undefined);

  if (isPending) return <LinearProgress />;
  if (error || !department) return <ErrorAlert error={error} />;
  // Hint only: the API checks departments.manage at this department's facility.
  const canManage = hasPermissionAt(user, "departments.manage", department.facility);
  const days = hoursByDay(department.hours);

  return (
    <Stack spacing={2}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/departments" underline="hover">
          Departments
        </Link>
        <Typography>{department.name}</Typography>
      </Breadcrumbs>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Box>
          <Typography variant="h5" component="h1">
            {department.name}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.5 }}>
            <Typography variant="body2">
              {department.code} · {department.department_type_label} · {department.facility_name} ·{" "}
              {department.current_staff} staff · {department.active_wards} ward(s)
            </Typography>
            <Chip
              size="small"
              color={department.status === "active" ? "success" : "default"}
              label={department.status === "active" ? "Active" : "Inactive"}
            />
          </Stack>
        </Box>
        {canManage && (
          <Button variant="outlined" onClick={() => setDialog("edit")}>
            Edit
          </Button>
        )}
      </Box>

      <Section
        title="Head of department"
        action={canManage && <Button size="small" onClick={() => setDialog("head")}>Change</Button>}
      >
        <Typography variant="body2">{department.head_name ?? "No head chosen yet."}</Typography>
      </Section>

      <Section
        title="Opening hours"
        action={canManage && <Button size="small" onClick={() => setDialog("hours")}>Edit hours</Button>}
      >
        {department.open_24_hours ? (
          <Chip color="success" label="Open 24 hours, every day" />
        ) : (
          <Table size="small" aria-label="Opening hours">
            <TableBody>
              {WEEKDAYS.map((name, day) => (
                <TableRow key={name}>
                  <TableCell sx={{ width: 140 }}>{name}</TableCell>
                  <TableCell>{days[day]}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <Typography variant="caption" component="p" sx={{ mt: 1 }}>
          Times in {department.timezone}.
        </Typography>
      </Section>

      <Section
        title="Services offered"
        action={
          canManage &&
          department.status === "active" && (
            <Button size="small" variant="contained" onClick={() => setDialog("service")}>
              Add service
            </Button>
          )
        }
      >
        <Table size="small" aria-label="Services">
          <TableHead>
            <TableRow>
              <TableCell>Service</TableCell>
              <TableCell>Description</TableCell>
              <TableCell>Status</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {department.services.map((s) => (
              <ServiceRow key={s.id} service={s} canManage={canManage} onEdit={() => setDialog({ service: s })} />
            ))}
            {department.services.length === 0 && (
              <TableRow>
                <TableCell colSpan={4}>No services listed yet.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        <Typography variant="caption" component="p" sx={{ mt: 1 }}>
          Prices are added with billing (Phase 5).
        </Typography>
      </Section>

      {dialog === "edit" && <EditDepartmentDialog department={department} onClose={close} />}
      {dialog === "head" && <HeadDialog department={department} onClose={close} />}
      {dialog === "hours" && <HoursDialog department={department} onClose={close} />}
      {dialog === "service" && <ServiceDialog departmentId={department.id} onClose={close} />}
      {typeof dialog === "object" && (
        <ServiceDialog departmentId={department.id} service={dialog.service} onClose={close} />
      )}
    </Stack>
  );
}
