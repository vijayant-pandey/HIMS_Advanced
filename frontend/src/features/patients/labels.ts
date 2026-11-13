import type {
  BloodGroupEnum,
  ConsentMethodEnum,
  MaritalStatusEnum,
  PatientConsentKindEnum,
  PatientConsentStatusEnum,
  PatientRelationEnum,
  PatientSexEnum,
} from "../../api/types";

export const SEX: Record<PatientSexEnum, string> = {
  male: "Male",
  female: "Female",
  intersex: "Intersex",
  unknown: "Unknown",
};

/** What found a patient in a search (HIMS-PAT-002). */
export const MATCHED_ON: Record<string, string> = {
  mrn: "MRN",
  phone: "Phone",
  id_number: "ID number",
  name: "Name",
};

/** Short form for lists: "34 y F". */
export const SEX_SHORT: Record<PatientSexEnum, string> = { male: "M", female: "F", intersex: "I", unknown: "U" };

export const RELATIONS: Record<PatientRelationEnum, string> = {
  mother: "Mother",
  father: "Father",
  guardian: "Guardian",
  spouse: "Spouse / partner",
  child: "Son / daughter",
  sibling: "Brother / sister",
  next_of_kin: "Next of kin",
  caregiver: "Caregiver",
  emergency_contact: "Emergency contact",
  other: "Other",
};

export const MARITAL: Record<MaritalStatusEnum, string> = {
  single: "Single",
  married: "Married",
  divorced: "Divorced",
  separated: "Separated",
  widowed: "Widowed",
  other: "Other",
};

export const BLOOD_GROUPS: BloodGroupEnum[] = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"];

export const CONSENT_KINDS: Record<PatientConsentKindEnum, string> = {
  privacy_notice: "Privacy notice given; agrees to processing for care",
  sms: "Messages by SMS",
  email: "Messages by email",
};

export const CONSENT_STATUS: Record<PatientConsentStatusEnum, { label: string; color: "success" | "error" | "warning" }> = {
  given: { label: "Given", color: "success" },
  refused: { label: "Refused", color: "error" },
  withdrawn: { label: "Withdrawn", color: "warning" },
};

export const CONSENT_METHODS: Record<ConsentMethodEnum, string> = {
  verbal: "Told the front desk",
  signed_form: "Signed a form",
};

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const moment = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function day(value: string | null | undefined): string {
  return value ? when.format(new Date(`${value}T00:00:00`)) : "—";
}

export function dayTime(value: string | null | undefined): string {
  return value ? moment.format(new Date(value)) : "—";
}
