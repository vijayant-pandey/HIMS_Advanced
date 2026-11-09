import {
  Box,
  Button,
  Chip,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { Equipment, EquipmentStatusEnum } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { HIDE_WHEN_PRINTING, PrintLetterhead } from "../../components/Letterhead";
import { useCurrentUser } from "../auth/api";
import { hasPermission, hasPermissionAt } from "../auth/grants";
import { useFacilities } from "../facilities/api";
import { PAGE_SIZE, useEquipmentList } from "./api";
import { CATEGORIES, EquipmentDetailsDialog, EquipmentFormDialog, STATUSES, day, whereIs } from "./EquipmentDialogs";

const DUE: Record<string, { label: string; color: "error" | "warning" }> = {
  overdue: { label: "Overdue", color: "error" },
  due_soon: { label: "Due in 30 days", color: "warning" },
};

/** The equipment register (HIMS-FAC-009; spec 4.12): what, where, status and service dates. */
export function EquipmentPage() {
  const { data: user } = useCurrentUser();
  const [filters, setFilters] = useState({ facility: "", status: "", category: "", due: "", search: "" });
  const [page, setPage] = useState(0);
  const [openId, setOpenId] = useState<string>();
  const [adding, setAdding] = useState(false);
  const { data, isFetching, error } = useEquipmentList(filters, page + 1);
  const facilities = useFacilities().data?.results ?? [];
  const canManageSomewhere = hasPermission(user, "equipment.manage");
  const addable = facilities.filter((facility) => hasPermissionAt(user, "equipment.manage", facility.id));
  const set = (name: keyof typeof filters, value: string) => {
    setFilters((current) => ({ ...current, [name]: value }));
    setPage(0);
  };
  // The list refreshes after a change, so the open item is looked up rather than remembered.
  const open: Equipment | undefined = data?.results.find((item) => item.id === openId);
  // The same rule as the server: a department grant reaches only that department's equipment.
  const canManage = (item: Equipment) =>
    !!user?.grants?.some(
      (grant) =>
        grant.permission === "equipment.manage" &&
        (grant.facility_id === null ||
          (grant.facility_id === item.facility &&
            (grant.department_id === null || grant.department_id === item.department))),
    );

  return (
    <Stack spacing={2}>
      <PrintLetterhead title="Equipment register" />
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2, ...HIDE_WHEN_PRINTING }}>
        <Box>
          <Typography variant="h5" component="h1">
            Equipment
          </Typography>
          <Typography variant="body2">
            What the hospital owns, where it is, whether it can be used and when it is due for service. Select an item
            for its details and visits.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button onClick={() => window.print()}>Print</Button>
          {canManageSomewhere && (
            <Button variant="contained" onClick={() => setAdding(true)}>
              Add equipment
            </Button>
          )}
        </Stack>
      </Box>
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", ...HIDE_WHEN_PRINTING }}>
        <TextField
          size="small"
          label="Search"
          value={filters.search}
          onChange={(event) => set("search", event.target.value)}
          helperText="Tag, name, serial or maker"
        />
        {facilities.length > 1 && (
          <TextField
            select
            size="small"
            label="Facility"
            value={filters.facility}
            onChange={(event) => set("facility", event.target.value)}
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="">Any</MenuItem>
            {facilities.map((facility) => (
              <MenuItem key={facility.id} value={facility.id}>
                {facility.name}
              </MenuItem>
            ))}
          </TextField>
        )}
        <TextField
          select
          size="small"
          label="Status"
          value={filters.status}
          onChange={(event) => set("status", event.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">Any</MenuItem>
          {Object.entries(STATUSES).map(([value, info]) => (
            <MenuItem key={value} value={value}>
              {info.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Category"
          value={filters.category}
          onChange={(event) => set("category", event.target.value)}
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">Any</MenuItem>
          {Object.entries(CATEGORIES).map(([value, label]) => (
            <MenuItem key={value} value={value}>
              {label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Due"
          value={filters.due}
          onChange={(event) => set("due", event.target.value)}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">Any</MenuItem>
          {Object.entries(DUE).map(([value, info]) => (
            <MenuItem key={value} value={value}>
              {info.label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {error && <ErrorAlert error={error} />}
      <TableContainer component={Paper}>
        {isFetching && <LinearProgress aria-label="Loading equipment" sx={HIDE_WHEN_PRINTING} />}
        <Table size="small" aria-label="Equipment">
          <TableHead>
            <TableRow>
              <TableCell>Asset tag</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Where</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Next service</TableCell>
              <TableCell>Next calibration</TableCell>
              <TableCell>Due</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.results.map((item) => {
              const status = STATUSES[item.status as EquipmentStatusEnum];
              const due = DUE[item.due_state];
              return (
                <TableRow key={item.id} hover>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>
                    <Button variant="text" size="small" sx={{ p: 0, minWidth: 0 }} onClick={() => setOpenId(item.id)}>
                      {item.asset_tag}
                    </Button>
                  </TableCell>
                  <TableCell>{item.name}</TableCell>
                  <TableCell>
                    {facilities.length > 1 ? `${item.facility_name} · ` : ""}
                    {whereIs(item)}
                  </TableCell>
                  <TableCell>
                    <Chip size="small" color={status.color} label={status.label} />
                  </TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{day(item.next_service_due)}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{day(item.next_calibration_due)}</TableCell>
                  <TableCell>{due && <Chip size="small" color={due.color} label={due.label} />}</TableCell>
                </TableRow>
              );
            })}
            {data?.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>No equipment matches.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {data && data.count > PAGE_SIZE && (
          <TablePagination
            component="div"
            count={data.count}
            page={page}
            rowsPerPage={PAGE_SIZE}
            rowsPerPageOptions={[PAGE_SIZE]}
            onPageChange={(_, value: number) => setPage(value)}
          />
        )}
      </TableContainer>
      {open && (
        <EquipmentDetailsDialog
          item={open}
          canManage={canManage(open)}
          showFacility={facilities.length > 1}
          onClose={() => setOpenId(undefined)}
        />
      )}
      {adding && (
        <EquipmentFormDialog
          facilities={addable.length ? addable : facilities}
          onClose={() => setAdding(false)}
        />
      )}
    </Stack>
  );
}
