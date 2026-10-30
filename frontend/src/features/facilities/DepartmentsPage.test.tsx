import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CurrentUser, Department, Facility } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { DepartmentsPage } from "./DepartmentsPage";
import { FacilitiesPage } from "./FacilitiesPage";

const FACILITY: Facility = {
  id: "f1",
  code: "main",
  name: "Main Hospital",
  facility_type: "hospital",
  facility_type_label: "Hospital",
  country: "IN",
  state_region: "Karnataka",
  city: "Bengaluru",
  address_line1: "1 Synthetic Road",
  address_line2: "",
  postal_code: "560001",
  timezone: "Asia/Kolkata",
  phone: "",
  status: "active",
  active_departments: 1,
  version: 2,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const CARDIOLOGY: Department = {
  id: "d1",
  facility: "f1",
  facility_name: "Main Hospital",
  code: "cardio",
  name: "Cardiology",
  department_type: "clinical",
  department_type_label: "Clinical",
  status: "active",
  current_staff: 3,
  active_wards: 1,
  head: null,
  head_name: null,
  open_24_hours: false,
  version: 5,
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
    if (method === "PATCH" && url.includes("/departments/")) {
      const body = JSON.parse(String(init!.body)) as { status?: string };
      if (body.status === "inactive")
        return json(
          {
            title: "Validation failed",
            status: 400,
            code: "VALIDATION_ERROR",
            errors: [
              {
                field: "status",
                message: "It cannot be deactivated yet: 3 staff members are posted here (end their postings on the Staff page).",
              },
            ],
          },
          400,
        );
      return json(CARDIOLOGY);
    }
    if (method !== "GET") return json({}, method === "POST" ? 201 : 200);
    if (url.includes("/departments/")) return json(page([CARDIOLOGY]));
    if (url.includes("/facilities/")) return json(page([FACILITY]));
    return json(page([]));
  });
}

function renderAt(path: string, grants: string[]) {
  const user: CurrentUser = {
    id: "u1",
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
          <Route path="/departments" element={<DepartmentsPage />} />
          <Route path="/facilities" element={<FacilitiesPage />} />
          <Route path="/staff" element={<p>Staff page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ADMIN = ["facilities.view", "facilities.manage", "departments.view", "departments.manage", "staff.view"];

describe("Departments and facilities screens", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists departments with staff and ward counts; the staff count opens the staff list", async () => {
    mockApi();
    renderAt("/departments", ADMIN);
    expect(await screen.findByText("Cardiology")).toBeInTheDocument();
    expect(screen.getByText("Clinical")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "3" }));
    expect(await screen.findByText("Staff page")).toBeInTheDocument();
  });

  it("adds a department with a safe code", async () => {
    const fetchMock = mockApi();
    renderAt("/departments", ADMIN);
    fireEvent.click(await screen.findByRole("button", { name: "Add department" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: "Emergency" } });
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "ER Main" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith("/departments/") && i?.method === "POST")).toBe(true),
    );
    const call = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith("/departments/") && i?.method === "POST")!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({
      facility: "f1",
      code: "er-main",
      name: "Emergency",
      department_type: "clinical",
    });
    expect((call[1]!.headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();
  });

  it("explains why a department in use cannot be deactivated", async () => {
    mockApi();
    renderAt("/departments", ADMIN);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Cardiology" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "Status" }));
    fireEvent.click(await screen.findByRole("option", { name: "Inactive" }));
    expect(within(dialog).getByText(/Still in use: 3 staff posted, 1 active ward/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText(/3 staff members are posted here/)).toBeInTheDocument();
  });

  it("hides add and edit from people who may only view", async () => {
    mockApi();
    renderAt("/departments", ["departments.view"]);
    await screen.findByText("Cardiology");
    expect(screen.queryByRole("button", { name: "Add department" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit Cardiology" })).not.toBeInTheDocument();
  });

  it("edits a facility with its current version", async () => {
    const fetchMock = mockApi();
    renderAt("/facilities", ADMIN);
    expect(await screen.findByText("Hospital")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit Main Hospital" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^Phone/), { target: { value: "+91-80-0000" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([, i]) => i?.method === "PATCH")).toBe(true),
    );
    const patch = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH")!;
    expect(String(patch[0])).toMatch(/\/facilities\/f1\/$/);
    expect(JSON.parse(String(patch[1]!.body))).toMatchObject({
      version: 2,
      phone: "+91-80-0000",
      timezone: "Asia/Kolkata",
      status: "active",
    });
  });
});
