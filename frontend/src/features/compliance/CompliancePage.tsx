import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { ComplianceRequirement, IncidentNotification, RiskEntry, SecurityIncident } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import {
  useComplianceSummary,
  useCreateRisk,
  useIncidents,
  useRecordNotification,
  useRequirements,
  useRisks,
  useUpdateIncident,
  useUpdateRequirement,
  useUpdateRisk,
} from "./api";
import { BrowserProtectionTab } from "./BrowserProtectionTab";
import { ConsoleAccessTab } from "./ConsoleAccessTab";
import { DatabaseAccessTab } from "./DatabaseAccessTab";
import { RetentionTab } from "./RetentionTab";
import { ScanningTab } from "./ScanningTab";
import { SecurityReviewTab } from "./SecurityReviewTab";
import { ReportIncidentDialog, SEVERITIES } from "./ReportIncidentDialog";

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const formatWhen = (value?: string | null) => (value ? when.format(new Date(value)) : "—");

type ChipColor = "default" | "info" | "success" | "warning" | "error";

const REQUIREMENT_STATUS: { value: ComplianceRequirement["status"]; label: string; color: ChipColor }[] = [
  { value: "not_started", label: "Not started", color: "default" },
  { value: "in_progress", label: "In progress", color: "warning" },
  { value: "implemented", label: "Implemented, not verified", color: "info" },
  { value: "verified", label: "Verified with evidence", color: "success" },
  { value: "not_applicable", label: "Not applicable", color: "default" },
];
const RISK_STATUS: { value: RiskEntry["status"]; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "treating", label: "Being treated" },
  { value: "accepted", label: "Accepted" },
  { value: "closed", label: "Closed" },
];
const INCIDENT_STATUS: { value: SecurityIncident["status"]; label: string; color: ChipColor }[] = [
  { value: "reported", label: "Reported", color: "error" },
  { value: "investigating", label: "Investigating", color: "warning" },
  { value: "contained", label: "Contained", color: "info" },
  { value: "closed", label: "Closed", color: "default" },
];

function riskColor(score: number): ChipColor {
  if (score >= 15) return "error";
  if (score >= 8) return "warning";
  return "default";
}

// --- Requirements ---------------------------------------------------------------------------

function RequirementDialog({ item, canManage, onClose }: { item: ComplianceRequirement; canManage: boolean; onClose: () => void }) {
  const update = useUpdateRequirement(item.id);
  const [status, setStatus] = useState(item.status);
  const [owner, setOwner] = useState(item.owner);
  const [evidence, setEvidence] = useState(item.evidence);
  const [next, setNext] = useState(item.next_review_on ?? "");
  return (
    <FormDialog
      title={item.title}
      error={update.error}
      fields={["status", "owner", "evidence", "next_review_on"]}
      submitLabel="Save"
      submitDisabled={!canManage}
      pending={update.isPending}
      onClose={onClose}
      maxWidth="md"
      onSubmit={() =>
        update.mutate(
          { version: item.version, status, owner, evidence, next_review_on: next || null },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="caption">
        {item.regulation} · {item.citation} · {item.code}
      </Typography>
      <Typography variant="body2">
        <strong>What the law asks:</strong> {item.summary}
      </Typography>
      <Typography variant="body2">
        <strong>What HIMS does:</strong> {item.hims_support || "—"}
      </Typography>
      <TextField select label="Status" value={status} disabled={!canManage} onChange={(e) => setStatus(e.target.value as ComplianceRequirement["status"])}>
        {REQUIREMENT_STATUS.map((s) => (
          <MenuItem key={s.value} value={s.value}>
            {s.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField label="Who answers for it" value={owner} disabled={!canManage} onChange={(e) => setOwner(e.target.value)} />
      <TextField
        label="Evidence"
        multiline
        minRows={2}
        value={evidence}
        disabled={!canManage}
        onChange={(e) => setEvidence(e.target.value)}
        helperText="Where the proof is (signed policy, audit report…). Required to mark as verified."
      />
      <TextField
        type="date"
        label="Next review"
        value={next}
        disabled={!canManage}
        onChange={(e) => setNext(e.target.value)}
        slotProps={{ inputLabel: { shrink: true } }}
      />
    </FormDialog>
  );
}

function RequirementsTab({ canManage }: { canManage: boolean }) {
  const [filters, setFilters] = useState({ status: "", search: "" });
  const { data, isFetching, error } = useRequirements(filters);
  const [open, setOpen] = useState<ComplianceRequirement>();
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2}>
        <TextField size="small" label="Search" value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} helperText="Code, title or law" />
        <TextField select size="small" label="Status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} sx={{ minWidth: 220 }}>
          <MenuItem value="">Any</MenuItem>
          {REQUIREMENT_STATUS.map((s) => (
            <MenuItem key={s.value} value={s.value}>
              {s.label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isFetching && <LinearProgress />}
        <Table size="small" aria-label="Compliance requirements">
          <TableHead>
            <TableRow>
              <TableCell>Requirement</TableCell>
              <TableCell>Law</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Owner</TableCell>
              <TableCell>Next review</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.map((item) => {
              const status = REQUIREMENT_STATUS.find((s) => s.value === item.status)!;
              return (
                <TableRow key={item.id} hover>
                  <TableCell>
                    <Button size="small" sx={{ p: 0, textAlign: "left" }} onClick={() => setOpen(item)}>
                      {item.title}
                    </Button>
                    <Typography variant="caption" component="p">
                      {item.code}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    {item.regulation}
                    <Typography variant="caption" component="p">
                      {item.citation}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" color={status.color} label={status.label} />
                  </TableCell>
                  <TableCell>{item.owner || "—"}</TableCell>
                  <TableCell>{item.next_review_on ?? "—"}</TableCell>
                </TableRow>
              );
            })}
            {data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>Nothing matches.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {open && <RequirementDialog item={open} canManage={canManage} onClose={() => setOpen(undefined)} />}
    </Stack>
  );
}

// --- Risks ----------------------------------------------------------------------------------

function RiskDialog({ risk, onClose }: { risk?: RiskEntry; onClose: () => void }) {
  const create = useCreateRisk(useState(() => crypto.randomUUID())[0]);
  const update = useUpdateRisk(risk?.id ?? "");
  const save = risk ? update : create;
  const [form, setForm] = useState({
    title: risk?.title ?? "",
    description: risk?.description ?? "",
    category: risk?.category ?? "",
    likelihood: risk?.likelihood ?? 3,
    impact: risk?.impact ?? 3,
    mitigation: risk?.mitigation ?? "",
    status: risk?.status ?? "open",
    owner: risk?.owner ?? "",
    acceptance_reason: risk?.acceptance_reason ?? "",
  });
  const set = (name: keyof typeof form, value: string | number) => setForm((f) => ({ ...f, [name]: value }));
  return (
    <FormDialog
      title={risk ? `${risk.code}: ${risk.title}` : "Add a risk"}
      error={save.error}
      fields={Object.keys(form)}
      submitDisabled={!form.title.trim() || !form.description.trim() || !form.category.trim()}
      pending={save.isPending}
      onClose={onClose}
      maxWidth="md"
      onSubmit={() => save.mutate(risk ? { ...form, version: risk.version } : form, { onSuccess: onClose })}
    >
      <TextField label="Risk" required value={form.title} onChange={(e) => set("title", e.target.value)} />
      <TextField label="Description" required multiline minRows={2} value={form.description} onChange={(e) => set("description", e.target.value)} />
      <TextField label="Area" required value={form.category} onChange={(e) => set("category", e.target.value)} helperText="e.g. access, data, availability" />
      <Stack direction="row" spacing={2}>
        {(["likelihood", "impact"] as const).map((name) => (
          <TextField key={name} select fullWidth label={name === "likelihood" ? "Likelihood (1 to 5)" : "Impact (1 to 5)"} value={form[name]} onChange={(e) => set(name, Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map((n) => (
              <MenuItem key={n} value={n}>
                {n}
              </MenuItem>
            ))}
          </TextField>
        ))}
      </Stack>
      <TextField label="What reduces it" multiline minRows={2} value={form.mitigation} onChange={(e) => set("mitigation", e.target.value)} />
      <TextField select label="Status" value={form.status} onChange={(e) => set("status", e.target.value)}>
        {RISK_STATUS.map((s) => (
          <MenuItem key={s.value} value={s.value}>
            {s.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField label="Owner" value={form.owner} onChange={(e) => set("owner", e.target.value)} />
      {form.status === "accepted" && (
        <TextField label="Why is this risk accepted?" required value={form.acceptance_reason} onChange={(e) => set("acceptance_reason", e.target.value)} />
      )}
    </FormDialog>
  );
}

function RisksTab({ canManage }: { canManage: boolean }) {
  const { data, isPending, error } = useRisks();
  const [open, setOpen] = useState<RiskEntry | "new">();
  const rows = [...(data ?? [])].sort((a, b) => b.score - a.score);
  return (
    <Stack spacing={2}>
      {canManage && (
        <Box>
          <Button variant="contained" onClick={() => setOpen("new")}>
            Add a risk
          </Button>
        </Box>
      )}
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Risk register">
          <TableHead>
            <TableRow>
              <TableCell>Risk</TableCell>
              <TableCell>Area</TableCell>
              <TableCell>Score</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>What reduces it</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((risk) => (
              <TableRow key={risk.id} hover>
                <TableCell>
                  {canManage ? (
                    <Button size="small" sx={{ p: 0, textAlign: "left" }} onClick={() => setOpen(risk)}>
                      {risk.title}
                    </Button>
                  ) : (
                    risk.title
                  )}
                  <Typography variant="caption" component="p">
                    {risk.code}
                  </Typography>
                </TableCell>
                <TableCell>{risk.category}</TableCell>
                <TableCell>
                  <Chip size="small" color={riskColor(risk.score)} label={risk.score} />
                </TableCell>
                <TableCell>{risk.status_label}</TableCell>
                <TableCell>
                  <Typography variant="caption">{risk.mitigation}</Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {open && <RiskDialog risk={open === "new" ? undefined : open} onClose={() => setOpen(undefined)} />}
    </Stack>
  );
}

// --- Incidents ------------------------------------------------------------------------------

function NotificationRow({ incident, row, canManage }: { incident: SecurityIncident; row: IncidentNotification; canManage: boolean }) {
  const record = useRecordNotification(incident.id);
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  return (
    <TableRow>
      <TableCell>{row.kind_label}</TableCell>
      <TableCell sx={{ whiteSpace: "nowrap" }}>
        {formatWhen(row.due_at)}
        {row.is_overdue && <Chip size="small" color="error" label="Overdue" sx={{ ml: 1 }} />}
      </TableCell>
      <TableCell>
        {row.status === "pending" && canManage ? (
          <Stack spacing={1}>
            <TextField size="small" label={`Reference: ${row.kind_label}`} value={reference} onChange={(e) => setReference(e.target.value)} />
            <TextField size="small" label={`Why not required: ${row.kind_label}`} value={note} onChange={(e) => setNote(e.target.value)} />
            <Stack direction="row" spacing={1}>
              <Button size="small" variant="contained" disabled={record.isPending} onClick={() => record.mutate({ id: row.id, status: "done", reference, note })}>
                Mark done
              </Button>
              <Button size="small" disabled={record.isPending || !note.trim()} onClick={() => record.mutate({ id: row.id, status: "not_required", reference, note })}>
                Not required
              </Button>
            </Stack>
            {record.error && <ErrorAlert error={record.error} />}
          </Stack>
        ) : (
          <>
            {row.status_label}
            <Typography variant="caption" component="p">
              {[row.done_by_name, formatWhen(row.done_at), row.reference, row.note].filter((v) => v && v !== "—").join(" · ")}
            </Typography>
          </>
        )}
      </TableCell>
    </TableRow>
  );
}

function IncidentDialog({ incident, canManage, onClose }: { incident: SecurityIncident; canManage: boolean; onClose: () => void }) {
  const update = useUpdateIncident(incident.id);
  const [form, setForm] = useState({
    severity: incident.severity,
    status: incident.status,
    personal_data_affected: incident.personal_data_affected,
    people_affected: incident.people_affected === null ? "" : String(incident.people_affected),
    actions_taken: incident.actions_taken,
    closure_summary: incident.closure_summary,
  });
  const closed = incident.status === "closed";
  const editable = canManage && !closed;
  return (
    <FormDialog
      title={incident.title}
      error={update.error}
      fields={Object.keys(form)}
      submitDisabled={!editable}
      pending={update.isPending}
      onClose={onClose}
      maxWidth="md"
      onSubmit={() =>
        update.mutate(
          { ...form, people_affected: form.people_affected === "" ? null : Number(form.people_affected), version: incident.version },
          { onSuccess: onClose },
        )
      }
    >
      <Typography variant="body2">
        Noticed {formatWhen(incident.detected_at)} · reported by {incident.reported_by_name ?? "—"}
      </Typography>
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
        {incident.description}
      </Typography>
      <Stack direction="row" spacing={2}>
        <TextField select fullWidth label="Severity" value={form.severity} disabled={!editable} onChange={(e) => setForm({ ...form, severity: e.target.value as SecurityIncident["severity"] })}>
          {SEVERITIES.map((s) => (
            <MenuItem key={s.value} value={s.value}>
              {s.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField select fullWidth label="Status" value={form.status} disabled={!editable} onChange={(e) => setForm({ ...form, status: e.target.value as SecurityIncident["status"] })}>
          {INCIDENT_STATUS.map((s) => (
            <MenuItem key={s.value} value={s.value}>
              {s.label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      <FormControlLabel
        disabled={!editable}
        control={<Checkbox checked={form.personal_data_affected} onChange={(e) => setForm({ ...form, personal_data_affected: e.target.checked })} />}
        label="Personal or patient data affected"
      />
      <TextField type="number" label="People affected" value={form.people_affected} disabled={!editable} onChange={(e) => setForm({ ...form, people_affected: e.target.value })} helperText="Leave empty if not known yet" />
      <TextField label="Actions taken" multiline minRows={2} value={form.actions_taken} disabled={!editable} onChange={(e) => setForm({ ...form, actions_taken: e.target.value })} />
      <TextField label="Closure summary" multiline minRows={2} value={form.closure_summary} disabled={!editable} onChange={(e) => setForm({ ...form, closure_summary: e.target.value })} helperText="Required to close" />
      <Typography variant="subtitle2" component="h3">
        Legal notifications
      </Typography>
      {incident.notifications.length === 0 ? (
        <Typography variant="body2">None required by the facts so far. Tick "Personal data affected" if that changes.</Typography>
      ) : (
        <TableContainer component={Paper}>
          <Table size="small" aria-label="Legal notifications">
            <TableHead>
              <TableRow>
                <TableCell>Notice</TableCell>
                <TableCell>Deadline</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {incident.notifications.map((row) => (
                <NotificationRow key={row.id} incident={incident} row={row} canManage={canManage} />
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <Typography variant="caption">
        Deadlines are working defaults for the team. Counsel confirms which notices apply; see the incident runbook.
      </Typography>
    </FormDialog>
  );
}

function IncidentsTab({ canManage }: { canManage: boolean }) {
  const { data, isPending, error } = useIncidents();
  const [params] = useSearchParams();
  const [openId, setOpenId] = useState<string | null>(params.get("incident"));
  const [reporting, setReporting] = useState(false);
  const open = data?.find((incident) => incident.id === openId);
  return (
    <Stack spacing={2}>
      <Box>
        <Button variant="contained" onClick={() => setReporting(true)}>
          Report a security incident
        </Button>
      </Box>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label="Security incidents">
          <TableHead>
            <TableRow>
              <TableCell>Incident</TableCell>
              <TableCell>Noticed</TableCell>
              <TableCell>Severity</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Next deadline</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.map((incident) => {
              const status = INCIDENT_STATUS.find((s) => s.value === incident.status)!;
              const next = incident.notifications.find((row) => row.status === "pending");
              return (
                <TableRow key={incident.id} hover>
                  <TableCell>
                    <Button size="small" sx={{ p: 0, textAlign: "left" }} onClick={() => setOpenId(incident.id)}>
                      {incident.title}
                    </Button>
                  </TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{formatWhen(incident.detected_at)}</TableCell>
                  <TableCell>{incident.severity_label}</TableCell>
                  <TableCell>
                    <Chip size="small" color={status.color} label={status.label} />
                  </TableCell>
                  <TableCell>
                    {next ? (
                      <>
                        {formatWhen(next.due_at)}
                        {next.is_overdue && <Chip size="small" color="error" label="Overdue" sx={{ ml: 1 }} />}
                        <Typography variant="caption" component="p">
                          {next.kind_label}
                        </Typography>
                      </>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>No incidents reported.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {open && <IncidentDialog key={open.version} incident={open} canManage={canManage} onClose={() => setOpenId(null)} />}
      {reporting && <ReportIncidentDialog onClose={() => setReporting(false)} />}
    </Stack>
  );
}

// --- Page -----------------------------------------------------------------------------------

/** Compliance registers (spec 13, 23, 26.7; HIMS-COMP). Software support is not legal compliance. */
export function CompliancePage() {
  const { data: me } = useCurrentUser();
  const canManage = hasOrganizationWidePermission(me, "compliance.manage");
  const [params] = useSearchParams();
  const [tab, setTab] = useState(params.get("incident") ? "incidents" : "requirements");
  const summary = useComplianceSummary();
  const counts = summary.data?.requirements_by_status ?? {};
  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Compliance
        </Typography>
        <Typography variant="body2">
          What the law asks of this hospital, the risks being managed and any security incidents. "Implemented" means
          the software supports it; legal counsel and the hospital confirm compliance.
        </Typography>
      </Box>
      {summary.error && <ErrorAlert error={summary.error} />}
      {summary.data && (summary.data.notifications_overdue > 0 ? (
        <Alert severity="error">
          {summary.data.notifications_overdue} legal notification(s) are overdue. Open the Incidents tab.
        </Alert>
      ) : null)}
      {summary.data && (
        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", rowGap: 1 }}>
          <Chip label={`${summary.data.requirements_total} requirements`} />
          <Chip color="success" label={`${counts.verified ?? 0} verified`} />
          <Chip color="info" label={`${counts.implemented ?? 0} implemented`} />
          <Chip color="warning" label={`${counts.in_progress ?? 0} in progress`} />
          <Chip label={`${counts.not_started ?? 0} not started`} />
          <Chip color={summary.data.risks_high ? "error" : "default"} label={`${summary.data.risks_high} high risks`} />
          <Chip color={summary.data.incidents_open ? "error" : "default"} label={`${summary.data.incidents_open} open incidents`} />
        </Stack>
      )}
      <Tabs value={tab} onChange={(_, value: string) => setTab(value)} variant="scrollable" scrollButtons="auto">
        <Tab value="requirements" label="Requirements" />
        <Tab value="risks" label="Risks" />
        <Tab value="incidents" label="Incidents" />
        <Tab value="browser" label="Browser protection" />
        <Tab value="console" label="Console access" />
        <Tab value="database" label="Database access" />
        <Tab value="scanning" label="Scanning and traces" />
        <Tab value="retention" label="Retention" />
        <Tab value="review" label="Security review" />
      </Tabs>
      {tab === "requirements" && <RequirementsTab canManage={canManage} />}
      {tab === "risks" && <RisksTab canManage={canManage} />}
      {tab === "incidents" && <IncidentsTab canManage={canManage} />}
      {tab === "browser" && <BrowserProtectionTab canManage={canManage} />}
      {tab === "console" && <ConsoleAccessTab canManage={canManage} />}
      {tab === "database" && <DatabaseAccessTab />}
      {tab === "scanning" && <ScanningTab canManage={canManage} />}
      {tab === "retention" && <RetentionTab canManage={canManage} />}
      {tab === "review" && <SecurityReviewTab />}
    </Stack>
  );
}
