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
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import type { FeatureSetting, FeatureState } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasPermissionAt } from "../auth/grants";
import { useFacilities } from "../facilities/api";
import { useFeatureStates } from "./api";
import { ChangeFeatureDialog } from "./ChangeFeatureDialog";

const SETTING_LABEL: Record<FeatureSetting["setting"], string> = {
  default: "Default",
  on: "On",
  off: "Off",
};

function Availability({ feature }: { feature: FeatureState }) {
  if (!feature.available) {
    return <Chip size="small" variant="outlined" label={`Coming in ${feature.planned_phase}`} />;
  }
  if (!feature.offered_in_country) {
    return <Chip size="small" variant="outlined" label="Not offered in this country" />;
  }
  return (
    <Chip
      size="small"
      color={feature.enabled ? "success" : "default"}
      label={feature.enabled ? "On" : "Off"}
    />
  );
}

function SettingCell({ setting, isDefault }: { setting: FeatureSetting; isDefault: boolean }) {
  return (
    <>
      <Typography variant="body2">
        {SETTING_LABEL[setting.setting]}
        {setting.setting === "default" && ` (${isDefault ? "on" : "off"})`}
      </Typography>
      {setting.updated_by_name && (
        <Typography variant="caption" component="p" title={setting.reason}>
          {setting.reason} · {setting.updated_by_name}
        </Typography>
      )}
    </>
  );
}

export function FeaturesPage() {
  const { data: user } = useCurrentUser();
  const facilities = useFacilities();
  const [facilityId, setFacilityId] = useState<string>("");
  const facility = facilities.data?.results.find((f) => f.id === facilityId);
  const { data, isPending, error } = useFeatureStates(facilityId || undefined);
  const [changing, setChanging] = useState<FeatureState>();
  // Hint only: the API checks features.manage at the hospital or the facility.
  const canChange = hasPermissionAt(user, "features.manage", facilityId || null);

  const categories = [...new Set((data ?? []).map((f) => f.category))];

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="h5" component="h1">
            Features
          </Typography>
          <Typography variant="body2">
            Turn parts of HIMS on or off for the whole hospital or one facility. Every change needs
            a reason and is kept in the audit log.
          </Typography>
        </Box>
        <TextField
          select
          size="small"
          label="Settings for"
          value={facilityId}
          onChange={(e) => setFacilityId(e.target.value)}
          sx={{ minWidth: 240 }}
        >
          <MenuItem value="">Whole hospital</MenuItem>
          {facilities.data?.results.map((f) => (
            <MenuItem key={f.id} value={f.id}>
              {f.name}
            </MenuItem>
          ))}
        </TextField>
      </Box>
      {facility && (
        <Typography variant="body2">
          Only features that can differ per facility are shown. &ldquo;Same as the hospital&rdquo;
          means this facility follows the whole-hospital setting.
        </Typography>
      )}
      {error && <ErrorAlert error={error} />}
      {isPending && <LinearProgress />}
      {categories.map((category) => (
        <Stack key={category} spacing={1}>
          <Typography variant="h6" component="h2">
            {category}
          </Typography>
          <TableContainer component={Paper}>
            <Table size="small" aria-label={category}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: "40%" }}>Feature</TableCell>
                  <TableCell>Applies to</TableCell>
                  <TableCell>Hospital setting</TableCell>
                  {facility && <TableCell>{facility.name}</TableCell>}
                  <TableCell>Now</TableCell>
                  <TableCell align="right" />
                </TableRow>
              </TableHead>
              <TableBody>
                {data
                  ?.filter((f) => f.category === category)
                  .map((feature) => {
                    const changeable =
                      canChange && feature.available && feature.offered_in_country;
                    return (
                      <TableRow key={feature.key}>
                        <TableCell>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {feature.name}
                          </Typography>
                          <Typography variant="caption" component="p">
                            {feature.description}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          {feature.scope === "facility" ? "Each facility" : "Whole hospital"}
                        </TableCell>
                        <TableCell>
                          <SettingCell setting={feature.hospital} isDefault={feature.default} />
                        </TableCell>
                        {facility && (
                          <TableCell>
                            {feature.facility?.setting === "default" ? (
                              <Typography variant="body2">Same as the hospital</Typography>
                            ) : (
                              feature.facility && (
                                <SettingCell setting={feature.facility} isDefault={feature.default} />
                              )
                            )}
                          </TableCell>
                        )}
                        <TableCell>
                          <Availability feature={feature} />
                        </TableCell>
                        <TableCell align="right">
                          {changeable && (
                            <Button
                              size="small"
                              onClick={() => setChanging(feature)}
                              aria-label={`Change ${feature.name}`}
                            >
                              Change
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      ))}
      {changing && (
        <ChangeFeatureDialog
          key={`${changing.key}-${facilityId}`}
          feature={changing}
          facility={facility ? { id: facility.id, name: facility.name } : undefined}
          onClose={() => setChanging(undefined)}
        />
      )}
    </Stack>
  );
}
