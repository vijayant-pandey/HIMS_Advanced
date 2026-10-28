import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { Account, CurrentUser, Organization } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { HospitalSettingsPage } from "../organization/HospitalSettingsPage";
import { AccountDetailPage } from "./AccountDetailPage";
import { AccountsPage } from "./AccountsPage";

const AUDITOR: Account = {
  id: "u-aud",
  email: "auditor@synthetic.test",
  display_name: "External Auditor",
  is_active: true,
  activated: true,
  two_factor_enabled: true,
  invitation_expires_at: null,
  staff_member_id: null,
  roles: ["Auditor / compliance officer"],
  last_login: "2026-10-28T09:00:00Z",
  date_joined: "2026-10-01T00:00:00Z",
};

const ORGANIZATION: Organization = {
  id: "o1",
  legal_name: "Synthetic Healthcare Pvt Ltd",
  display_name: "Synthetic Health",
  country: "IN",
  default_timezone: "Asia/Kolkata",
  default_currency: "INR",
  status: "active",
  version: 3,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
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
    if (url.includes("/organization/")) return json(ORGANIZATION);
    if (method === "POST" && url.endsWith("/accounts/")) return json({ ...AUDITOR, id: "u-new" }, 201);
    if (method === "POST") return json({ ...AUDITOR, is_active: false });
    if (url.includes("/accounts/u-aud/")) return json(AUDITOR);
    if (url.includes("/accounts/")) return json(page([AUDITOR]));
    return json(page([]));
  });
}

function renderAt(path: string, grants: string[]) {
  const user: CurrentUser = {
    id: "u-admin",
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
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/accounts/:id" element={<AccountDetailPage />} />
          <Route path="/settings" element={<HospitalSettingsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ADMIN = ["access.roles.view", "accounts.manage", "access.assignments.manage", "organization.view", "organization.manage"];

const posted = (fetchMock: ReturnType<typeof mockApi>, end: string) =>
  fetchMock.mock.calls.find(([u, i]) => String(u).endsWith(end) && i?.method === "POST");

describe("Accounts and hospital settings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists accounts and adds one for someone who is not staff", async () => {
    const fetchMock = mockApi();
    renderAt("/accounts", ADMIN);
    expect(await screen.findByText("External Auditor")).toBeInTheDocument();
    expect(screen.getByText("Auditor / compliance officer")).toBeInTheDocument();
    expect(screen.getByText("Not staff")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add account" }));
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "Add and send invitation" });
    expect(submit).toBeDisabled(); // reason required
    fireEvent.change(within(dialog).getByLabelText(/Full name/), { target: { value: "IT Vendor" } });
    fireEvent.change(within(dialog).getByLabelText(/Email/), { target: { value: "it@synthetic.test" } });
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Support contract" } });
    fireEvent.click(submit);
    await vi.waitFor(() => expect(posted(fetchMock, "/accounts/")).toBeDefined(), { timeout: 4000 });
    expect(JSON.parse(String(posted(fetchMock, "/accounts/")![1]!.body))).toEqual({
      display_name: "IT Vendor",
      email: "it@synthetic.test",
      reason: "Support contract",
    });
  });

  it("switches an account off with a reason", async () => {
    const fetchMock = mockApi();
    renderAt("/accounts/u-aud", ADMIN);
    fireEvent.click(await screen.findByRole("button", { name: "Switch account off" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Audit finished" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Switch off" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/accounts/u-aud/deactivate/")).toBeDefined(), {
      timeout: 4000,
    });
    expect(JSON.parse(String(posted(fetchMock, "/accounts/u-aud/deactivate/")![1]!.body))).toEqual({
      reason: "Audit finished",
    });
  });

  it("offers no account actions on your own account or without permission", async () => {
    mockApi();
    renderAt("/accounts/u-aud", ["access.roles.view"]);
    await screen.findByRole("heading", { name: "External Auditor" });
    expect(screen.queryByRole("button", { name: "Switch account off" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add account" })).not.toBeInTheDocument();
  });

  it("shows hospital settings and edits them with the current version", async () => {
    const fetchMock = mockApi();
    renderAt("/settings", ADMIN);
    expect(await screen.findByText("Synthetic Healthcare Pvt Ltd")).toBeInTheDocument();
    expect(screen.getByText("India")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Name shown in HIMS/), { target: { value: "Sunrise" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await vi.waitFor(
      () => expect(fetchMock.mock.calls.some(([, i]) => i?.method === "PATCH")).toBe(true),
      { timeout: 4000 },
    );
    const patch = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH")!;
    expect(JSON.parse(String(patch[1]!.body))).toEqual({
      version: 3,
      display_name: "Sunrise",
      legal_name: "Synthetic Healthcare Pvt Ltd",
      default_timezone: "Asia/Kolkata",
    });
  });

  it("hides the edit button from people who may only view the settings", async () => {
    mockApi();
    renderAt("/settings", ["organization.view"]);
    await screen.findByText("Synthetic Healthcare Pvt Ltd");
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });
});
