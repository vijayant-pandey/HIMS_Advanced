import { Breadcrumbs, Button, LinearProgress, Link, Stack, Tab, Tabs, Typography } from "@mui/material";
import { useState } from "react";
import { Link as RouterLink, useParams, useSearchParams } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasPermission } from "../auth/grants";
import { usePatient } from "./api";
import { ChartAlerts, ChartHeader } from "./ChartHeader";
import { PatientDemographics } from "./PatientDemographics";
import { PatientHistory } from "./PatientHistory";
import { PatientOverview } from "./PatientOverview";
import { EmergencyAccessBanner, RestrictedGate, RestrictionDialog } from "./RestrictedRecord";

const TABS = ["overview", "demographics", "history"] as const;
type ChartTab = (typeof TABS)[number];

/**
 * The patient chart (HIMS-PAT-005; spec 15.3, P0 part 01 section 7): the header stays in view on
 * every tab; Overview, Demographics (HIMS-PAT-001's record) and, for medical records, History.
 * Visits, Notes and Vitals tabs come with the visit record (HIMS-CLIN-001, -002, -005). The tab
 * is in the address (`?tab=`), never anything about the patient.
 *
 * A restricted record (HIMS-PAT-006) that the reader may not open shows the emergency access
 * form instead; medical records restrict a record or lift it from the header.
 */
export function PatientDetailPage() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const { data: user } = useCurrentUser();
  const { data: patient, isPending, error } = usePatient(id);
  const [restricting, setRestricting] = useState(false);
  // Hints only: the API checks every permission.
  const canChange = hasPermission(user, "patients.register") && patient?.status === "active";
  const canSeeHistory = hasPermission(user, "patients.history");
  const canRestrict = hasPermission(user, "patients.restricted") && patient?.status === "active";
  const us = user?.organization?.country === "US";
  const asked = params.get("tab") as ChartTab | null;
  const tab: ChartTab = asked && TABS.includes(asked) && (asked !== "history" || canSeeHistory) ? asked : "overview";

  if (isPending) return <LinearProgress />;
  if (id && error?.code === "RESTRICTED_RECORD") {
    return (
      <Stack spacing={2}>
        <Breadcrumbs>
          <Link component={RouterLink} to="/patients" underline="hover">
            Patients
          </Link>
          <Typography color="text.primary">Restricted record</Typography>
        </Breadcrumbs>
        <RestrictedGate patientId={id} />
      </Stack>
    );
  }
  if (error || !patient) return <ErrorAlert error={error} />;

  return (
    <Stack spacing={2}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/patients" underline="hover">
          Patients
        </Link>
        <Typography color="text.primary">{patient.mrn}</Typography>
      </Breadcrumbs>
      <ChartHeader
        patient={patient}
        actions={
          canRestrict && (
            <Button size="small" variant="outlined" color="error" onClick={() => setRestricting(true)}>
              {patient.is_restricted ? "Lift restriction" : "Restrict record"}
            </Button>
          )
        }
      />
      <EmergencyAccessBanner patient={patient} />
      <ChartAlerts patient={patient} />
      <Tabs
        value={tab}
        onChange={(_, value: ChartTab) => setParams(value === "overview" ? {} : { tab: value }, { replace: true })}
        aria-label="Chart sections"
      >
        <Tab value="overview" label="Overview" />
        <Tab value="demographics" label="Demographics" />
        {canSeeHistory && <Tab value="history" label="History" />}
      </Tabs>
      {tab === "overview" && <PatientOverview patient={patient} />}
      {tab === "demographics" && <PatientDemographics patient={patient} canChange={canChange} us={us} />}
      {tab === "history" && <PatientHistory patientId={patient.id} />}
      {restricting && <RestrictionDialog patient={patient} onClose={() => setRestricting(false)} />}
    </Stack>
  );
}
