import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { FeatureSetting, FeatureState } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { FEATURE, useChangeFeature } from "./api";

type Setting = FeatureSetting["setting"];

interface Props {
  feature: FeatureState;
  /** Change the setting of this facility, or the hospital-wide one when undefined. */
  facility?: { id: string; name: string };
  onClose: () => void;
}

export function ChangeFeatureDialog({ feature, facility, onClose }: Props) {
  const current = facility ? feature.facility! : feature.hospital;
  const [setting, setSetting] = useState<Setting>(current.setting);
  const [reason, setReason] = useState("");
  // One key per dialog session: a double-click cannot apply the change twice.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const change = useChangeFeature(feature.key, idempotencyKey);
  const where = facility ? facility.name : "the whole hospital";
  const defaultLabel = facility
    ? `Same as the hospital (${feature.hospital.setting === "default" ? (feature.default ? "on" : "off") : feature.hospital.setting})`
    : `Use the default (${feature.default ? "on" : "off"})`;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    change.mutate(
      { facility: facility?.id ?? null, setting, reason: reason.trim(), version: current.version },
      { onSuccess: onClose },
    );
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <form onSubmit={submit} noValidate>
        <DialogTitle>
          {feature.name} · {where}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Typography variant="body2">{feature.description}</Typography>
            {change.error && <ErrorAlert error={change.error} />}
            <RadioGroup
              aria-label="Setting"
              value={setting}
              onChange={(e) => setSetting(e.target.value as Setting)}
            >
              <FormControlLabel value="default" control={<Radio />} label={defaultLabel} />
              <FormControlLabel value="on" control={<Radio />} label="On" />
              <FormControlLabel value="off" control={<Radio />} label="Off" />
            </RadioGroup>
            {feature.key === FEATURE.twoFactorForEveryone && setting === "on" && (
              <Alert severity="warning">
                Everyone without an authenticator app, including you if you have none, will be
                asked to set one up before they can continue.
              </Alert>
            )}
            {feature.key === FEATURE.locations && setting === "off" && (
              <Alert severity="warning">
                The Locations page and its data will be closed for {where}. Nothing is deleted;
                turning it on again brings everything back.
              </Alert>
            )}
            <TextField
              label="Reason"
              required
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              helperText="Kept in the audit log, e.g. 'Approved by the medical director on 28 Oct'."
              slotProps={{ htmlInput: { maxLength: 255 } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            type="submit"
            variant="contained"
            disabled={change.isPending || !reason.trim() || setting === current.setting}
          >
            Save
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
