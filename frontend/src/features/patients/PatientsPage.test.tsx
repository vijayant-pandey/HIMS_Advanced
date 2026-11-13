import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CurrentUser, PatientDetail, PatientListItem } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { PatientDetailPage } from "./PatientDetailPage";
import { PatientsPage } from "./PatientsPage";
import { RegisterPatientPage } from "./RegisterPatientPage";

// Invented people and numbers only.
const ROW: PatientListItem = {
  id: "p1",
  mrn: "MRN-00000001",
  name: "Asha Verma",
  sex: "female",
  age: "34 y",
  birth_date_estimated: true,
  phone_last4: "…3210",
  is_unknown: false,
  status: "active",
  registered_facility: "f1",
  registered_facility_name: "Facility A",
  created_at: "2026-11-12T05:00:00Z",
  matched_on: null,
};

const DETAIL: PatientDetail = {
  id: "p1",
  mrn: "MRN-00000001",
  status: "active",
  merged_into: null,
  merged_into_mrn: null,
  name: "Asha Verma",
  title: "",
  given_name: "Asha",
  middle_name: "",
  family_name: "Verma",
  preferred_name: "",
  date_of_birth: "2015-07-01",
  birth_date_estimated: true,
  age: "11 y",
  sex: "female",
  gender_identity: "",
  pronouns: "",
  preferred_language: "hi",
  marital_status: "" as PatientDetail["marital_status"], // not given (blank)
  occupation: "",
  blood_group_reported: "B+",
  has_no_phone: false,
  is_unknown: false,
  identification_note: "",
  registered_facility: "f1",
  registered_facility_name: "Facility A",
  registered_by_name: "Front Desk",
  needs_guardian: true,
  contacts: [
    {
      id: "c1",
      kind: "mobile",
      kind_label: "Mobile",
      phone: "+919876543210",
      email: "",
      address_line1: "",
      address_line2: "",
      city: "",
      district: "",
      state: "",
      postal_code: "",
      country: "",
      is_primary: true,
      is_active: true,
      version: 1,
      created_at: "2026-11-12T05:00:00Z",
    },
  ],
  relationships: [],
  identifiers: [
    {
      id: "i1",
      kind: "aadhaar",
      kind_label: "Aadhaar number",
      value_display: "XXXX XXXX 1234",
      issuer: "",
      verification: "unverified",
      verification_label: "Not verified",
      valid_until: null,
      is_active: true,
      ended_at: null,
      ended_by_name: null,
      end_reason: "",
      version: 1,
      created_at: "2026-11-12T05:00:00Z",
    },
  ],
  consents: [
    {
      id: "k2",
      kind: "sms",
      kind_label: "Messages by SMS",
      status: "withdrawn",
      status_label: "Withdrawn",
      method: "verbal",
      method_label: "Told the front desk",
      note: "",
      recorded_by_name: "Front Desk",
      created_at: "2026-11-12T06:00:00Z",
    },
    {
      id: "k1",
      kind: "sms",
      kind_label: "Messages by SMS",
      status: "given",
      status_label: "Given",
      method: "verbal",
      method_label: "Told the front desk",
      note: "",
      recorded_by_name: "Front Desk",
      created_at: "2026-11-12T05:00:00Z",
    },
  ],
  aliases: [],
  version: 1,
  created_at: "2026-11-12T05:00:00Z",
  updated_at: "2026-11-12T05:00:00Z",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Grant = CurrentUser["grants"][number];
const grant = (permission: string, facility_id: string | null = null): Grant => ({ permission, facility_id, department_id: null });
const DESK = [grant("patients.search"), grant("patients.view"), grant("patients.register", "f1"), grant("facilities.view")];
const ADMIN = [grant("patients.search"), grant("patients.view"), grant("facilities.view")];

function user(grants: Grant[]): CurrentUser {
  return {
    id: "u1",
    email: "desk@synthetic.test",
    display_name: "Synthetic Desk",
    staff_member_id: null,
    grants,
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: false, required: false, verified: true, recovery_codes_remaining: 0, passkeys: 0 },
  };
}

function renderAt(path: string, grants: Grant[], answer?: (url: string, init?: RequestInit) => Response | undefined) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const custom = answer?.(url, init);
    if (custom) return custom;
    if (url.includes("/registration-options/")) {
      return json({
        country: "IN",
        identifier_kinds: [
          { kind: "aadhaar", label: "Aadhaar number", example: "1234 5678 9012", needs_issuer: false, one_per_person: true },
          { kind: "previous_mrn", label: "Previous hospital's MRN", example: "OLD-000123", needs_issuer: true, one_per_person: false },
        ],
      });
    }
    if (url.includes("/facilities/")) {
      return json({ count: 1, next: null, previous: null, results: [{ id: "f1", name: "Facility A" }] });
    }
    if (url.match(/\/patients\/p1\/$/)) return json(DETAIL);
    if (init?.method === "POST" && url.endsWith("/patients/")) return json(DETAIL, 201);
    if (init?.method === "POST") return json({}, 201);
    return json({ count: 1, next: null, previous: null, results: [ROW] });
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user(grants));
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/patients" element={<PatientsPage />} />
          <Route path="/patients/register" element={<RegisterPatientPage />} />
          <Route path="/patients/:id" element={<PatientDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const sentTo = (fetchMock: ReturnType<typeof renderAt>, ending: string) => {
  const call = fetchMock.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith(ending));
  return call ? (JSON.parse(String(call[1]?.body)) as Record<string, unknown>) : undefined;
};

// The registration form is long (many fields to fill): over 5 s when the whole suite runs at once.
describe("Patients (HIMS-PAT-001)", { timeout: 20_000 }, () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the minimum, then searches by a name spelt another way with sex and age (HIMS-PAT-002)", async () => {
    const fetchMock = renderAt("/patients", DESK, (url) =>
      url.includes("search=") ? json({ count: 1, next: null, previous: null, results: [{ ...ROW, matched_on: "name" }] }) : undefined,
    );
    const table = await screen.findByRole("table", { name: "Patients" });
    const row = (await within(table).findByRole("link", { name: "MRN-00000001" })).closest("tr")!;
    expect(row).toHaveTextContent("Asha Verma");
    expect(row).toHaveTextContent("~34 y F");
    expect(row).toHaveTextContent("…3210");
    expect(screen.getByRole("heading", { name: "Newest registrations" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Search" }), { target: { value: " aasha  " } });
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Sex" }));
    fireEvent.click(await screen.findByRole("option", { name: "Female" }));
    fireEvent.change(screen.getByRole("spinbutton", { name: "Age (years)" }), { target: { value: "34" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByRole("heading", { name: "Search results" });
    const url = String(fetchMock.mock.calls.map(([called]) => called).find((called) => String(called).includes("search=")));
    expect(url).toContain("search=aasha");
    expect(url).toContain("sex=female");
    expect(url).toContain("age=34");
    expect(url).not.toContain("page="); // at most 50, best first: no pages
    const found = (await within(table).findByRole("link", { name: "MRN-00000001" })).closest("tr")!;
    expect(found).toHaveTextContent("Name"); // found by
    expect(screen.getByRole("link", { name: "Register new patient" })).toBeInTheDocument();
  });

  it("asks for more detail when more than 50 match, and offers registration when nobody does", async () => {
    let answer = { count: 75, next: null, previous: null, results: [ROW] };
    renderAt("/patients", DESK, (url) => (url.includes("search=") ? json(answer) : undefined));
    await screen.findByRole("link", { name: "MRN-00000001" });
    fireEvent.change(screen.getByRole("textbox", { name: "Search" }), { target: { value: "verma" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/75 patients match; the best 1 are shown/)).toBeInTheDocument();
    answer = { count: 0, next: null, previous: null, results: [] };
    fireEvent.change(screen.getByRole("textbox", { name: "Search" }), { target: { value: "zebedee" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/No patient found/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Register new patient" })).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(await screen.findByRole("heading", { name: "Newest registrations" })).toBeInTheDocument();
  });

  it("does not offer registration without the permission", async () => {
    renderAt("/patients", ADMIN);
    await screen.findByRole("link", { name: "MRN-00000001" });
    expect(screen.queryByRole("link", { name: "Register new patient" })).not.toBeInTheDocument();
  });

  it("registers with an age, a mobile and an ID number, then opens the record", async () => {
    const fetchMock = renderAt("/patients/register", DESK);
    await screen.findByRole("heading", { name: "Register new patient" });
    fireEvent.change(screen.getByLabelText(/Given name/), { target: { value: "Asha" } });
    fireEvent.change(screen.getByLabelText("Family name"), { target: { value: "Verma" } });
    fireEvent.click(screen.getByLabelText("Age in years"));
    fireEvent.change(screen.getByLabelText(/Age \(years\)/), { target: { value: "34" } });
    fireEvent.mouseDown(screen.getByLabelText(/^Sex/));
    fireEvent.click(await screen.findByRole("option", { name: "Female" }));
    fireEvent.change(screen.getByLabelText(/^Mobile/), { target: { value: "98765 43210" } });
    fireEvent.click(screen.getByRole("button", { name: "Add an ID number" }));
    fireEvent.change(screen.getByLabelText("Number"), { target: { value: "2999 9000 0119" } });
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    await screen.findByRole("heading", { name: "Asha Verma" }); // the record opens
    const body = sentTo(fetchMock, "/patients/")!;
    expect(body).toMatchObject({
      facility: "f1",
      given_name: "Asha",
      family_name: "Verma",
      age_years: 34,
      date_of_birth: null,
      sex: "female",
      mobile: "98765 43210",
      privacy_notice: "given",
      identifiers: [{ kind: "aadhaar", value: "2999 9000 0119", issuer: "" }],
    });
  });

  it("shows the server's message next to the field and asks why a child has no guardian", async () => {
    renderAt("/patients/register", DESK, (url, init) =>
      init?.method === "POST" && url.endsWith("/patients/")
        ? json(
            {
              title: "Validation failed",
              status: 400,
              code: "VALIDATION_ERROR",
              errors: [{ field: "mobile", message: "An Indian mobile number starts with 6, 7, 8 or 9.", code: "invalid" }],
            },
            400,
          )
        : undefined,
    );
    await screen.findByRole("heading", { name: "Register new patient" });
    fireEvent.click(screen.getByLabelText("Age in years"));
    fireEvent.change(screen.getByLabelText(/Age \(years\)/), { target: { value: "9" } });
    expect(screen.getByLabelText(/why/)).toBeInTheDocument(); // under 18 without a guardian
    fireEvent.click(screen.getByRole("button", { name: "Add a person" }));
    expect(screen.queryByLabelText(/why/)).not.toBeInTheDocument(); // a mother is added
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect(await screen.findByText("An Indian mobile number starts with 6, 7, 8 or 9.")).toBeInTheDocument();
  });

  it("shows the record: masked number, consent history, guardian warning", async () => {
    renderAt("/patients/p1", DESK);
    await screen.findByRole("heading", { name: "Asha Verma" });
    expect(screen.getByText("XXXX XXXX 1234")).toBeInTheDocument();
    expect(screen.getByText(/no parent or guardian recorded/)).toBeInTheDocument();
    const consent = screen.getByRole("table", { name: "Consent" });
    const rows = within(consent).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Withdrawn");
    expect(rows[1]).toHaveTextContent("Given (earlier)");
    expect(screen.getByText(/privacy notice is not recorded/)).toBeInTheDocument();
  });

  it("ends an ID number with a reason", async () => {
    const fetchMock = renderAt("/patients/p1", DESK);
    await screen.findByRole("heading", { name: "Asha Verma" });
    const ids = screen.getByRole("table", { name: "ID numbers" });
    fireEvent.click(within(ids).getByRole("button", { name: "End" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "End" })).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Typing mistake" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "End" }));
    await waitFor(() => expect(sentTo(fetchMock, "/identifiers/i1/end/")).toEqual({ version: 1, reason: "Typing mistake" }));
  });

  it("looks, without change buttons, for people who may not register", async () => {
    renderAt("/patients/p1", ADMIN);
    await screen.findByRole("heading", { name: "Asha Verma" });
    expect(screen.queryByRole("button", { name: "Correct details" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "End" })).not.toBeInTheDocument();
  });
});
