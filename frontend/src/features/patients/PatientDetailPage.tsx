import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  LinearProgress,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { type ReactNode, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";

import type { PatientConsent, PatientContact, PatientIdentifier, PatientRelationship } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "../auth/api";
import { hasPermission } from "../auth/grants";
import { usePatient } from "./api";
import { CONSENT_KINDS, CONSENT_STATUS, MARITAL, SEX, day, dayTime } from "./labels";
import {
  AddIdentifierDialog,
  ConsentDialog,
  ContactDialog,
  EditDetailsDialog,
  EndDialog,
  EndIdentifierDialog,
  RelationshipDialog,
} from "./PatientDialogs";

type Dialog =
  | { type: "details" }
  | { type: "contact"; row?: PatientContact }
  | { type: "relationship"; row?: PatientRelationship }
  | { type: "end"; item: { type: "contact"; row: PatientContact } | { type: "relationship"; row: PatientRelationship } }
  | { type: "identifier" }
  | { type: "endIdentifier"; row: PatientIdentifier }
  | { type: "consent" };

function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Stack spacing={1}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        {action}
      </Box>
      {children}
    </Stack>
  );
}

function contactText(contact: PatientContact): string {
  if (contact.kind === "email") return contact.email;
  if (contact.kind === "address") {
    return [contact.address_line1, contact.address_line2, contact.city, contact.district, contact.state, contact.postal_code]
      .filter(Boolean)
      .join(", ");
  }
  return contact.phone;
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography>{value || "—"}</Typography>
    </Box>
  );
}

/** The latest decision of each kind: the consent in force (D9). */
function currentConsents(consents: PatientConsent[]): PatientConsent[] {
  const seen = new Set<string>();
  return consents.filter((consent) => !seen.has(consent.kind) && !!seen.add(consent.kind));
}

/** One patient's record (HIMS-PAT-001): details, contacts, people, ID numbers (masked), consents. */
export function PatientDetailPage() {
  const { id } = useParams();
  const { data: user } = useCurrentUser();
  const { data: patient, isPending, error } = usePatient(id);
  const [dialog, setDialog] = useState<Dialog>();
  const close = () => setDialog(undefined);
  // Hints only: the API checks every permission.
  const canChange = hasPermission(user, "patients.register") && patient?.status === "active";
  const us = user?.organization?.country === "US";

  if (isPending) return <LinearProgress />;
  if (error || !patient) return <ErrorAlert error={error} />;
  const contacts = patient.contacts.filter((c) => c.is_active);
  const pastContacts = patient.contacts.filter((c) => !c.is_active);
  const consentNow = currentConsents(patient.consents);
  const privacy = consentNow.find((c) => c.kind === "privacy_notice");

  return (
    <Stack spacing={3}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/patients" underline="hover">
          Patients
        </Link>
        <Typography color="text.primary">{patient.mrn}</Typography>
      </Breadcrumbs>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
          <Typography variant="h5" component="h1" sx={{ mr: 1 }}>
            {patient.name}
          </Typography>
          <Chip label={patient.mrn} />
          <Chip label={`${patient.birth_date_estimated ? "~" : ""}${patient.age} · ${SEX[patient.sex]}`} variant="outlined" />
          {patient.is_unknown && <Chip color="warning" label="Unknown patient" />}
          {patient.status === "merged" && <Chip color="default" label={`Merged into ${patient.merged_into_mrn}`} />}
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Registered at {patient.registered_facility_name} on {dayTime(patient.created_at)}
          {patient.registered_by_name ? ` by ${patient.registered_by_name}` : ""}. Allergies and visits come with the
          clinical record (Phase 2).
        </Typography>
      </Paper>
      {patient.needs_guardian && (
        <Alert severity="warning">Under 18 with no parent or guardian recorded. Add one under People.</Alert>
      )}
      {!privacy && <Alert severity="info">The privacy notice is not recorded yet. Record it under Consent.</Alert>}

      <Section title="Details" action={canChange && <Button onClick={() => setDialog({ type: "details" })}>Correct details</Button>}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" } }}>
            <Fact label="Date of birth" value={`${day(patient.date_of_birth)}${patient.birth_date_estimated ? " (estimated)" : ""}`} />
            <Fact label="Sex" value={SEX[patient.sex]} />
            {us && <Fact label="Gender identity" value={patient.gender_identity} />}
            {us && <Fact label="Pronouns" value={patient.pronouns} />}
            <Fact label="Preferred name" value={patient.preferred_name} />
            <Fact label="Preferred language" value={patient.preferred_language} />
            <Fact label="Marital status" value={patient.marital_status ? MARITAL[patient.marital_status] : ""} />
            <Fact label="Occupation" value={patient.occupation} />
            <Fact label="Blood group (reported)" value={patient.blood_group_reported} />
            {patient.is_unknown && <Fact label="How the patient arrived" value={patient.identification_note} />}
          </Box>
        </Paper>
        {patient.aliases.length > 0 && (
          <Typography variant="body2" color="text.secondary">
            Earlier names (still found by search): {patient.aliases.map((alias) => alias.name || alias.mrn).join("; ")}
          </Typography>
        )}
      </Section>

      <Section title="Contact" action={canChange && <Button onClick={() => setDialog({ type: "contact" })}>Add</Button>}>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Contact">
            <TableBody>
              {contacts.map((contact) => (
                <TableRow key={contact.id}>
                  <TableCell sx={{ width: 140 }}>{contact.kind_label}</TableCell>
                  <TableCell>
                    {contactText(contact)}
                    {contact.is_primary && <Chip size="small" label="Main" sx={{ ml: 1 }} />}
                  </TableCell>
                  <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                    {canChange && (
                      <>
                        <Button size="small" onClick={() => setDialog({ type: "contact", row: contact })}>
                          Change
                        </Button>
                        <Button size="small" color="error" onClick={() => setDialog({ type: "end", item: { type: "contact", row: contact } })}>
                          End
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {contacts.length === 0 && (
                <TableRow>
                  <TableCell colSpan={3}>{patient.has_no_phone ? "No phone (as the patient said)." : "No contact recorded."}</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
        {pastContacts.length > 0 && (
          <Typography variant="body2" color="text.secondary">
            Ended: {pastContacts.map(contactText).join("; ")}
          </Typography>
        )}
      </Section>

      <Section title="People" action={canChange && <Button onClick={() => setDialog({ type: "relationship" })}>Add a person</Button>}>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="People">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Relation</TableCell>
                <TableCell>Phone</TableCell>
                <TableCell>Role</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {patient.relationships.map((person) => (
                <TableRow key={person.id} sx={person.is_active ? undefined : { opacity: 0.6 }}>
                  <TableCell>{person.name}</TableCell>
                  <TableCell>{person.relation_label}</TableCell>
                  <TableCell>{person.phone || "—"}</TableCell>
                  <TableCell>
                    {[person.is_legal_guardian && "Legal guardian", person.is_emergency_contact && "Emergency contact", !person.is_active && "Ended"]
                      .filter(Boolean)
                      .join(", ") || "—"}
                  </TableCell>
                  <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                    {canChange && person.is_active && (
                      <>
                        <Button size="small" onClick={() => setDialog({ type: "relationship", row: person })}>
                          Change
                        </Button>
                        <Button size="small" color="error" onClick={() => setDialog({ type: "end", item: { type: "relationship", row: person } })}>
                          End
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {patient.relationships.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5}>Nobody recorded.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Section>

      <Section title="ID numbers" action={canChange && <Button onClick={() => setDialog({ type: "identifier" })}>Add</Button>}>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="ID numbers">
            <TableBody>
              {patient.identifiers.map((row) => (
                <TableRow key={row.id} sx={row.is_active ? undefined : { opacity: 0.6 }}>
                  <TableCell sx={{ width: 200 }}>{row.kind_label}</TableCell>
                  <TableCell sx={{ fontFamily: "monospace" }}>{row.value_display}</TableCell>
                  <TableCell>{row.issuer}</TableCell>
                  <TableCell>
                    {row.is_active ? (
                      <Chip size="small" label={row.verification_label} variant="outlined" />
                    ) : (
                      `Ended ${day(row.ended_at?.slice(0, 10))}: ${row.end_reason}`
                    )}
                  </TableCell>
                  <TableCell align="right">
                    {canChange && row.is_active && (
                      <Button size="small" color="error" onClick={() => setDialog({ type: "endIdentifier", row })}>
                        End
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {patient.identifiers.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5}>No ID numbers recorded.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Section>

      <Section title="Consent" action={canChange && <Button onClick={() => setDialog({ type: "consent" })}>Record</Button>}>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Consent">
            <TableHead>
              <TableRow>
                <TableCell>What</TableCell>
                <TableCell>Decision</TableCell>
                <TableCell>How</TableCell>
                <TableCell>Recorded</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {patient.consents.map((consent) => (
                <TableRow key={consent.id} sx={consentNow.includes(consent) ? undefined : { opacity: 0.6 }}>
                  <TableCell>{CONSENT_KINDS[consent.kind]}</TableCell>
                  <TableCell>
                    <Chip size="small" color={CONSENT_STATUS[consent.status].color} label={CONSENT_STATUS[consent.status].label} />
                    {!consentNow.includes(consent) && " (earlier)"}
                  </TableCell>
                  <TableCell>{consent.method_label}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>
                    {dayTime(consent.created_at)}
                    {consent.recorded_by_name ? ` · ${consent.recorded_by_name}` : ""}
                  </TableCell>
                </TableRow>
              ))}
              {patient.consents.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>No consent recorded.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Section>

      {dialog?.type === "details" && <EditDetailsDialog patient={patient} us={us} onClose={close} />}
      {dialog?.type === "contact" && <ContactDialog patientId={patient.id} contact={dialog.row} onClose={close} />}
      {dialog?.type === "relationship" && <RelationshipDialog patientId={patient.id} relationship={dialog.row} onClose={close} />}
      {dialog?.type === "end" && <EndDialog patientId={patient.id} item={dialog.item} onClose={close} />}
      {dialog?.type === "identifier" && <AddIdentifierDialog patientId={patient.id} onClose={close} />}
      {dialog?.type === "endIdentifier" && <EndIdentifierDialog patientId={patient.id} identifier={dialog.row} onClose={close} />}
      {dialog?.type === "consent" && <ConsentDialog patientId={patient.id} onClose={close} />}
    </Stack>
  );
}
