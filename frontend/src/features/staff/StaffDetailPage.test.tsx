import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CurrentUser, RoleAssignment, StaffMemberDetail } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { StaffDetailPage } from "./StaffDetailPage";
import { StaffPage } from "./StaffPage";

const STAFF: StaffMemberDetail = {
  id: "s1",
  user: "u-nurse",
  email: "mary@synthetic.test",
  employee_number: "EMP-0101",
  given_name: "Mary",
  family_name: "Joseph",
  staff_type: "nurse",
  staff_type_label: "Nurse",
  employment_status: "active",
  employment_status_label: "Active",
  joined_on: "2026-01-05",
  left_on: null,
  version: 3,
  created_at: "2026-01-05T00:00:00Z",
  updated_at: "2026-01-05T00:00:00Z",
  account: {
    has_login: true,
    email: "mary@synthetic.test",
    is_active: true,
    activated: false,
    invitation_expires_at: "2026-11-01T10:00:00Z",
    two_factor_enabled: false,
  },
  department_assignments: [
    {
      id: "a1",
      department: "d1",
      designation: "des1",
      designation_name: "Staff Nurse",
      specialty: null,
      is_primary: true,
      valid_from: "2026-01-05",
      valid_until: null,
      department_name: "Cardiology",
      facility_name: "Main Hospital",
      specialty_name: null,
      is_current: true,
    },
  ],
  qualifications: [
    {
      id: "q1",
      qualification_type: "qt1",
      specialty: null,
      institution: "Synthetic College of Nursing",
      year_awarded: 2020,
      verification_status: "unverified",
      verified_by: null,
      verified_by_name: null,
      verified_at: null,
      qualification_type_name: "B.Sc. Nursing",
      specialty_name: null,
    },
  ],
  credentials: [
    {
      id: "c1",
      credential_type: "nursing_registration",
      registration_number: "KNC-55501",
      issuing_authority: "Karnataka Nursing Council",
      jurisdiction: "IN-KA",
      valid_from: null,
      expires_at: "2026-11-20",
      verification_status: "verified",
      verified_by: "u2",
      verified_by_name: "Synthetic HR",
      verified_at: "2026-02-01T00:00:00Z",
      credential_type_label: "Nursing council registration",
      expiry_state: "expiring_soon",
    },
  ],
};

const ASSIGNMENT: RoleAssignment = {
  id: "ra1",
  user: "u-nurse",
  role: "r1",
  role_code: "basic-staff",
  role_name: "Basic staff access",
  user_display_name: "Mary Joseph",
  user_email: "mary@synthetic.test",
  facility_name: "Main Hospital",
  department_name: null,
  granted_by_name: "Synthetic Admin",
  revoked_by_name: null,
  is_active: true,
  facility: "f1",
  department: null,
  valid_from: "2026-01-05T00:00:00Z",
  valid_until: null,
  reason: "New joiner",
  granted_by: "u-admin",
  revoked_at: null,
  revoked_by: null,
  revocation_reason: "",
  created_at: "2026-01-05T00:00:00Z",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const page = (results: unknown[]) => ({ count: results.length, next: null, previous: null, results });

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (method !== "GET") return json({}, url.endsWith("/role-assignments/") ? 201 : 200);
    if (url.includes("/staff/s1/")) return json(STAFF);
    if (url.includes("/staff/")) return json(page([STAFF]));
    if (url.includes("/role-assignments/")) return json(page([ASSIGNMENT]));
    if (url.includes("/roles/"))
      return json(page([{ id: "r1", name: "Basic staff access", description: "Minimum access", permissions: [] }]));
    if (url.includes("/facilities/")) return json(page([{ id: "f1", name: "Main Hospital" }]));
    return json(page([]));
  });
}

function renderAt(path: string, grants: string[], userId = "u-admin") {
  const user: CurrentUser = {
    id: userId,
    email: "admin@synthetic.test",
    display_name: "Synthetic Admin",
    staff_member_id: null,
    grants: grants.map((permission) => ({ permission, facility_id: null, department_id: null })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/staff" element={<StaffPage />} />
          <Route path="/staff/:id" element={<StaffDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const HR = ["staff.view", "staff.manage", "staff.credentials.verify", "access.roles.view", "access.assignments.manage"];

function bodyOf(fetchMock: ReturnType<typeof mockApi>, urlEnd: string) {
  const call = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith(urlEnd) && init?.method === "POST");
  return call ? (JSON.parse(String(call[1]!.body)) as Record<string, unknown>) : undefined;
}

describe("Staff screens", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists staff, filters by status and opens a person", async () => {
    const fetchMock = mockApi();
    renderAt("/staff", HR);
    expect(await screen.findByRole("button", { name: "Add staff member" })).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Status" }));
    fireEvent.click(await screen.findByRole("option", { name: "On leave" }));
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("employment_status=on_leave"))).toBe(true),
    );
    fireEvent.click(await screen.findByText("Mary Joseph"));
    expect(await screen.findByRole("heading", { name: "Mary Joseph" })).toBeInTheDocument();
  });

  it("hides the add button from people who may only view", async () => {
    mockApi();
    renderAt("/staff", ["staff.view"]);
    await screen.findByText("Mary Joseph");
    expect(screen.queryByRole("button", { name: "Add staff member" })).not.toBeInTheDocument();
  });

  it("shows the account, postings and lets HR end a posting with a reason", async () => {
    const fetchMock = mockApi();
    renderAt("/staff/s1", HR);
    expect(await screen.findByText(/Invitation sent to mary@synthetic.test/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resend invitation" })).toBeInTheDocument();
    expect(screen.getByText("Cardiology")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "End" }));
    const dialog = await screen.findByRole("dialog");
    const save = within(dialog).getByRole("button", { name: "End posting" });
    expect(save).toBeDisabled(); // reason required
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Transferred" } });
    fireEvent.click(save);
    await vi.waitFor(() => expect(bodyOf(fetchMock, "/department-assignments/a1/end/")).toBeDefined());
    expect(bodyOf(fetchMock, "/department-assignments/a1/end/")).toMatchObject({ reason: "Transferred" });
  });

  it("verifies a qualification and shows licence expiry", async () => {
    const fetchMock = mockApi();
    renderAt("/staff/s1", HR);
    fireEvent.click(await screen.findByRole("tab", { name: /Qualifications/ }));
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Mark verified" }));
    await vi.waitFor(() => expect(bodyOf(fetchMock, "/qualifications/q1/verify/")).toEqual({ verified: true, reason: "" }));

    fireEvent.click(screen.getByRole("tab", { name: /Licences/ }));
    expect(await screen.findByText("Expires soon")).toBeInTheDocument();
    expect(screen.getByText("by Synthetic HR")).toBeInTheDocument();
  });

  it("does not offer to verify your own qualification", async () => {
    mockApi();
    renderAt("/staff/s1", HR, "u-nurse");
    fireEvent.click(await screen.findByRole("tab", { name: /Qualifications/ }));
    expect(screen.queryByRole("button", { name: "Verify" })).not.toBeInTheDocument();
  });

  it("gives access at one facility and removes it with a reason", async () => {
    const fetchMock = mockApi();
    renderAt("/staff/s1", HR);
    fireEvent.click(await screen.findByRole("tab", { name: "Access" }));
    expect(await screen.findByText("Basic staff access")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Give access" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "Role" }));
    fireEvent.click(await screen.findByRole("option", { name: "Basic staff access" }));
    fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "Facility" }));
    fireEvent.click(await screen.findByRole("option", { name: "Main Hospital" }));
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Joined ICU" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Give access" }));
    await vi.waitFor(() => expect(bodyOf(fetchMock, "/role-assignments/")).toBeDefined());
    expect(bodyOf(fetchMock, "/role-assignments/")).toEqual({
      user: "u-nurse",
      role: "r1",
      facility: "f1",
      department: null,
      valid_until: null,
      reason: "Joined ICU",
    });

    fireEvent.click(await screen.findByRole("button", { name: "Remove Basic staff access" }));
    const revoke = await screen.findByRole("dialog");
    fireEvent.change(within(revoke).getByLabelText(/Reason/), { target: { value: "Left ICU" } });
    fireEvent.click(within(revoke).getByRole("button", { name: "Remove access" }));
    await vi.waitFor(() => expect(bodyOf(fetchMock, "/role-assignments/ra1/revoke/")).toEqual({ reason: "Left ICU" }));
  });
});
