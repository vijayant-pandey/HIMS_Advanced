import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CurrentUser, DepartmentDetail } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { DepartmentDetailPage, hoursByDay } from "./DepartmentDetailPage";

const DEPARTMENT: DepartmentDetail = {
  id: "d1",
  facility: "f1",
  facility_name: "Main Hospital",
  code: "cardio",
  name: "Cardiology",
  department_type: "clinical",
  department_type_label: "Clinical",
  status: "active",
  current_staff: 2,
  active_wards: 1,
  head: null,
  head_name: null,
  open_24_hours: false,
  timezone: "Asia/Kolkata",
  version: 7,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  services: [
    {
      id: "s1",
      department: "d1",
      name: "Echocardiography",
      description: "Adult echo",
      is_active: true,
      version: 1,
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
  hours: [
    { weekday: 0, opens_at: "09:00", closes_at: "13:00" },
    { weekday: 0, opens_at: "17:00", closes_at: "20:00" },
  ],
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(grants: string[]) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/head-candidates/"))
      return json([{ id: "st1", name: "Asha Rao", designation: "Consultant" }]);
    if (init?.method && init.method !== "GET") return json(DEPARTMENT);
    return json(DEPARTMENT);
  });
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
      <MemoryRouter initialEntries={["/departments/d1"]}>
        <Routes>
          <Route path="/departments/:id" element={<DepartmentDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const sent = (fetchMock: ReturnType<typeof renderPage>, method: string, end: string) => {
  const call = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith(end) && i?.method === method);
  return call ? (JSON.parse(String(call[1]!.body)) as Record<string, unknown>) : undefined;
};

describe("DepartmentDetailPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows hours by day, services and the head", async () => {
    renderPage(["departments.view"]);
    expect(await screen.findByRole("heading", { name: "Cardiology" })).toBeInTheDocument();
    expect(screen.getByText("09:00–13:00, 17:00–20:00")).toBeInTheDocument();
    expect(screen.getAllByText("Closed")).toHaveLength(6);
    expect(screen.getByText("Echocardiography")).toBeInTheDocument();
    expect(screen.getByText("No head chosen yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit hours" })).not.toBeInTheDocument();
  });

  it("chooses a head from staff posted in the department", async () => {
    const fetchMock = renderPage(["departments.view", "departments.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "Change" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "Head" }));
    fireEvent.click(await screen.findByRole("option", { name: "Asha Rao (Consultant)" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(sent(fetchMock, "PATCH", "/departments/d1/")).toBeDefined(), { timeout: 4000 });
    expect(sent(fetchMock, "PATCH", "/departments/d1/")).toEqual({ version: 7, head: "st1" });
  });

  it("edits the weekly hours and sends the whole week", async () => {
    const fetchMock = renderPage(["departments.view", "departments.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "Edit hours" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Add Saturday session" }));
    fireEvent.change(within(dialog).getByLabelText("Saturday closes"), { target: { value: "12:00" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove Monday 09:00–13:00" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(sent(fetchMock, "PUT", "/departments/d1/hours/")).toBeDefined(), {
      timeout: 4000,
    });
    expect(sent(fetchMock, "PUT", "/departments/d1/hours/")).toEqual({
      version: 7,
      open_24_hours: false,
      sessions: [
        { weekday: 0, opens_at: "17:00", closes_at: "20:00" },
        { weekday: 5, opens_at: "09:00", closes_at: "12:00" },
      ],
    });
  });

  it("adds a service", async () => {
    const fetchMock = renderPage(["departments.view", "departments.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "Add service" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Service name/), { target: { value: "Holter monitoring" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(sent(fetchMock, "POST", "/departments/d1/services/")).toBeDefined(), {
      timeout: 4000,
    });
    expect(sent(fetchMock, "POST", "/departments/d1/services/")).toEqual({
      name: "Holter monitoring",
      description: "",
    });
  });

  it("formats days in plain words", () => {
    expect(hoursByDay([])[0]).toBe("Closed");
  });
});
