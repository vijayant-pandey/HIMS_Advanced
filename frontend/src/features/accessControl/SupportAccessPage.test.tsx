import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { visibleNavItems } from "../../layouts/navigation";
import { currentUserKey } from "../auth/api";
import { SupportAccessPage } from "./SupportAccessPage";

const SUPPLIER = { id: "u-sup", display_name: "HIMS Supplier Support", email: "support@supplier.synthetic.test" };
const ADMIN_ROLE = { id: "r-admin", code: "organization-administrator", name: "Organization administrator", description: "" };
const WAITING = {
  id: "s1",
  requested_by: SUPPLIER,
  role: ADMIN_ROLE,
  kind: "standard",
  kind_label: "Asked for, approved by the hospital",
  reason: "Check the rota error",
  hours: 2,
  status: "waiting",
  status_label: "Waiting for the hospital",
  created_at: "2026-11-12T09:00:00Z",
  decided_by_name: null,
  decided_at: null,
  decision_note: "",
  starts_at: null,
  ends_at: null,
  ended_at: null,
  ended_by_name: null,
  end_reason: "",
  version: 1,
};
const EMERGENCY = {
  ...WAITING,
  id: "s2",
  kind: "emergency",
  kind_label: "Emergency (opened at once)",
  status: "active",
  status_label: "Active now",
  starts_at: "2026-11-12T10:00:00Z",
  ends_at: "2026-11-12T12:00:00Z",
  version: 2,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function user(grants: string[]): CurrentUser {
  return {
    id: "u-me",
    email: "me@synthetic.test",
    display_name: "Synthetic Person",
    staff_member_id: null,
    grants: grants.map((permission) => ({ permission, facility_id: null, department_id: null })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10, passkeys: 0 },
  };
}

function renderPage(grants: string[]) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST" && url.endsWith("/my-support-access/")) return json({ ...EMERGENCY, id: "s3" }, 201);
    if (init?.method === "POST") return json({ ...WAITING, status: "active", status_label: "Active now" });
    if (url.includes("/my-support-access/options/"))
      return json({ roles: [ADMIN_ROLE], default_hours: 2, max_hours: 8, emergency_notice: false });
    if (url.includes("/my-support-access/")) return json([WAITING]);
    if (url.includes("/support-access/")) return json([WAITING, EMERGENCY]);
    return json({});
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user(grants));
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SupportAccessPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const posted = (fetchMock: ReturnType<typeof renderPage>, ending: string) =>
  fetchMock.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith(ending));

describe("SupportAccessPage (HIMS-IAM-021)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the menu item to the hospital and to the supplier only", () => {
    const has = (grants: string[]) => visibleNavItems(user(grants)).some((item) => item.to === "/support-access");
    expect(has(["support.access.manage"])).toBe(true);
    expect(has(["support.access.request"])).toBe(true);
    expect(has(["staff.view"])).toBe(false);
  });

  it("lets the hospital approve a waiting request; emergency access is listed too", async () => {
    const fetchMock = renderPage(["support.access.manage"]);
    const table = await screen.findByRole("table", { name: "Support access requests" });
    expect(await within(table).findAllByText("HIMS Supplier Support")).toHaveLength(2);
    expect(table).toHaveTextContent("Emergency");
    expect(screen.queryByRole("button", { name: "Ask for access" })).not.toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/support-access/s1/approve/")).toBeTruthy(), { timeout: 4000 });
    expect(JSON.parse(String(posted(fetchMock, "/support-access/s1/approve/")![1]!.body))).toEqual({
      version: 1,
      note: "",
    });
  });

  it("needs a reason to refuse", async () => {
    const fetchMock = renderPage(["support.access.manage"]);
    const table = await screen.findByRole("table", { name: "Support access requests" });
    fireEvent.click(await within(table).findByRole("button", { name: "Refuse" }));
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "Refuse" });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Why is it refused/), { target: { value: "Not today" } });
    fireEvent.click(submit);
    await vi.waitFor(() => expect(posted(fetchMock, "/s1/refuse/")).toBeTruthy(), { timeout: 4000 });
  });

  it("lets the supplier ask, and warns before emergency access", async () => {
    const fetchMock = renderPage(["support.access.request"]);
    const mine = await screen.findByRole("table", { name: "Your support access requests" });
    expect(await within(mine).findByText("Waiting for the hospital")).toBeInTheDocument();
    expect(within(mine).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Support access requests" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ask for access" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialog).getByLabelText(/Access/));
    fireEvent.click(await screen.findByRole("option", { name: "Organization administrator" }));
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Sign-in outage" } });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Emergency/ }));
    expect(within(dialog).getByText(/The hospital is not emailed/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Open emergency access now" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/my-support-access/")).toBeTruthy(), { timeout: 4000 });
    expect(JSON.parse(String(posted(fetchMock, "/my-support-access/")![1]!.body))).toEqual({
      role: "r-admin",
      hours: 2,
      reason: "Sign-in outage",
      emergency: true,
    });
    expect(await screen.findByText(/access is open until/)).toBeInTheDocument();
  });
});
