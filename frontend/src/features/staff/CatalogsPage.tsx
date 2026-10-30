import {
  Box,
  Button,
  Chip,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Switch,
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

import type {
  Designation,
  DesignationCategory,
  QualificationCategory,
  QualificationType,
  Specialty,
} from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission } from "../auth/grants";
import { type CatalogKind, useCatalog, useSaveCatalogItem } from "./api";

const DESIGNATION_CATEGORIES: Record<DesignationCategory, string> = {
  medical: "Medical (doctors)",
  nursing: "Nursing",
  pharmacy: "Pharmacy",
  allied_health: "Allied health & technicians",
  administration: "Administration & management",
  support: "Support services",
  other: "Other",
};

const QUALIFICATION_CATEGORIES: Record<QualificationCategory, string> = {
  degree: "Degree",
  diploma: "Diploma",
  fellowship: "Fellowship",
  certification: "Certification",
};

const COUNTRIES = [
  { value: "", label: "Both countries" },
  { value: "IN", label: "India" },
  { value: "US", label: "United States" },
];

type Item = (Designation | Specialty | QualificationType) & {
  category?: string;
  country?: string;
  seniority?: number;
  description?: string;
};

const TABS: { kind: CatalogKind; label: string; one: string }[] = [
  { kind: "designations", label: "Job titles", one: "job title" },
  { kind: "specialties", label: "Specialties", one: "specialty" },
  { kind: "qualification-types", label: "Qualification types", one: "qualification type" },
];

function ItemDialog({ kind, one, item, onClose }: { kind: CatalogKind; one: string; item?: Item; onClose: () => void }) {
  const save = useSaveCatalogItem(kind, item?.id, useState(() => crypto.randomUUID())[0]);
  const [values, setValues] = useState({
    name: item?.name ?? "",
    category: item?.category ?? (kind === "designations" ? "medical" : "degree"),
    country: item?.country ?? "",
    seniority: item?.seniority ?? 3,
    description: item?.description ?? "",
  });
  const errors = fieldErrors(save.error);
  const set = (name: keyof typeof values, value: string | number) =>
    setValues((current) => ({ ...current, [name]: value }));
  const body: Record<string, unknown> =
    kind === "specialties"
      ? { name: values.name.trim() }
      : kind === "qualification-types"
        ? { name: values.name.trim(), category: values.category, country: values.country }
        : { ...values, name: values.name.trim() };

  return (
    <FormDialog
      title={item ? `Edit ${one} · ${item.name}` : `Add ${one}`}
      error={save.error}
      fields={Object.keys(values)}
      submitDisabled={!values.name.trim()}
      pending={save.isPending}
      onClose={onClose}
      onSubmit={() => save.mutate(item ? { version: item.version, ...body } : body, { onSuccess: onClose })}
    >
      <TextField
        label="Name"
        required
        value={values.name}
        onChange={(e) => set("name", e.target.value)}
        error={!!errors.name}
        helperText={errors.name ?? (item ? `Code ${item.code} stays the same.` : "A short code is made from the name.")}
      />
      {kind !== "specialties" && (
        <Stack direction="row" spacing={2}>
          <TextField select fullWidth label="Category" value={values.category} onChange={(e) => set("category", e.target.value)}>
            {Object.entries(kind === "designations" ? DESIGNATION_CATEGORIES : QUALIFICATION_CATEGORIES).map(
              ([value, label]) => (
                <MenuItem key={value} value={value}>
                  {label}
                </MenuItem>
              ),
            )}
          </TextField>
          <TextField select fullWidth label="Country" value={values.country} onChange={(e) => set("country", e.target.value)}>
            {COUNTRIES.map((c) => (
              <MenuItem key={c.value} value={c.value}>
                {c.label}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      )}
      {kind === "designations" && (
        <>
          <TextField
            type="number"
            label="Seniority (1 = entry level … 10 = leadership)"
            value={values.seniority}
            onChange={(e) => set("seniority", Number(e.target.value))}
            error={!!errors.seniority}
            helperText={errors.seniority}
            slotProps={{ htmlInput: { min: 1, max: 10 } }}
          />
          <TextField
            label="Description (optional)"
            value={values.description}
            onChange={(e) => set("description", e.target.value)}
            multiline
            minRows={2}
          />
        </>
      )}
    </FormDialog>
  );
}

function ActiveToggle({ kind, item, disabled }: { kind: CatalogKind; item: Item; disabled: boolean }) {
  const save = useSaveCatalogItem(kind, item.id, "unused");
  return (
    <Switch
      size="small"
      checked={item.is_active}
      disabled={disabled || save.isPending}
      onChange={(e) => save.mutate({ version: item.version, is_active: e.target.checked })}
      slotProps={{ input: { "aria-label": `${item.name} in use` } }}
    />
  );
}

function CatalogTab({ kind, one, canManage }: { kind: CatalogKind; one: string; canManage: boolean }) {
  const { data, isPending, error } = useCatalog<Item>(kind);
  const [search, setSearch] = useState("");
  const [onlyCustom, setOnlyCustom] = useState(false);
  const [editing, setEditing] = useState<Item | "new">();
  const term = search.trim().toLowerCase();
  const rows = (data ?? []).filter(
    (r) => (!term || r.name.toLowerCase().includes(term) || r.code.includes(term)) && (!onlyCustom || r.is_custom),
  );

  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 1 }}>
        <TextField size="small" label="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
        <FormControlLabel
          label="Only added by this hospital"
          control={<Switch checked={onlyCustom} onChange={(e) => setOnlyCustom(e.target.checked)} />}
        />
        <Box sx={{ flex: 1 }} />
        {canManage && (
          <Button variant="contained" size="small" onClick={() => setEditing("new")}>
            Add {one}
          </Button>
        )}
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isPending && <LinearProgress />}
        <Table size="small" aria-label={one}>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              {kind !== "specialties" && <TableCell>Category</TableCell>}
              {kind !== "specialties" && <TableCell>Country</TableCell>}
              {kind === "designations" && <TableCell>Seniority</TableCell>}
              <TableCell>Source</TableCell>
              <TableCell>In use</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} sx={{ opacity: r.is_active ? 1 : 0.6 }}>
                <TableCell>
                  {r.name}
                  <Typography variant="caption" component="p">
                    {r.code}
                  </Typography>
                </TableCell>
                {kind !== "specialties" && (
                  <TableCell>
                    {(kind === "designations" ? DESIGNATION_CATEGORIES : QUALIFICATION_CATEGORIES)[
                      r.category as never
                    ] ?? r.category}
                  </TableCell>
                )}
                {kind !== "specialties" && <TableCell>{r.country || "Both"}</TableCell>}
                {kind === "designations" && <TableCell>{r.seniority}</TableCell>}
                <TableCell>
                  <Chip size="small" variant="outlined" label={r.is_custom ? "Added by hospital" : "Standard"} />
                </TableCell>
                <TableCell>
                  <ActiveToggle kind={kind} item={r} disabled={!canManage} />
                </TableCell>
                <TableCell align="right">
                  {canManage && (
                    <Button size="small" onClick={() => setEditing(r)} aria-label={`Edit ${r.name}`}>
                      Edit
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data && rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>Nothing matches.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      {editing && (
        <ItemDialog
          key={editing === "new" ? "new" : editing.id}
          kind={kind}
          one={one}
          item={editing === "new" ? undefined : editing}
          onClose={() => setEditing(undefined)}
        />
      )}
    </Stack>
  );
}

/** HIMS-STAFF-010: the lists used when adding staff, postings and qualifications. */
export function CatalogsPage() {
  const { data: user } = useCurrentUser();
  const [tab, setTab] = useState(0);
  const canManage = hasOrganizationWidePermission(user, "catalogs.manage");
  const current = TABS[tab]!;
  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h5" component="h1">
          Job titles and catalogs
        </Typography>
        <Typography variant="body2">
          The lists used when adding staff, department postings and qualifications. HIMS comes with
          standard entries for India and the US; add your hospital&apos;s own, rename them, or switch
          off ones you do not use. Switched-off entries stay on existing records.
        </Typography>
      </Box>
      <Tabs value={tab} onChange={(_, value: number) => setTab(value)} aria-label="Catalogs">
        {TABS.map((t) => (
          <Tab key={t.kind} label={t.label} />
        ))}
      </Tabs>
      <CatalogTab key={current.kind} kind={current.kind} one={current.one} canManage={canManage} />
    </Stack>
  );
}
