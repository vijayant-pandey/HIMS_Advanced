import { Box, Chip, Paper, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

import type { PatientDetail } from "../../api/types";
import { contactText, currentConsents } from "./PatientDemographics";
import { ALLERGY_STATUS, CONSENT_KINDS, CONSENT_STATUS, day, dayTime } from "./labels";

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Paper variant="outlined" component="section" aria-label={title} sx={{ p: 2 }}>
      <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
        {title}
      </Typography>
      <Stack spacing={0.75}>{children}</Stack>
    </Paper>
  );
}

function Line({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 170 }}>
        {label}
      </Typography>
      <Typography variant="body2" component="div">
        {children}
      </Typography>
    </Box>
  );
}

const NOT_YET = "None recorded";

/**
 * The chart's Overview tab (HIMS-PAT-005; P0 part 01 section 7): the clinical summary (allergies,
 * problems, reported medicines, last vitals, next appointment), how to reach the patient and who
 * to call, ID numbers (masked), consent in force and where the record came from. The clinical
 * lines fill in as the visit record and appointments arrive (HIMS-CLIN-002 to -006, HIMS-OPD-002).
 */
export function PatientOverview({ patient }: { patient: PatientDetail }) {
  const contacts = patient.contacts.filter((c) => c.is_active);
  const people = patient.relationships.filter((p) => p.is_active && (p.is_legal_guardian || p.is_emergency_contact));
  const ids = patient.identifiers.filter((i) => i.is_active);
  const consents = currentConsents(patient.consents);

  return (
    <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
      <Card title="Clinical summary">
        <Line label="Allergies">{ALLERGY_STATUS[patient.allergy_status] ?? patient.allergy_status}</Line>
        <Line label="Problems (diagnoses)">{NOT_YET}</Line>
        <Line label="Medicines (as reported)">{NOT_YET}</Line>
        <Line label="Last vitals">{NOT_YET}</Line>
        <Line label="Next appointment">None booked</Line>
        <Typography variant="caption" color="text.secondary">
          Recorded on the visit screen and in appointments, which come later in Phase 2.
        </Typography>
      </Card>

      <Card title="Contact">
        {contacts.map((contact) => (
          <Line key={contact.id} label={contact.kind_label}>
            {contactText(contact)}
            {contact.is_primary && <Chip size="small" label="Main" sx={{ ml: 1 }} />}
          </Line>
        ))}
        {contacts.length === 0 && (
          <Typography variant="body2">{patient.has_no_phone ? "No phone (as the patient said)." : "No contact recorded."}</Typography>
        )}
        {patient.preferred_language && <Line label="Preferred language">{patient.preferred_language}</Line>}
      </Card>

      <Card title="Guardian and emergency contact">
        {people.map((person) => (
          <Line key={person.id} label={person.relation_label}>
            {person.name}
            {person.phone ? ` · ${person.phone}` : ""}
            {person.is_legal_guardian && <Chip size="small" label="Legal guardian" sx={{ ml: 1 }} />}
          </Line>
        ))}
        {people.length === 0 && <Typography variant="body2">Nobody recorded.</Typography>}
      </Card>

      <Card title="ID numbers">
        {ids.map((row) => (
          <Line key={row.id} label={row.kind_label}>
            <Box component="span" sx={{ fontFamily: "monospace" }}>
              {row.value_display}
            </Box>{" "}
            ({row.verification_label.toLowerCase()})
          </Line>
        ))}
        {ids.length === 0 && <Typography variant="body2">No ID numbers recorded.</Typography>}
      </Card>

      <Card title="Consent in force">
        {(["privacy_notice", "sms", "email"] as const).map((kind) => {
          const consent = consents.find((c) => c.kind === kind);
          return (
            <Line key={kind} label={CONSENT_KINDS[kind]}>
              {consent ? (
                <Chip size="small" color={CONSENT_STATUS[consent.status].color} label={CONSENT_STATUS[consent.status].label} />
              ) : (
                "Not recorded"
              )}
            </Line>
          );
        })}
      </Card>

      <Card title="Record">
        <Line label="Registered">
          {patient.registered_facility_name}, {dayTime(patient.created_at)}
          {patient.registered_by_name ? ` by ${patient.registered_by_name}` : ""}
        </Line>
        <Line label="Last changed">{dayTime(patient.updated_at)}</Line>
        <Line label="Date of birth">
          {day(patient.date_of_birth)}
          {patient.birth_date_estimated ? " (estimated)" : ""}
        </Line>
        {patient.blood_group_reported && <Line label="Blood group (reported)">{patient.blood_group_reported}</Line>}
        {patient.aliases.length > 0 && (
          <Line label="Earlier names">{patient.aliases.map((alias) => alias.name || alias.mrn).join("; ")}</Line>
        )}
      </Card>
    </Box>
  );
}
