import { Checkbox, FormControlLabel, MenuItem, TextField, Typography } from "@mui/material";
import { useState } from "react";

import type {
  ConsentMethodEnum,
  PatientConsentKindEnum,
  PatientConsentStatusEnum,
  PatientContact,
  PatientContactKindEnum,
  PatientDetail,
  PatientIdentifier,
  PatientIdentifierKindEnum,
  PatientRelationEnum,
  PatientRelationship,
  PatientSexEnum,
} from "../../api/types";
import { FormDialog, fieldErrors } from "../../components/FormDialog";
import {
  useAddContact,
  useAddIdentifier,
  useAddRelationship,
  useEndIdentifier,
  useRecordConsent,
  useRegistrationOptions,
  useUpdateContact,
  useUpdatePatient,
  useUpdateRelationship,
} from "./api";
import { BLOOD_GROUPS, CONSENT_KINDS, CONSENT_METHODS, MARITAL, RELATIONS, SEX } from "./labels";

const DETAIL_FIELDS = [
  ["title", "Title"],
  ["given_name", "Given name"],
  ["middle_name", "Middle name"],
  ["family_name", "Family name"],
  ["preferred_name", "Preferred name"],
  ["occupation", "Occupation"],
  ["preferred_language", "Preferred language"],
] as const;

/** Correct the patient's details. A changed name stays findable as an earlier name. */
export function EditDetailsDialog({ patient, us, onClose }: { patient: PatientDetail; us: boolean; onClose: () => void }) {
  const update = useUpdatePatient(patient.id);
  const [values, setValues] = useState({
    title: patient.title,
    given_name: patient.given_name,
    middle_name: patient.middle_name,
    family_name: patient.family_name,
    preferred_name: patient.preferred_name,
    occupation: patient.occupation,
    preferred_language: patient.preferred_language,
    date_of_birth: patient.date_of_birth,
    birth_date_estimated: patient.birth_date_estimated,
    sex: patient.sex,
    gender_identity: patient.gender_identity,
    pronouns: patient.pronouns,
    marital_status: patient.marital_status as string,
    blood_group_reported: patient.blood_group_reported as string,
    is_unknown: patient.is_unknown,
    identification_note: patient.identification_note,
  });
  const errors = fieldErrors(update.error);
  const set = (change: Partial<typeof values>) => setValues((current) => ({ ...current, ...change }));
  return (
    <FormDialog
      title={`Correct details of ${patient.mrn}`}
      error={update.error}
      fields={Object.keys(values)}
      pending={update.isPending}
      onClose={onClose}
      onSubmit={() =>
        update.mutate(
          {
            version: patient.version,
            ...values,
            marital_status: values.marital_status as PatientDetail["marital_status"],
            blood_group_reported: values.blood_group_reported as PatientDetail["blood_group_reported"],
          },
          { onSuccess: onClose },
        )
      }
    >
      {DETAIL_FIELDS.map(([name, label]) => (
        <TextField
          key={name}
          label={label}
          value={values[name]}
          onChange={(event) => set({ [name]: event.target.value })}
          error={!!errors[name]}
          helperText={errors[name]}
        />
      ))}
      <TextField
        type="date"
        label="Date of birth"
        value={values.date_of_birth}
        onChange={(event) => set({ date_of_birth: event.target.value, birth_date_estimated: false })}
        error={!!errors.date_of_birth}
        helperText={errors.date_of_birth}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <FormControlLabel
        control={<Checkbox checked={values.birth_date_estimated} onChange={(event) => set({ birth_date_estimated: event.target.checked })} />}
        label="Date of birth is estimated"
      />
      <TextField select label="Sex" value={values.sex} onChange={(event) => set({ sex: event.target.value as PatientSexEnum })}>
        {Object.entries(SEX).map(([value, label]) => (
          <MenuItem key={value} value={value}>
            {label}
          </MenuItem>
        ))}
      </TextField>
      {us && (
        <TextField label="Gender identity" value={values.gender_identity} onChange={(event) => set({ gender_identity: event.target.value })} />
      )}
      {us && <TextField label="Pronouns" value={values.pronouns} onChange={(event) => set({ pronouns: event.target.value })} />}
      <TextField select label="Marital status" value={values.marital_status} onChange={(event) => set({ marital_status: event.target.value })}>
        <MenuItem value="">Not given</MenuItem>
        {Object.entries(MARITAL).map(([value, label]) => (
          <MenuItem key={value} value={value}>
            {label}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Blood group (as the patient says)"
        value={values.blood_group_reported}
        onChange={(event) => set({ blood_group_reported: event.target.value })}
      >
        <MenuItem value="">Not known</MenuItem>
        {BLOOD_GROUPS.map((group) => (
          <MenuItem key={group} value={group}>
            {group}
          </MenuItem>
        ))}
      </TextField>
      <FormControlLabel
        control={<Checkbox checked={values.is_unknown} onChange={(event) => set({ is_unknown: event.target.checked })} />}
        label="Unknown patient (not identified yet)"
      />
      {values.is_unknown && (
        <TextField
          label="How the patient arrived"
          value={values.identification_note}
          onChange={(event) => set({ identification_note: event.target.value })}
          error={!!errors.identification_note}
          helperText={errors.identification_note}
        />
      )}
    </FormDialog>
  );
}

const CONTACT_KINDS: Record<PatientContactKindEnum, string> = {
  mobile: "Mobile",
  phone: "Other phone",
  email: "Email",
  address: "Address",
};

const ADDRESS_FIELDS = [
  ["address_line1", "Address line 1"],
  ["address_line2", "Address line 2"],
  ["city", "City / town"],
  ["district", "District / county"],
  ["state", "State"],
  ["postal_code", "PIN / ZIP code"],
] as const;

/** Add a phone, email or address, or change one (ending it keeps it on record). */
export function ContactDialog({
  patientId,
  contact,
  onClose,
}: {
  patientId: string;
  contact?: PatientContact;
  onClose: () => void;
}) {
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const add = useAddContact(patientId, idempotencyKey);
  const update = useUpdateContact(patientId, contact?.id ?? "");
  const save = contact ? update : add;
  const [kind, setKind] = useState<PatientContactKindEnum>(contact?.kind ?? "mobile");
  const [values, setValues] = useState({
    phone: contact?.phone ?? "",
    email: contact?.email ?? "",
    address_line1: contact?.address_line1 ?? "",
    address_line2: contact?.address_line2 ?? "",
    city: contact?.city ?? "",
    district: contact?.district ?? "",
    state: contact?.state ?? "",
    postal_code: contact?.postal_code ?? "",
    is_primary: contact?.is_primary ?? true,
  });
  const errors = fieldErrors(save.error);
  const set = (change: Partial<typeof values>) => setValues((current) => ({ ...current, ...change }));
  const phone = kind === "mobile" || kind === "phone";
  return (
    <FormDialog
      title={contact ? `Change ${CONTACT_KINDS[contact.kind].toLowerCase()}` : "Add a phone, email or address"}
      error={save.error}
      fields={["kind", ...Object.keys(values)]}
      pending={save.isPending}
      onClose={onClose}
      onSubmit={() =>
        contact
          ? update.mutate({ version: contact.version, ...values }, { onSuccess: onClose })
          : add.mutate({ kind, ...values, country: "" }, { onSuccess: onClose })
      }
    >
      {!contact && (
        <TextField select label="Kind" value={kind} onChange={(event) => setKind(event.target.value as PatientContactKindEnum)}>
          {Object.entries(CONTACT_KINDS).map(([value, label]) => (
            <MenuItem key={value} value={value}>
              {label}
            </MenuItem>
          ))}
        </TextField>
      )}
      {phone && (
        <TextField label="Phone" value={values.phone} onChange={(event) => set({ phone: event.target.value })} error={!!errors.phone} helperText={errors.phone} />
      )}
      {kind === "email" && (
        <TextField label="Email" value={values.email} onChange={(event) => set({ email: event.target.value })} error={!!errors.email} helperText={errors.email} />
      )}
      {kind === "address" &&
        ADDRESS_FIELDS.map(([name, label]) => (
          <TextField
            key={name}
            label={label}
            value={values[name]}
            onChange={(event) => set({ [name]: event.target.value })}
            error={!!errors[name]}
            helperText={errors[name]}
          />
        ))}
      <FormControlLabel
        control={<Checkbox checked={values.is_primary} onChange={(event) => set({ is_primary: event.target.checked })} />}
        label="Main one of its kind"
      />
    </FormDialog>
  );
}

/** Add a parent, guardian, next of kin, emergency contact or caregiver. */
export function RelationshipDialog({
  patientId,
  relationship,
  onClose,
}: {
  patientId: string;
  relationship?: PatientRelationship;
  onClose: () => void;
}) {
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const add = useAddRelationship(patientId, idempotencyKey);
  const update = useUpdateRelationship(patientId, relationship?.id ?? "");
  const save = relationship ? update : add;
  const [values, setValues] = useState({
    relation: (relationship?.relation ?? "next_of_kin") as PatientRelationEnum,
    name: relationship?.name ?? "",
    phone: relationship?.phone ?? "",
    is_legal_guardian: relationship?.is_legal_guardian ?? false,
    is_emergency_contact: relationship?.is_emergency_contact ?? false,
    note: relationship?.note ?? "",
  });
  const errors = fieldErrors(save.error);
  const set = (change: Partial<typeof values>) => setValues((current) => ({ ...current, ...change }));
  return (
    <FormDialog
      title={relationship ? `Change ${relationship.name}` : "Add a person"}
      error={save.error}
      fields={Object.keys(values)}
      pending={save.isPending}
      submitDisabled={!values.name.trim()}
      onClose={onClose}
      onSubmit={() =>
        relationship
          ? update.mutate({ version: relationship.version, ...values }, { onSuccess: onClose })
          : add.mutate({ ...values, related_patient: null }, { onSuccess: onClose })
      }
    >
      <TextField select label="Relation" value={values.relation} onChange={(event) => set({ relation: event.target.value as PatientRelationEnum })}>
        {Object.entries(RELATIONS).map(([value, label]) => (
          <MenuItem key={value} value={value}>
            {label}
          </MenuItem>
        ))}
      </TextField>
      <TextField label="Name" required value={values.name} onChange={(event) => set({ name: event.target.value })} error={!!errors.name} helperText={errors.name} />
      <TextField label="Phone" value={values.phone} onChange={(event) => set({ phone: event.target.value })} error={!!errors.phone} helperText={errors.phone} />
      <FormControlLabel
        control={<Checkbox checked={values.is_legal_guardian} onChange={(event) => set({ is_legal_guardian: event.target.checked })} />}
        label="Legal guardian"
      />
      <FormControlLabel
        control={<Checkbox checked={values.is_emergency_contact} onChange={(event) => set({ is_emergency_contact: event.target.checked })} />}
        label="Emergency contact"
      />
      <TextField label="Note" value={values.note} onChange={(event) => set({ note: event.target.value })} helperText="No clinical details." />
    </FormDialog>
  );
}

/** End a contact or relationship: it stays on record as ended. */
export function EndDialog({
  patientId,
  item,
  onClose,
}: {
  patientId: string;
  item: { type: "contact"; row: PatientContact } | { type: "relationship"; row: PatientRelationship };
  onClose: () => void;
}) {
  const contact = useUpdateContact(patientId, item.type === "contact" ? item.row.id : "");
  const relationship = useUpdateRelationship(patientId, item.type === "relationship" ? item.row.id : "");
  const save = item.type === "contact" ? contact : relationship;
  return (
    <FormDialog
      title="End it?"
      error={save.error}
      submitLabel="End"
      submitColor="error"
      pending={save.isPending}
      onClose={onClose}
      maxWidth="xs"
      onSubmit={() =>
        item.type === "contact"
          ? contact.mutate({ version: item.row.version, is_active: false }, { onSuccess: onClose })
          : relationship.mutate({ version: item.row.version, is_active: false }, { onSuccess: onClose })
      }
    >
      <Typography>It is kept on the record as ended, not deleted.</Typography>
    </FormDialog>
  );
}

/** Add an ID number: checked, stored encrypted, shown masked. */
export function AddIdentifierDialog({ patientId, onClose }: { patientId: string; onClose: () => void }) {
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const add = useAddIdentifier(patientId, idempotencyKey);
  const kinds = useRegistrationOptions().data?.identifier_kinds ?? [];
  const [kind, setKind] = useState<PatientIdentifierKindEnum | "">("");
  const [value, setValue] = useState("");
  const [issuer, setIssuer] = useState("");
  const chosen = kinds.find((k) => k.kind === (kind || kinds[0]?.kind));
  const errors = fieldErrors(add.error);
  return (
    <FormDialog
      title="Add an ID number"
      error={add.error}
      fields={["kind", "value", "issuer"]}
      submitLabel="Add"
      submitDisabled={!value.trim() || !chosen}
      pending={add.isPending}
      onClose={onClose}
      onSubmit={() =>
        chosen && add.mutate({ kind: chosen.kind as PatientIdentifierKindEnum, value, issuer, valid_until: null }, { onSuccess: onClose })
      }
    >
      <TextField select label="Kind" value={chosen?.kind ?? ""} onChange={(event) => setKind(event.target.value as PatientIdentifierKindEnum)}>
        {kinds.map((k) => (
          <MenuItem key={k.kind} value={k.kind}>
            {k.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        label="Number"
        value={value}
        autoComplete="off"
        placeholder={chosen?.example}
        onChange={(event) => setValue(event.target.value)}
        error={!!errors.value}
        helperText={errors.value ?? "Stored encrypted; only the last 4 are shown. Marked not verified."}
      />
      {chosen?.needs_issuer && (
        <TextField label="Which hospital" value={issuer} onChange={(event) => setIssuer(event.target.value)} error={!!errors.issuer} helperText={errors.issuer} />
      )}
    </FormDialog>
  );
}

/** End a wrong or replaced ID number, with a reason. */
export function EndIdentifierDialog({ patientId, identifier, onClose }: { patientId: string; identifier: PatientIdentifier; onClose: () => void }) {
  const end = useEndIdentifier(patientId, identifier.id);
  const [reason, setReason] = useState("");
  const errors = fieldErrors(end.error);
  return (
    <FormDialog
      title={`End ${identifier.kind_label} ${identifier.value_display}`}
      error={end.error}
      fields={["reason"]}
      submitLabel="End"
      submitColor="error"
      submitDisabled={!reason.trim()}
      pending={end.isPending}
      onClose={onClose}
      maxWidth="xs"
      onSubmit={() => end.mutate({ version: identifier.version, reason }, { onSuccess: onClose })}
    >
      <TextField
        label="Reason"
        required
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        error={!!errors.reason}
        helperText={errors.reason ?? "e.g. Typing mistake. It stays on record as ended."}
      />
    </FormDialog>
  );
}

/** Record a new consent decision; earlier ones stay as history. */
export function ConsentDialog({
  patientId,
  kind: startKind,
  onClose,
}: {
  patientId: string;
  kind?: PatientConsentKindEnum;
  onClose: () => void;
}) {
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const record = useRecordConsent(patientId, idempotencyKey);
  const [kind, setKind] = useState<PatientConsentKindEnum>(startKind ?? "privacy_notice");
  const [status, setStatus] = useState<PatientConsentStatusEnum>("given");
  const [method, setMethod] = useState<ConsentMethodEnum>("verbal");
  const [note, setNote] = useState("");
  return (
    <FormDialog
      title="Record consent"
      error={record.error}
      fields={["kind", "status", "method", "note"]}
      pending={record.isPending}
      onClose={onClose}
      onSubmit={() => record.mutate({ kind, status, method, note }, { onSuccess: onClose })}
    >
      <TextField select label="What" value={kind} onChange={(event) => setKind(event.target.value as PatientConsentKindEnum)}>
        {Object.entries(CONSENT_KINDS).map(([value, label]) => (
          <MenuItem key={value} value={value}>
            {label}
          </MenuItem>
        ))}
      </TextField>
      <TextField select label="Decision" value={status} onChange={(event) => setStatus(event.target.value as PatientConsentStatusEnum)}>
        <MenuItem value="given">Given</MenuItem>
        <MenuItem value="refused">Refused</MenuItem>
        <MenuItem value="withdrawn">Withdrawn</MenuItem>
      </TextField>
      <TextField select label="How" value={method} onChange={(event) => setMethod(event.target.value as ConsentMethodEnum)}>
        {Object.entries(CONSENT_METHODS).map(([value, label]) => (
          <MenuItem key={value} value={value}>
            {label}
          </MenuItem>
        ))}
      </TextField>
      <TextField label="Note" value={note} onChange={(event) => setNote(event.target.value)} helperText="No clinical details." />
    </FormDialog>
  );
}
