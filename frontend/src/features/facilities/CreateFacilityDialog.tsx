import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from "@mui/material";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "../../api/client";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCreateFacility } from "./api";

const FACILITY_TYPES = [
  { value: "hospital", label: "Hospital" },
  { value: "clinic", label: "Clinic" },
  { value: "diagnostic_center", label: "Diagnostic center" },
  { value: "day_care", label: "Day-care center" },
] as const;

const schema = z.object({
  code: z
    .string()
    .min(1, "Required")
    .max(32)
    .regex(/^[-a-zA-Z0-9_]+$/, "Letters, numbers, hyphens and underscores only"),
  name: z.string().min(1, "Required").max(255),
  facility_type: z.enum(["hospital", "clinic", "diagnostic_center", "day_care"]),
  country: z.enum(["US", "IN"]),
  state_region: z.string().min(1, "Required").max(100),
  city: z.string().min(1, "Required").max(100),
  address_line1: z.string().min(1, "Required").max(255),
  address_line2: z.string().max(255),
  postal_code: z.string().min(1, "Required").max(20),
  timezone: z.string().min(1, "Required"),
  phone: z.string().max(32),
});
type FormValues = z.infer<typeof schema>;

const DEFAULTS: FormValues = {
  code: "",
  name: "",
  facility_type: "hospital",
  country: "IN",
  state_region: "",
  city: "",
  address_line1: "",
  address_line2: "",
  postal_code: "",
  timezone: "Asia/Kolkata",
  phone: "",
};

interface Props {
  open: boolean;
  onClose: () => void;
}

export function CreateFacilityDialog({ open, onClose }: Props) {
  // One key per dialog session: double-clicks and network retries cannot create duplicates.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const create = useCreateFacility(idempotencyKey);
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: DEFAULTS });

  const close = () => {
    reset(DEFAULTS);
    create.reset();
    setIdempotencyKey(crypto.randomUUID());
    onClose();
  };

  const onSubmit = handleSubmit((values) =>
    create.mutate(values, {
      onSuccess: close,
      onError: (error) => {
        if (error instanceof ApiError) {
          for (const fieldError of error.problem.errors ?? []) {
            if (fieldError.field && fieldError.field in DEFAULTS) {
              setError(fieldError.field as keyof FormValues, { message: fieldError.message });
            }
          }
        }
      },
    }),
  );

  const field = (name: keyof FormValues, label: string, required = true) => (
    <TextField
      label={label}
      required={required}
      error={!!errors[name]}
      helperText={errors[name]?.message}
      {...register(name)}
    />
  );

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm">
      <form onSubmit={onSubmit} noValidate>
        <DialogTitle>New facility</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {create.error && !create.error.problem.errors && <ErrorAlert error={create.error} />}
            {field("code", "Code")}
            {field("name", "Name")}
            <TextField select label="Type" defaultValue={DEFAULTS.facility_type} {...register("facility_type")}>
              {FACILITY_TYPES.map((type) => (
                <MenuItem key={type.value} value={type.value}>
                  {type.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label="Country" defaultValue={DEFAULTS.country} {...register("country")}>
              <MenuItem value="IN">India</MenuItem>
              <MenuItem value="US">United States</MenuItem>
            </TextField>
            {field("state_region", "State / region")}
            {field("city", "City")}
            {field("address_line1", "Address line 1")}
            {field("address_line2", "Address line 2", false)}
            {field("postal_code", "Postal code")}
            {field("timezone", "Time zone (IANA)")}
            {field("phone", "Phone", false)}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={close}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={create.isPending}>
            Create
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
