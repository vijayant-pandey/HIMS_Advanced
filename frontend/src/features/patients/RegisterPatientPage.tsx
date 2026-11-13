import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Checkbox,
  FormControlLabel,
  IconButton,
  Link,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { type ReactNode, useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";

import type {
  ConsentMethodEnum,
  PatientIdentifierKindEnum,
  PatientRegisterRequest,
  PatientRelationEnum,
  PatientSexEnum,
} from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { fieldErrors } from "../../components/FormDialog";
import { useCurrentUser } from "../auth/api";
import { hasPermissionAt } from "../auth/grants";
import { useFacilities } from "../facilities/api";
import { useRegisterPatient, useRegistrationOptions } from "./api";
import { BLOOD_GROUPS, CONSENT_METHODS, MARITAL, RELATIONS, SEX } from "./labels";

type BirthMode = "date" | "years" | "months" | "days";

interface Person {
  relation: PatientRelationEnum;
  name: string;
  phone: string;
  is_legal_guardian: boolean;
  is_emergency_contact: boolean;
}

interface IdNumber {
  kind: PatientIdentifierKindEnum | "";
  value: string;
  issuer: string;
}

const GUARDIANS: PatientRelationEnum[] = ["mother", "father", "guardian"];

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        {children}
      </Stack>
    </Paper>
  );
}

const row = { display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "repeat(auto-fill, minmax(200px, 1fr))" } };

/** Registration (HIMS-PAT-001; P0 part 01 section 1). Required: a name, sex, date of birth or age, a mobile or "no phone". */
export function RegisterPatientPage() {
  const navigate = useNavigate();
  const { data: user } = useCurrentUser();
  const facilities = (useFacilities().data?.results ?? []).filter((item) =>
    hasPermissionAt(user, "patients.register", item.id),
  );
  const options = useRegistrationOptions().data;
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const register = useRegisterPatient(idempotencyKey);
  const errors = fieldErrors(register.error);
  const us = options?.country === "US";

  const [facility, setFacility] = useState("");
  const [unknown, setUnknown] = useState(false);
  const [names, setNames] = useState({ title: "", given_name: "", middle_name: "", family_name: "", preferred_name: "" });
  const [birthMode, setBirthMode] = useState<BirthMode>("date");
  const [birth, setBirth] = useState({ date: "", age: "" });
  const [sex, setSex] = useState<PatientSexEnum | "">("");
  const [more, setMore] = useState({
    gender_identity: "",
    pronouns: "",
    preferred_language: "",
    marital_status: "",
    occupation: "",
    blood_group_reported: "",
    identification_note: "",
  });
  const [contact, setContact] = useState({ mobile: "", alternate_phone: "", email: "" });
  const [noPhone, setNoPhone] = useState(false);
  const [address, setAddress] = useState({
    address_line1: "",
    address_line2: "",
    city: "",
    district: "",
    state: "",
    postal_code: "",
  });
  const [people, setPeople] = useState<Person[]>([]);
  const [ids, setIds] = useState<IdNumber[]>([]);
  const [noGuardianReason, setNoGuardianReason] = useState("");
  const [privacy, setPrivacy] = useState(true);
  const [sms, setSms] = useState(false);
  const [emailConsent, setEmailConsent] = useState(false);
  const [method, setMethod] = useState<ConsentMethodEnum>("verbal");

  const facilityId = facility || facilities[0]?.id || "";
  const ageYears = birthMode === "years" ? Number(birth.age) : birthMode === "date" && birth.date ? yearsSince(birth.date) : 99;
  const child = !unknown && (birthMode === "months" || birthMode === "days" || ageYears < 18);
  const hasGuardian = people.some((p) => p.is_legal_guardian || GUARDIANS.includes(p.relation));
  const kinds = options?.identifier_kinds ?? [];

  const text = (value: string, onChange: (value: string) => void, label: string, field: string, extra: object = {}) => (
    <TextField
      label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      error={!!errors[field]}
      helperText={errors[field]}
      {...extra}
    />
  );

  const submit = () => {
    const age = birth.age === "" ? null : Number(birth.age);
    const body: PatientRegisterRequest = {
      facility: facilityId,
      ...names,
      date_of_birth: birthMode === "date" && birth.date ? birth.date : null,
      age_years: birthMode === "years" ? age : null,
      age_months: birthMode === "months" ? age : null,
      age_days: birthMode === "days" ? age : null,
      sex: sex as PatientSexEnum, // empty is refused by the server with a message next to Sex
      ...more,
      marital_status: more.marital_status as PatientRegisterRequest["marital_status"],
      blood_group_reported: more.blood_group_reported as PatientRegisterRequest["blood_group_reported"],
      is_unknown: unknown,
      mobile: noPhone ? "" : contact.mobile,
      has_no_phone: noPhone,
      alternate_phone: contact.alternate_phone,
      email: contact.email,
      ...address,
      country: "",
      relationships: people.map((person) => ({ ...person, note: "" })),
      identifiers: ids
        .filter((item) => item.kind && item.value.trim())
        .map((item) => ({ kind: item.kind as PatientIdentifierKindEnum, value: item.value, issuer: item.issuer })),
      privacy_notice: privacy ? "given" : "",
      sms_consent: sms,
      email_consent: contact.email ? emailConsent : null,
      consent_method: method,
      no_guardian_reason: child && !hasGuardian ? noGuardianReason : "",
    };
    register.mutate(body, { onSuccess: (patient) => navigate(`/patients/${patient.id}`) });
  };

  const shown = new Set([
    "facility", "title", "given_name", "middle_name", "family_name", "preferred_name", "date_of_birth", "sex",
    "gender_identity", "pronouns", "preferred_language", "marital_status", "occupation", "blood_group_reported",
    "identification_note", "mobile", "alternate_phone", "email", "address_line1", "address_line2", "city", "district",
    "state", "postal_code", "relationships", "no_guardian_reason",
  ]);
  const listErrors = Object.keys(errors).some((name) => name.startsWith("relationships[") || name.startsWith("identifiers["));
  const elsewhere = Object.keys(errors).some((name) => !shown.has(name) && !name.includes("["));
  const showTop = !!register.error && (Object.keys(errors).length === 0 || elsewhere);

  return (
    <Stack spacing={2} component="form" noValidate onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/patients" underline="hover">
          Patients
        </Link>
        <Typography color="text.primary">Register</Typography>
      </Breadcrumbs>
      <Box>
        <Typography variant="h5" component="h1">
          Register new patient
        </Typography>
        <Typography variant="body2">
          Look the patient up first so nobody is registered twice. The MRN is given when you save. Required: a name, sex,
          the date of birth or age, and a mobile number or "No phone".
        </Typography>
      </Box>
      {showTop && <ErrorAlert error={register.error} />}
      {listErrors && <Alert severity="error">Check the people and ID numbers below.</Alert>}

      <Block title="Person">
        {facilities.length > 1 && (
          <TextField
            select
            label="Registered at"
            value={facilityId}
            onChange={(event) => setFacility(event.target.value)}
            error={!!errors.facility}
            helperText={errors.facility}
            sx={{ maxWidth: 360 }}
          >
            {facilities.map((item) => (
              <MenuItem key={item.id} value={item.id}>
                {item.name}
              </MenuItem>
            ))}
          </TextField>
        )}
        <FormControlLabel
          control={<Checkbox checked={unknown} onChange={(event) => setUnknown(event.target.checked)} />}
          label="Unknown or unconscious patient (details completed later)"
        />
        {unknown &&
          text(more.identification_note, (v) => setMore({ ...more, identification_note: v }), "How the patient arrived", "identification_note", {
            required: true,
            placeholder: "e.g. Brought by ambulance from MG Road",
          })}
        <Box sx={row}>
          {text(names.title, (v) => setNames({ ...names, title: v }), "Title", "title")}
          {text(names.given_name, (v) => setNames({ ...names, given_name: v }), "Given name", "given_name", {
            required: !unknown,
          })}
          {text(names.middle_name, (v) => setNames({ ...names, middle_name: v }), "Middle name", "middle_name")}
          {text(names.family_name, (v) => setNames({ ...names, family_name: v }), "Family name", "family_name")}
          {text(names.preferred_name, (v) => setNames({ ...names, preferred_name: v }), "Preferred name", "preferred_name")}
        </Box>
        <RadioGroup row value={birthMode} onChange={(event) => setBirthMode(event.target.value as BirthMode)} aria-label="Birth">
          <FormControlLabel value="date" control={<Radio />} label="Date of birth" />
          <FormControlLabel value="years" control={<Radio />} label="Age in years" />
          <FormControlLabel value="months" control={<Radio />} label="Months (baby)" />
          <FormControlLabel value="days" control={<Radio />} label="Days (newborn)" />
        </RadioGroup>
        <Box sx={row}>
          {birthMode === "date" ? (
            <TextField
              type="date"
              label="Date of birth"
              required
              value={birth.date}
              onChange={(event) => setBirth({ ...birth, date: event.target.value })}
              error={!!errors.date_of_birth}
              helperText={errors.date_of_birth}
              slotProps={{ inputLabel: { shrink: true } }}
            />
          ) : (
            <TextField
              type="number"
              label={{ years: "Age (years)", months: "Age (months)", days: "Age (days)" }[birthMode]}
              required
              value={birth.age}
              onChange={(event) => setBirth({ ...birth, age: event.target.value })}
              error={!!errors.date_of_birth}
              helperText={errors.date_of_birth ?? "The date of birth is saved as estimated"}
            />
          )}
          <TextField
            select
            label="Sex"
            required
            value={sex}
            onChange={(event) => setSex(event.target.value as PatientSexEnum)}
            error={!!errors.sex}
            helperText={errors.sex}
          >
            {Object.entries(SEX).map(([value, label]) => (
              <MenuItem key={value} value={value}>
                {label}
              </MenuItem>
            ))}
          </TextField>
          {us && text(more.gender_identity, (v) => setMore({ ...more, gender_identity: v }), "Gender identity (optional)", "gender_identity")}
          {us && text(more.pronouns, (v) => setMore({ ...more, pronouns: v }), "Pronouns (optional)", "pronouns")}
        </Box>
        <Box sx={row}>
          {text(more.preferred_language, (v) => setMore({ ...more, preferred_language: v }), "Preferred language", "preferred_language", {
            placeholder: us ? "e.g. en-US, es" : "e.g. hi, en",
          })}
          <TextField
            select
            label="Marital status"
            value={more.marital_status}
            onChange={(event) => setMore({ ...more, marital_status: event.target.value })}
          >
            <MenuItem value="">Not given</MenuItem>
            {Object.entries(MARITAL).map(([value, label]) => (
              <MenuItem key={value} value={value}>
                {label}
              </MenuItem>
            ))}
          </TextField>
          {text(more.occupation, (v) => setMore({ ...more, occupation: v }), "Occupation", "occupation")}
          <TextField
            select
            label="Blood group (as the patient says)"
            value={more.blood_group_reported}
            onChange={(event) => setMore({ ...more, blood_group_reported: event.target.value })}
          >
            <MenuItem value="">Not known</MenuItem>
            {BLOOD_GROUPS.map((group) => (
              <MenuItem key={group} value={group}>
                {group}
              </MenuItem>
            ))}
          </TextField>
        </Box>
      </Block>

      <Block title="Contact">
        <Box sx={row}>
          {text(contact.mobile, (v) => setContact({ ...contact, mobile: v }), "Mobile", "mobile", {
            required: !noPhone && !unknown,
            disabled: noPhone,
            placeholder: us ? "(312) 555-0142" : "98765 43210",
          })}
          {text(contact.alternate_phone, (v) => setContact({ ...contact, alternate_phone: v }), "Other phone", "alternate_phone")}
          {text(contact.email, (v) => setContact({ ...contact, email: v }), "Email", "email", { type: "email" })}
        </Box>
        <FormControlLabel
          control={<Checkbox checked={noPhone} onChange={(event) => setNoPhone(event.target.checked)} />}
          label="No phone"
        />
        <Typography variant="body2" color="text.secondary">
          Address (optional; give the state when you give an address)
        </Typography>
        <Box sx={row}>
          {text(address.address_line1, (v) => setAddress({ ...address, address_line1: v }), "Address line 1", "address_line1")}
          {text(address.address_line2, (v) => setAddress({ ...address, address_line2: v }), "Address line 2", "address_line2")}
          {text(address.city, (v) => setAddress({ ...address, city: v }), "City / town", "city")}
          {text(address.district, (v) => setAddress({ ...address, district: v }), us ? "County" : "District", "district")}
          {text(address.state, (v) => setAddress({ ...address, state: v }), "State", "state")}
          {text(address.postal_code, (v) => setAddress({ ...address, postal_code: v }), us ? "ZIP code" : "PIN code", "postal_code")}
        </Box>
      </Block>

      <Block title="People: parent or guardian, next of kin, emergency contact">
        {errors.relationships && <Alert severity="warning">{errors.relationships}</Alert>}
        {people.map((person, n) => {
          const set = (change: Partial<Person>) => setPeople(people.map((p, i) => (i === n ? { ...p, ...change } : p)));
          return (
            <Box key={n} sx={{ ...row, alignItems: "center" }}>
              <TextField
                select
                label="Relation"
                value={person.relation}
                onChange={(event) => set({ relation: event.target.value as PatientRelationEnum })}
              >
                {Object.entries(RELATIONS).map(([value, label]) => (
                  <MenuItem key={value} value={value}>
                    {label}
                  </MenuItem>
                ))}
              </TextField>
              {text(person.name, (v) => set({ name: v }), "Name", `relationships[${n}].name`)}
              {text(person.phone, (v) => set({ phone: v }), "Phone", `relationships[${n}].phone`)}
              <FormControlLabel
                control={<Checkbox checked={person.is_legal_guardian} onChange={(event) => set({ is_legal_guardian: event.target.checked })} />}
                label="Legal guardian"
              />
              <FormControlLabel
                control={
                  <Checkbox checked={person.is_emergency_contact} onChange={(event) => set({ is_emergency_contact: event.target.checked })} />
                }
                label="Emergency contact"
              />
              <IconButton aria-label={`Remove person ${n + 1}`} onClick={() => setPeople(people.filter((_, i) => i !== n))}>
                ✕
              </IconButton>
            </Box>
          );
        })}
        <Box>
          <Button
            onClick={() =>
              setPeople([
                ...people,
                { relation: child ? "mother" : "next_of_kin", name: "", phone: "", is_legal_guardian: child, is_emergency_contact: true },
              ])
            }
          >
            Add a person
          </Button>
        </Box>
        {child && !hasGuardian && (
          <TextField
            label="No parent or guardian with the patient: why"
            value={noGuardianReason}
            onChange={(event) => setNoGuardianReason(event.target.value)}
            error={!!errors.no_guardian_reason}
            helperText={errors.no_guardian_reason ?? "Under 18: add a parent or guardian, or say why not (e.g. emergency)."}
          />
        )}
      </Block>

      <Block title="ID numbers">
        <Typography variant="body2" color="text.secondary">
          Stored encrypted and shown masked (last 4 only). Typed numbers are marked "not verified".
        </Typography>
        {ids.map((item, n) => {
          const set = (change: Partial<IdNumber>) => setIds(ids.map((p, i) => (i === n ? { ...p, ...change } : p)));
          const kind = kinds.find((k) => k.kind === item.kind);
          return (
            <Box key={n} sx={{ ...row, alignItems: "center" }}>
              <TextField select label="Kind" value={item.kind} onChange={(event) => set({ kind: event.target.value as PatientIdentifierKindEnum })}>
                {kinds.map((k) => (
                  <MenuItem key={k.kind} value={k.kind}>
                    {k.label}
                  </MenuItem>
                ))}
              </TextField>
              {text(item.value, (v) => set({ value: v }), "Number", `identifiers[${n}].value`, {
                placeholder: kind?.example,
                autoComplete: "off",
              })}
              {kind?.needs_issuer && text(item.issuer, (v) => set({ issuer: v }), "Which hospital", `identifiers[${n}].issuer`)}
              <IconButton aria-label={`Remove ID number ${n + 1}`} onClick={() => setIds(ids.filter((_, i) => i !== n))}>
                ✕
              </IconButton>
            </Box>
          );
        })}
        <Box>
          <Button onClick={() => setIds([...ids, { kind: (kinds[0]?.kind ?? "") as IdNumber["kind"], value: "", issuer: "" }])} disabled={!kinds.length}>
            Add an ID number
          </Button>
        </Box>
      </Block>

      <Block title="Consent">
        <FormControlLabel
          control={<Checkbox checked={privacy} onChange={(event) => setPrivacy(event.target.checked)} />}
          label="Privacy notice given; the patient agrees to their data being used for their care"
        />
        <FormControlLabel
          control={<Checkbox checked={sms} onChange={(event) => setSms(event.target.checked)} />}
          label="Agrees to messages by SMS"
        />
        {contact.email && (
          <FormControlLabel
            control={<Checkbox checked={emailConsent} onChange={(event) => setEmailConsent(event.target.checked)} />}
            label="Agrees to messages by email"
          />
        )}
        <TextField
          select
          label="How"
          value={method}
          onChange={(event) => setMethod(event.target.value as ConsentMethodEnum)}
          sx={{ maxWidth: 360 }}
        >
          {Object.entries(CONSENT_METHODS).map(([value, label]) => (
            <MenuItem key={value} value={value}>
              {label}
            </MenuItem>
          ))}
        </TextField>
      </Block>

      <Stack direction="row" spacing={1}>
        <Button type="submit" variant="contained" disabled={register.isPending || !facilityId}>
          Register
        </Button>
        <Button component={RouterLink} to="/patients">
          Cancel
        </Button>
      </Stack>
    </Stack>
  );
}

function yearsSince(isoDate: string): number {
  const born = new Date(`${isoDate}T00:00:00`);
  const now = new Date();
  let years = now.getFullYear() - born.getFullYear();
  if (now.getMonth() < born.getMonth() || (now.getMonth() === born.getMonth() && now.getDate() < born.getDate())) years -= 1;
  return years;
}
