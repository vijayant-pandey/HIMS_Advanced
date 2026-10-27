import {
  Alert,
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

import type { BedType } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useBulkBeds } from "./api";
import { BED_TYPES, options } from "./choices";

const MAX_BEDS = 60;

/** The same codes the server will create, e.g. prefix "b", start 1, count 4 -> b01..b04. */
export function bedCodes(prefix: string, start: number, count: number): string[] {
  const width = Math.max(2, String(start + count - 1).length);
  return Array.from(
    { length: count },
    (_, i) => `${prefix}${String(start + i).padStart(width, "0")}`.toLowerCase(),
  );
}

interface Props {
  roomId: string;
  roomName: string;
  /** Codes already used in this ward, to warn before saving. */
  takenCodes: string[];
  onClose: () => void;
}

export function AddBedsDialog({ roomId, roomName, takenCodes, onClose }: Props) {
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const bulk = useBulkBeds(idempotencyKey);
  const [prefix, setPrefix] = useState("b");
  const [start, setStart] = useState(1);
  const [count, setCount] = useState(4);
  const [bedType, setBedType] = useState<BedType>("general");

  const validCount = Number.isInteger(count) && count >= 1 && count <= MAX_BEDS;
  const validPrefix = /^[a-z0-9_-]{1,10}$/.test(prefix);
  const codes = validCount && validPrefix ? bedCodes(prefix, start, count) : [];
  const clashes = codes.filter((code) => takenCodes.includes(code));

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    bulk.mutate(
      { room: roomId, prefix, start, count, bed_type: bedType },
      { onSuccess: onClose },
    );
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <form onSubmit={submit} noValidate>
        <DialogTitle>Add beds · {roomName}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {bulk.error && <ErrorAlert error={bulk.error} />}
            <Stack direction="row" spacing={2}>
              <TextField
                label="Prefix"
                value={prefix}
                onChange={(e) => setPrefix(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))}
                error={!validPrefix}
                helperText="e.g. b or icu"
                slotProps={{ htmlInput: { maxLength: 10 } }}
              />
              <TextField
                label="Start at"
                type="number"
                value={start}
                onChange={(e) => setStart(Number(e.target.value))}
                slotProps={{ htmlInput: { min: 0 } }}
              />
              <TextField
                label="How many"
                type="number"
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                error={!validCount}
                helperText={`1 to ${MAX_BEDS}`}
                slotProps={{ htmlInput: { min: 1, max: MAX_BEDS } }}
              />
            </Stack>
            <TextField
              select
              label="Bed type"
              value={bedType}
              onChange={(e) => setBedType(e.target.value as BedType)}
            >
              {options(BED_TYPES).map((choice) => (
                <MenuItem key={choice.value} value={choice.value}>
                  {choice.label}
                </MenuItem>
              ))}
            </TextField>
            {codes.length > 0 && (
              <Alert severity={clashes.length ? "error" : "info"}>
                {clashes.length
                  ? `Already used in this ward: ${clashes.join(", ").toUpperCase()}. Change the prefix or start number.`
                  : `Creates ${codes.length} bed(s): ${codes[0]!.toUpperCase()}${
                      codes.length > 1 ? ` … ${codes[codes.length - 1]!.toUpperCase()}` : ""
                    }`}
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            type="submit"
            variant="contained"
            disabled={bulk.isPending || !codes.length || clashes.length > 0}
          >
            Add beds
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
