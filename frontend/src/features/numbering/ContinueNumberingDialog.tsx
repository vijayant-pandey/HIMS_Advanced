import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from "@mui/material";
import { useState } from "react";

import type { NumberingScheme } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useSetNextNumber } from "./api";

interface Props {
  scheme: NumberingScheme;
  onClose: () => void;
}

/** For hospitals moving from another system: continue after the old system's last number. */
export function ContinueNumberingDialog({ scheme, onClose }: Props) {
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const setNext = useSetNextNumber(scheme.id, idempotencyKey);
  const [value, setValue] = useState("");
  const nextValue = Number(value);
  const valid = Number.isInteger(nextValue) && nextValue >= 1;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setNext.mutate({ version: scheme.version, next_value: nextValue }, { onSuccess: onClose });
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <form onSubmit={submit} noValidate>
        <DialogTitle>Continue numbering · {scheme.document_type_label}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Alert severity="info">
              Use this when moving from another system. If its last number was 54321, enter
              54322. The number can only move forward, so no number is ever used twice.
            </Alert>
            {setNext.error && <ErrorAlert error={setNext.error} />}
            <TextField
              label="Next running number"
              type="number"
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
              helperText={`The next number is currently ${scheme.next_number}`}
              slotProps={{ htmlInput: { min: 1 } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={!valid || setNext.isPending}>
            Save
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
