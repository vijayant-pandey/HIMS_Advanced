import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import type { Facility, NumberingPreviewRequest, NumberingScheme } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCreateScheme, useNumberingPreview, useUpdateScheme } from "./api";
import { DOCUMENT_TYPES, MONTHS, PERIODS, SEPARATORS } from "./labels";

type Settings = Required<
  Pick<
    NumberingPreviewRequest,
    | "document_type"
    | "prefix"
    | "separator"
    | "include_facility_code"
    | "period"
    | "year_format"
    | "financial_year_start_month"
    | "padding"
    | "start_at"
  >
> & { facility: string | null; is_active: boolean };

const NEW_SCHEME: Settings = {
  document_type: "encounter",
  facility: null,
  prefix: "",
  separator: "-",
  include_facility_code: false,
  period: "calendar_year",
  year_format: "full",
  financial_year_start_month: 4,
  padding: 6,
  start_at: 1,
  is_active: true,
};

function fromScheme(scheme: NumberingScheme): Settings {
  return {
    document_type: scheme.document_type,
    facility: scheme.facility,
    prefix: scheme.prefix,
    separator: scheme.separator,
    include_facility_code: scheme.include_facility_code,
    period: scheme.period,
    year_format: scheme.year_format,
    financial_year_start_month: scheme.financial_year_start_month,
    padding: scheme.padding,
    start_at: scheme.start_at,
    is_active: scheme.is_active,
  };
}

/** The format settings only (what the preview and both save requests share). */
function formatOf(values: Settings) {
  return {
    prefix: values.prefix,
    separator: values.separator,
    include_facility_code: values.include_facility_code,
    period: values.period,
    year_format: values.year_format,
    financial_year_start_month: values.financial_year_start_month,
    padding: values.padding,
    start_at: values.start_at,
  };
}

function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

interface Props {
  /** The scheme to edit, or undefined to add a facility's own series. */
  scheme?: NumberingScheme;
  /** Facilities the user may create a series for (create mode only). */
  facilities: Facility[];
  onClose: () => void;
}

export function SchemeDialog({ scheme, facilities, onClose }: Props) {
  const editing = scheme !== undefined;
  const [values, setValues] = useState<Settings>(() =>
    scheme ? fromScheme(scheme) : { ...NEW_SCHEME, facility: facilities[0]?.id ?? null },
  );
  // One key per dialog session: a double-click cannot create two series.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const create = useCreateScheme(idempotencyKey);
  const update = useUpdateScheme(scheme?.id ?? "");
  const saving = create.isPending || update.isPending;
  const saveError = create.error ?? update.error;

  // Debounce a string (compared by value) so typing sends one preview request, not one per key.
  const settingsJson = useDebounced(
    JSON.stringify({
      document_type: values.document_type,
      facility: values.facility,
      ...formatOf(values),
    }),
  );
  const previewSettings = useMemo(
    () => JSON.parse(settingsJson) as NumberingPreviewRequest,
    [settingsJson],
  );
  const preview = useNumberingPreview(previewSettings);
  const problems = preview.data?.errors ?? {};
  const serverErrors: Record<string, string> = {};
  if (saveError instanceof ApiError) {
    for (const fieldError of saveError.problem.errors ?? []) {
      if (fieldError.field) serverErrors[fieldError.field] = fieldError.message;
    }
  }
  const errorFor = (field: string) => serverErrors[field] ?? problems[field]?.[0];

  const set = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setValues((current) => ({ ...current, [key]: value }));

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (editing) {
      update.mutate(
        { version: scheme.version, is_active: values.is_active, ...formatOf(values) },
        { onSuccess: onClose },
      );
    } else {
      create.mutate(
        { document_type: values.document_type, facility: values.facility, ...formatOf(values) },
        { onSuccess: onClose },
      );
    }
  };

  const title = editing
    ? `${scheme.document_type_label} · ${scheme.facility_name ?? "whole hospital"}`
    : "New facility series";

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <form onSubmit={submit} noValidate>
        <DialogTitle>{title}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {saveError && !Object.keys(serverErrors).length && <ErrorAlert error={saveError} />}
            {!editing && (
              <Stack direction="row" spacing={2}>
                <TextField
                  select
                  fullWidth
                  label="Number type"
                  value={values.document_type}
                  onChange={(e) => set("document_type", e.target.value as Settings["document_type"])}
                  helperText="MRN is always hospital-wide"
                >
                  {DOCUMENT_TYPES.filter((t) => t.value !== "mrn").map((t) => (
                    <MenuItem key={t.value} value={t.value}>
                      {t.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  select
                  fullWidth
                  label="Facility"
                  value={values.facility ?? ""}
                  onChange={(e) => set("facility", e.target.value)}
                  error={!!errorFor("facility")}
                  helperText={errorFor("facility") ?? "Uses its own series instead of the hospital's"}
                >
                  {facilities.map((f) => (
                    <MenuItem key={f.id} value={f.id}>
                      {f.name}
                    </MenuItem>
                  ))}
                </TextField>
              </Stack>
            )}

            <Box
              aria-live="polite"
              sx={{ p: 1.5, borderRadius: 1, bgcolor: "action.hover", textAlign: "center" }}
            >
              <Typography variant="caption" component="p">
                The first number will look like
              </Typography>
              <Typography
                variant="h6"
                component="p"
                data-testid="numbering-example"
                sx={{ fontFamily: "monospace", letterSpacing: 0.5 }}
              >
                {preview.data?.example ?? "…"}
              </Typography>
              {preview.data && preview.data.longest !== preview.data.example && (
                <Typography variant="caption" component="p">
                  Longest possible: {preview.data.longest} ({preview.data.longest.length}{" "}
                  characters)
                </Typography>
              )}
            </Box>

            <Stack direction="row" spacing={2}>
              <TextField
                fullWidth
                label="Prefix"
                value={values.prefix}
                onChange={(e) => set("prefix", e.target.value.toUpperCase())}
                error={!!errorFor("prefix")}
                helperText={errorFor("prefix") ?? "Capital letters and digits, e.g. MRN, UHID"}
                slotProps={{ htmlInput: { maxLength: 10 } }}
              />
              <TextField
                select
                fullWidth
                label="Separator"
                value={values.separator}
                onChange={(e) => set("separator", e.target.value as Settings["separator"])}
              >
                {SEPARATORS.map((s) => (
                  <MenuItem key={s.label} value={s.value}>
                    {s.label}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>

            <Stack direction="row" spacing={2}>
              <TextField
                select
                fullWidth
                label="Running number restarts"
                value={values.period}
                onChange={(e) => set("period", e.target.value as Settings["period"])}
              >
                {PERIODS.map((p) => (
                  <MenuItem key={p.value} value={p.value}>
                    {p.label}
                  </MenuItem>
                ))}
              </TextField>
              {values.period !== "none" && (
                <TextField
                  select
                  fullWidth
                  label="Year in the number"
                  value={values.year_format}
                  onChange={(e) => set("year_format", e.target.value as Settings["year_format"])}
                >
                  <MenuItem value="full">Full (2026, 2026-27)</MenuItem>
                  <MenuItem value="short">Short (26, 26-27)</MenuItem>
                </TextField>
              )}
            </Stack>

            {values.period === "financial_year" && (
              <TextField
                select
                label="Financial year starts in"
                value={values.financial_year_start_month}
                onChange={(e) => set("financial_year_start_month", Number(e.target.value))}
                helperText="India: April. US: your hospital's fiscal year (often January, July or October)."
              >
                {MONTHS.map((month, index) => (
                  <MenuItem key={month} value={index + 1}>
                    {month}
                  </MenuItem>
                ))}
              </TextField>
            )}

            <Stack direction="row" spacing={2}>
              <TextField
                fullWidth
                type="number"
                label="Digits in the running number"
                value={values.padding}
                onChange={(e) => set("padding", Number(e.target.value))}
                error={!!errorFor("padding")}
                helperText={errorFor("padding") ?? "3 to 12; 6 gives 000001"}
                slotProps={{ htmlInput: { min: 3, max: 12 } }}
              />
              <TextField
                fullWidth
                type="number"
                label="Each new series starts at"
                value={values.start_at}
                onChange={(e) => set("start_at", Number(e.target.value))}
                error={!!errorFor("start_at")}
                helperText={errorFor("start_at") ?? "Usually 1"}
                slotProps={{ htmlInput: { min: 0 } }}
              />
            </Stack>

            <FormControlLabel
              control={
                <Switch
                  checked={values.include_facility_code}
                  onChange={(e) => set("include_facility_code", e.target.checked)}
                />
              }
              label="Include the facility code (e.g. ENC-BLR-2026-0000001)"
            />
            {editing && (
              <FormControlLabel
                control={
                  <Switch
                    checked={values.is_active}
                    onChange={(e) => set("is_active", e.target.checked)}
                  />
                }
                label="Active"
              />
            )}
            {editing && !values.is_active && (
              <Alert severity="warning">
                {scheme.facility
                  ? "This facility will go back to the hospital-wide series."
                  : "No new numbers of this type can be issued until a series is active again."}
              </Alert>
            )}
            {editing && (
              <Alert severity="info">
                Numbers already issued never change. New settings apply to the next number, and
                no number is ever handed out twice.
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            type="submit"
            variant="contained"
            disabled={saving || Object.keys(problems).length > 0}
          >
            Save
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
