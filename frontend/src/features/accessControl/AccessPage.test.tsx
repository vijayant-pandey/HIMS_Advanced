import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { CurrentUser, Role } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { AccessPage } from "./AccessPage";

const SYSTEM: Role = {
  id: "r1",
  code: "basic-staff",
  name: "Basic staff access",
  description: "Minimum access for any employee",
  is_system: true,
  permissions: ["facilities.view"],
  active_assignments: 12,
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
};
const CUSTOM: Role = {
  ...SYSTEM,
  id: "r2",
  code: "ward-clerk-plus",
  name: "Ward clerk plus",
  description: "",
  is_system: false,
  permissions: ["locations.view"],
  active_assignments: 2,
  version: 4,
};

const ENDPOINT = {
  area: "facilities",
  area_label: "Facilities, departments and locations",
  scope: "facility",
  confirm_identity: false,
  idempotency: "optional",
  requirements: ["HIMS-FAC-001"],
};
const ENDPOINTS = {
  summary: {
    total: 2,
    public: 1,
    signed_in: 0,
    permission: 1,
    confirm_identity: 0,
    idempotent: 1,
    audited_writes: 1,
    writes: 2,
  },
  endpoints: [
    {
      ...ENDPOINT,
      method: "POST",
      path: "/api/v1/facilities/",
      summary: "Add (facilities).",
      access: "permission",
      permission: "facilities.manage",
      permission_label: "Create facilities",
      roles: ["Organization administrator"],
      audit_actions: ["facility.created"],
    },
    {
      ...ENDPOINT,
      area: "identity",
      area_label: "Sign-in, two-factor, passkeys, sessions and accounts",
      method: "POST",
      path: "/api/v1/auth/login/",
      summary: "Sign in with email and password.",
      access: "public",
      permission: "",
      permission_label: "",
      roles: [],
      scope: "",
      idempotency: "",
      audit_actions: ["auth.login"],
      requirements: ["HIMS-IAM-002"],
    },
  ],
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
const page = (results: unknown[]) => ({ count: results.length, next: null, previous: null, results });

function renderPage(grants: string[]) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "PATCH") return json(CUSTOM);
    if (url.includes("/api-endpoints/")) return json(ENDPOINTS);
    if (url.includes("/permissions/"))
      return json([
        { codename: "locations.view", description: "View buildings, floors, wards, rooms and beds" },
        { codename: "beds.status.manage", description: "Put beds into or out of maintenance" },
        { codename: "facilities.view", description: "View facilities" },
      ]);
    if (url.includes("/roles/")) return json(page([SYSTEM, CUSTOM]));
    if (url.includes("/role-assignments/"))
      return json(
        page([
          {
            id: "ra1",
            user: "u2",
            role: "r1",
            role_name: "Basic staff access",
            user_display_name: "Mary Joseph",
            user_email: "mary@synthetic.test",
            facility_name: "Main Hospital",
            department_name: null,
            granted_by_name: "Synthetic Admin",
            is_active: true,
            valid_until: null,
            created_at: "2026-01-05T00:00:00Z",
          },
        ]),
      );
    return json(page([]));
  });
  const user: CurrentUser = {
    id: "u-admin",
    email: "admin@synthetic.test",
    display_name: "Synthetic Admin",
    staff_member_id: null,
    grants: grants.map((permission) => ({ permission, facility_id: null, department_id: null })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10, passkeys: 0 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <AccessPage />
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("AccessPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows who has access where", async () => {
    renderPage(["access.roles.view", "access.assignments.manage"]);
    expect(await screen.findByText("Mary Joseph")).toBeInTheDocument();
    expect(screen.getByText("Main Hospital")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Basic staff access from Mary Joseph" })).toBeInTheDocument();
  });

  it("lists roles; only custom roles can be edited, sending the version", async () => {
    const fetchMock = renderPage(["access.roles.view", "access.roles.manage"]);
    fireEvent.click(await screen.findByRole("tab", { name: "Roles" }));
    expect(await screen.findByText("Ward clerk plus")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit Basic staff access" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Edit Ward clerk plus" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/2 person\(s\) hold this role/)).toBeInTheDocument();
    fireEvent.click(await within(dialog).findByRole("checkbox", { name: /Put beds into or out of maintenance/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true),
    );
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(String(patch[0])).toMatch(/\/roles\/r2\/$/);
    expect(JSON.parse(String(patch[1]!.body))).toEqual({
      version: 4,
      name: "Ward clerk plus",
      description: "",
      permissions: ["beds.status.manage", "locations.view"],
    });
  });

  it("lists API endpoints with who may call them, filtered by access", async () => {
    renderPage(["access.roles.view"]);
    fireEvent.click(await screen.findByRole("tab", { name: "API endpoints" }));
    const table = await screen.findByRole("table", { name: "API endpoints" });
    expect(await within(table).findByText("facilities.manage")).toBeInTheDocument();
    expect(within(table).getByText("Organization administrator")).toBeInTheDocument();
    expect(within(table).getByText("facility.created")).toBeInTheDocument();
    expect(within(table).getByText("Anyone (no sign-in)")).toBeInTheDocument();
    expect(screen.getByText(/2 endpoints: 1 need a permission/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "login" } });
    expect(within(table).queryByText("facilities.manage")).not.toBeInTheDocument();
    expect(within(table).getByText("HIMS-IAM-002")).toBeInTheDocument();
  });

  it("hides role and access changes from view-only users", async () => {
    renderPage(["access.roles.view"]);
    await screen.findByText("Mary Joseph");
    expect(screen.queryByRole("button", { name: /^Remove/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Roles" }));
    await screen.findByText("Ward clerk plus");
    expect(screen.queryByRole("button", { name: "New custom role" })).not.toBeInTheDocument();
  });
});
