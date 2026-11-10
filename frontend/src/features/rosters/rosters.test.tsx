import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { localDate } from "../../components/dates";
import { currentUserKey } from "../auth/api";
import { addDays, mondayOf } from "./labels";
import { LeavePage } from "./LeavePage";
import { MySchedulePage } from "./MySchedulePage";
import { RotaPage } from "./RotaPage";

const MONDAY = mondayOf(localDate());
const NEXT = addDays(MONDAY, 8); // a day in next week: never in the past
const SHIFT = {
  id: "s1",
  staff_id: "st-asha",
  staff_name: "Asha Nurse",
  department_id: "dep-1",
  department_name: "Cardiology",
  facility_id: "fac-1",
  shift_type_id: "t-night",
  shift_type_name: "Night",
  kind: "shift",
  on_date: MONDAY,
  starts_at: `${MONDAY}T14:30:00Z`,
  ends_at: `${MONDAY}T02:30:00Z`,
  hours: "20:00-08:00",
  note: "",
  status: "scheduled",
  cancel_reason: "",
  version: 1,
};
const WEEK = {
  department_id: "dep-1",
  department_name: "Cardiology",
  facility_id: "fac-1",
  facility_name: "Main Hospital",
  start: MONDAY,
  days: [0, 1, 2, 3, 4, 5, 6].map((n) => addDays(MONDAY, n)),
  can_manage: true,
  leave_details: false,
  staffing_gaps: [],
  people: [
    { staff_id: "st-asha", name: "Asha Nurse", designation: "Staff nurse", shifts: [SHIFT], away: [] },
    {
      staff_id: "st-ravi",
      name: "Ravi Nurse",
      designation: "Staff nurse",
      shifts: [],
      away: [
        { leave_id: "l1", start_date: MONDAY, end_date: addDays(MONDAY, 1), status: "approved", leave_type: null, leave_type_label: null },
      ],
    },
  ],
};
const LEAVE = {
  id: "l2",
  staff_id: "st-asha",
  staff_name: "Asha Nurse",
  department_id: "dep-1",
  department_name: "Cardiology",
  facility_id: "fac-1",
  leave_type: "annual",
  leave_type_label: "Annual / earned leave",
  start_date: NEXT,
  end_date: addDays(NEXT, 1),
  days: 2,
  reason: "",
  status: "requested",
  status_label: "Waiting for a decision",
  requested_by_name: "Asha Nurse",
  created_at: "2026-11-01T10:00:00Z",
  decided_by_name: null,
  decided_at: null,
  decision_note: "",
  cancelled_at: null,
  cancel_reason: "",
  conflicting_shifts: [{ ...SHIFT, id: "s2", on_date: NEXT }],
  version: 1,
};

const BALANCE = {
  leave_type: "annual",
  label: "Annual / earned leave",
  year: 2026,
  year_label: "2026",
  entitled: 20,
  carried_in: 2,
  adjusted: 0,
  taken: 10,
  waiting: 1,
  remaining: 12,
};
const REQUIREMENT = {
  id: "m1",
  department: "dep-1",
  department_name: "Cardiology",
  shift_type: "t-night",
  shift_type_name: "Night",
  staff_type: "nurse",
  staff_type_label: "Nurse",
  applies_on: "every_day",
  applies_on_label: "Every day",
  minimum: 2,
  is_active: true,
  version: 4,
};
const ENTITLEMENT = {
  id: "e1",
  leave_type: "annual",
  leave_type_label: "Annual / earned leave",
  from_year: 2026,
  year_label: "2026",
  days: 20,
  max_carry_over: 5,
  prorate_on_joining: true,
  tracked: true,
  can_change: true,
  version: 2,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderPage(ui: ReactElement, grants: string[], routes: Record<string, unknown> = {}) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST") return json({ created: [SHIFT], skipped: [], ...LEAVE }, 201);
    for (const [path, body] of Object.entries(routes)) if (url.includes(path)) return json(body);
    if (url.includes("/rota/now/")) return json({ at: "2026-11-06T10:00:00Z", on_call: [{ ...SHIFT, kind: "on_call", shift_type_name: "On call (24 hours)" }], working: [] });
    if (url.includes("/rota/")) return json(WEEK);
    if (url.includes("/departments/"))
      return json({ count: 1, next: null, previous: null, results: [{ id: "dep-1", name: "Cardiology", facility_name: "Main Hospital", status: "active" }] });
    if (url.includes("/shift-types/"))
      return json([{ id: "t-night", code: "night", name: "Night", kind: "shift", kind_label: "Working shift", start_time: "20:00:00", end_time: "08:00:00", minutes: 720, is_active: true, is_custom: false, version: 1 }]);
    return json({});
  });
  const user: CurrentUser = {
    id: "u1",
    email: "head@synthetic.test",
    display_name: "Synthetic Head",
    staff_member_id: "st-head",
    grants: grants.map((permission) => ({ permission, facility_id: "fac-1", department_id: "dep-1" })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: false, required: false, verified: false, recovery_codes_remaining: 0 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const posted = (fetchMock: ReturnType<typeof renderPage>, ending: string) =>
  fetchMock.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith(ending));

describe("Rota (HIMS-STAFF-012)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the week, who is away (not why) and who is on call now", async () => {
    renderPage(<RotaPage />, ["rota.view", "rota.manage"]);
    const grid = await screen.findByRole("table", { name: "Rota for Cardiology" });
    expect(within(grid).getByText("Night 20:00-08:00")).toBeInTheDocument();
    expect(within(grid).getAllByText("On leave")).toHaveLength(2);
    expect(grid).not.toHaveTextContent("Sick");
    const now = screen.getByRole("region", { name: "On call now" });
    expect(now).toHaveTextContent("Cardiology: Asha Nurse · until 08:00");
  });

  it("plans a shift from the grid with the chosen person, day and shift", async () => {
    const fetchMock = renderPage(<RotaPage />, ["rota.view", "rota.manage"]);
    const sunday = addDays(MONDAY, 6);
    const add = await screen.findAllByRole("button", { name: /Plan a shift for Ravi Nurse/ });
    fireEvent.click(add[add.length - 1]!);
    const dialog = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialog).getByLabelText(/Shift/));
    fireEvent.click(await screen.findByRole("option", { name: /Night · 20:00–08:00/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Plan" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/shifts/")).toBeTruthy());
    const body = JSON.parse(String(posted(fetchMock, "/shifts/")![1]!.body));
    expect(body).toMatchObject({ staff: "st-ravi", department: "dep-1", shift_type: "t-night", from_date: sunday, to_date: sunday });
  });

  it("cancels a shift with a reason", async () => {
    const fetchMock = renderPage(<RotaPage />, ["rota.view", "rota.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: /Night 20:00-08:00, Asha Nurse, .*: cancel/ }));
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "Cancel shift" });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Why/), { target: { value: "Swapped with Ravi" } });
    fireEvent.click(submit);
    await vi.waitFor(() => expect(posted(fetchMock, "/shifts/s1/cancel/")).toBeTruthy());
  });

  it("view only: no planning buttons", async () => {
    renderPage(<RotaPage />, ["rota.view"], { "/rota/?": { ...WEEK, can_manage: false } });
    await screen.findByRole("table", { name: "Rota for Cardiology" });
    expect(screen.queryByRole("button", { name: "Plan shifts" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Plan a shift for/ })).not.toBeInTheDocument();
  });
});

describe("Leave (HIMS-STAFF-012)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("approving over planned shifts needs 'cancel those shifts' ticked", async () => {
    const fetchMock = renderPage(<LeavePage />, ["leave.approve"], { "/leave-requests/": [LEAVE] });
    fireEvent.click(await screen.findByRole("button", { name: "Approve leave for Asha Nurse" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("1 planned shift(s) during this leave");
    const approve = within(dialog).getByRole("button", { name: "Approve leave" });
    expect(approve).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Cancel those shifts/ }));
    fireEvent.click(approve);
    await vi.waitFor(() => expect(posted(fetchMock, "/leave-requests/l2/approve/")).toBeTruthy());
    const body = JSON.parse(String(posted(fetchMock, "/leave-requests/l2/approve/")![1]!.body));
    expect(body).toEqual({ version: 1, note: "", cancel_shifts: true });
  });

  it("refusing needs a reason", async () => {
    renderPage(<LeavePage />, ["leave.approve"], { "/leave-requests/": [LEAVE] });
    fireEvent.click(await screen.findByRole("button", { name: "Refuse leave for Asha Nurse" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Refuse leave" })).toBeDisabled();
  });
});

describe("My schedule (HIMS-STAFF-012)", () => {
  afterEach(() => vi.restoreAllMocks());

  const SCHEDULE = {
    has_staff_record: true,
    name: "Asha Nurse",
    postings: [{ department_id: "dep-1", department_name: "Cardiology", facility_name: "Main Hospital", is_primary: true }],
    shifts: [{ ...SHIFT, on_date: NEXT }],
    leave: [LEAVE],
    leave_balances: [BALANCE],
  };

  it("shows what is left of my leave", async () => {
    renderPage(<MySchedulePage />, [], { "/my-schedule/": SCHEDULE });
    const table = await screen.findByRole("table", { name: "My leave balance" });
    expect(table).toHaveTextContent("Annual / earned leave");
    expect(table).toHaveTextContent("12 left of 20 (2 carried in, 1 waiting)");
    expect(screen.getByRole("heading", { name: "My leave balance, 2026" })).toBeInTheDocument();
  });

  it("shows no balance table when no kind of leave is tracked", async () => {
    renderPage(<MySchedulePage />, [], { "/my-schedule/": { ...SCHEDULE, leave_balances: [] } });
    await screen.findByRole("table", { name: "My leave" });
    expect(screen.queryByRole("table", { name: "My leave balance" })).toBeNull();
  });

  it("lists my shifts and leave, and asks for leave", async () => {
    const fetchMock = renderPage(<MySchedulePage />, [], { "/my-schedule/": SCHEDULE });
    const shifts = await screen.findByRole("table", { name: "My coming shifts" });
    expect(shifts).toHaveTextContent("Night");
    expect(shifts).toHaveTextContent("20:00-08:00");
    expect(screen.getByRole("table", { name: "My leave" })).toHaveTextContent("Waiting for a decision");
    fireEvent.click(screen.getByRole("button", { name: "Ask for leave" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("No medical details");
    fireEvent.click(within(dialog).getByRole("button", { name: "Send" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/my-leave-requests/")).toBeTruthy());
    const body = JSON.parse(String(posted(fetchMock, "/my-leave-requests/")![1]!.body));
    expect(body).toMatchObject({ department: "dep-1", leave_type: "annual" });
  });

  it("explains when the account has no staff record", async () => {
    renderPage(<MySchedulePage />, [], { "/my-schedule/": { has_staff_record: false, postings: [], shifts: [], leave: [], leave_balances: [] } });
    expect(await screen.findByText(/no staff record/)).toBeInTheDocument();
  });
});

const bodyOf = (fetchMock: ReturnType<typeof renderPage>, method: string, ending: string) => {
  const call = fetchMock.mock.calls.find(([url, init]) => init?.method === method && String(url).endsWith(ending));
  return call ? (JSON.parse(String(call[1]?.body)) as Record<string, unknown>) : undefined;
};

describe("Minimum staffing (HIMS-STAFF-015)", () => {
  afterEach(() => vi.restoreAllMocks());

  const GAP = {
    on_date: NEXT,
    shift_type_id: "t-night",
    shift_type_name: "Night",
    staff_type: "nurse",
    staff_type_label: "Nurse",
    minimum: 2,
    planned: 1,
    short_by: 1,
  };

  it("warns about shifts below the minimum, without blocking planning", async () => {
    renderPage(<RotaPage />, ["rota.view", "rota.manage"], { "/rota/?": { ...WEEK, staffing_gaps: [GAP] } });
    const gaps = await screen.findByRole("region", { name: "Staffing gaps" });
    expect(gaps).toHaveTextContent("1 shift(s) this week below the minimum");
    expect(gaps).toHaveTextContent("Night: 1 of 2 planned (nurse)");
    expect(screen.getByRole("button", { name: "Plan shifts" })).toBeEnabled();
  });

  it("shows no warning when every shift has enough people", async () => {
    renderPage(<RotaPage />, ["rota.view"], {});
    await screen.findByRole("table", { name: "Rota for Cardiology" });
    expect(screen.queryByRole("region", { name: "Staffing gaps" })).toBeNull();
  });

  it("lets a planner add a minimum", async () => {
    const fetchMock = renderPage(<RotaPage />, ["rota.view", "rota.manage"], { "/staffing-requirements/": [REQUIREMENT] });
    fireEvent.click(await screen.findByRole("button", { name: "Minimum staffing" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("table", { name: "Minimum staffing" })).toHaveTextContent("Nurse");
    const form = within(dialog).getByRole("region", { name: "Add a minimum" });
    expect(within(form).getByRole("button", { name: "Add" })).toBeDisabled();
    fireEvent.mouseDown(within(form).getByRole("combobox", { name: "Shift" }));
    fireEvent.click(await screen.findByRole("option", { name: /^Night ·/ }));
    fireEvent.change(within(form).getByLabelText("At least"), { target: { value: "3" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add" }));
    await vi.waitFor(() =>
      expect(bodyOf(fetchMock, "POST", "/staffing-requirements/")).toEqual({
        department: "dep-1",
        shift_type: "t-night",
        staff_type: "",
        applies_on: "every_day",
        minimum: 3,
      }),
    );
  });

  it("changes a minimum and switches it off with its version", async () => {
    const fetchMock = renderPage(<RotaPage />, ["rota.view", "rota.manage"], { "/staffing-requirements/": [REQUIREMENT] });
    fireEvent.click(await screen.findByRole("button", { name: "Minimum staffing" }));
    const table = await screen.findByRole("table", { name: "Minimum staffing" });
    fireEvent.change(await within(table).findByLabelText("Minimum"), { target: { value: "5" } });
    fireEvent.click(within(table).getByRole("button", { name: "Save" }));
    await vi.waitFor(() =>
      expect(bodyOf(fetchMock, "PATCH", "/staffing-requirements/m1/")).toEqual({ version: 4, minimum: 5 }),
    );
    fireEvent.click(within(table).getByRole("switch", { name: /Night, Every day: in use/ }));
    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([, init]) => String(init?.body).includes('"is_active":false')),
      ).toBe(true),
    );
  });

  it("someone who only sees the rota can read the numbers, not change them", async () => {
    renderPage(<RotaPage />, ["rota.view"], {
      "/rota/?": { ...WEEK, can_manage: false },
      "/staffing-requirements/": [REQUIREMENT],
    });
    fireEvent.click(await screen.findByRole("button", { name: "Minimum staffing" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("table", { name: "Minimum staffing" })).toHaveTextContent("2");
    expect(within(dialog).queryByRole("region", { name: "Add a minimum" })).toBeNull();
    expect(within(dialog).queryByRole("switch")).toBeNull();
  });
});

describe("Leave balances (HIMS-STAFF-013)", () => {
  afterEach(() => vi.restoreAllMocks());

  const PEOPLE = {
    year: 2026,
    year_label: "2026",
    people: [{ staff_id: "st-asha", name: "Asha Nurse", balances: [BALANCE] }],
  };
  const open = async (name: string) => fireEvent.click(await screen.findByRole("tab", { name }));

  it("shows a department's balances; only the policy permission can adjust", async () => {
    renderPage(<LeavePage />, ["leave.approve"], { "/leave-balances/": PEOPLE, "/leave-requests/": [] });
    await open("Balances");
    const table = await screen.findByRole("table", { name: "Leave balances 2026" });
    expect(table).toHaveTextContent("12 left of 20 (2 carried in, 1 waiting)");
    expect(within(table).queryByRole("button", { name: /Adjust/ })).toBeNull();
  });

  it("explains when nothing is tracked yet", async () => {
    renderPage(<LeavePage />, ["leave.approve"], {
      "/leave-balances/": { ...PEOPLE, people: [{ ...PEOPLE.people[0], balances: [] }] },
      "/leave-requests/": [],
    });
    await open("Balances");
    expect(await screen.findByText(/No balances yet/)).toBeInTheDocument();
  });

  it("adjusts a balance with a reason", async () => {
    const orgWide = ["leave.approve", "leave.policy.manage"];
    const fetchMock = renderPageOrgWide(orgWide, { "/leave-balances/": PEOPLE, "/leave-adjustments/": [], "/leave-requests/": [] });
    await open("Balances");
    fireEvent.click(await screen.findByRole("button", { name: "Adjust Annual / earned leave for Asha Nurse" }));
    const dialog = await screen.findByRole("dialog");
    const save = within(dialog).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Days/), { target: { value: "-2" } });
    fireEvent.change(within(dialog).getByLabelText(/Why/), { target: { value: "Correction" } });
    fireEvent.click(save);
    await vi.waitFor(() =>
      expect(bodyOf(fetchMock, "POST", "/leave-adjustments/")).toEqual({
        staff: "st-asha",
        leave_type: "annual",
        leave_year: 2026,
        days: -2,
        reason: "Correction",
      }),
    );
  });

  it("sets an entitlement; a row from an earlier year cannot be changed", async () => {
    const fetchMock = renderPageOrgWide(["leave.approve", "leave.policy.manage"], {
      "/leave-entitlements/": [ENTITLEMENT, { ...ENTITLEMENT, id: "e0", from_year: 2025, year_label: "2025", can_change: false }],
      "/leave-requests/": [],
    });
    await open("Entitlements");
    const table = await screen.findByRole("table", { name: "Leave entitlements" });
    expect(await within(table).findByRole("button", { name: "Change Annual / earned leave from 2026" })).toBeInTheDocument();
    expect(within(table).queryByRole("button", { name: "Change Annual / earned leave from 2025" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Add an entitlement" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Days per leave year"), { target: { value: "24" } });
    fireEvent.change(within(dialog).getByLabelText("Most days carried into the next year"), { target: { value: "6" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await vi.waitFor(() =>
      expect(bodyOf(fetchMock, "POST", "/leave-entitlements/")).toMatchObject({
        leave_type: "annual",
        days: 24,
        max_carry_over: 6,
        prorate_on_joining: true,
        tracked: true,
      }),
    );
  });

  it("approving over the balance needs a tick and a reason", async () => {
    const leave = { ...LEAVE, conflicting_shifts: [], balance_after: -2 };
    const fetchMock = renderPage(<LeavePage />, ["leave.approve"], { "/leave-requests/": [leave] });
    const table = await screen.findByRole("table", { name: "Leave" });
    expect(await within(table).findByText("2 day(s) over the balance")).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "Approve leave for Asha Nurse" }));
    const dialog = await screen.findByRole("dialog");
    const approve = within(dialog).getByRole("button", { name: "Approve leave" });
    expect(approve).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Approve anyway/ }));
    expect(approve).toBeDisabled();
    fireEvent.change(within(dialog).getByRole("textbox", { name: /Reason/ }), { target: { value: "Family emergency" } });
    fireEvent.click(approve);
    await vi.waitFor(() =>
      expect(bodyOf(fetchMock, "POST", "/l2/approve/")).toMatchObject({
        allow_over_balance: true,
        note: "Family emergency",
      }),
    );
  });

  it("says what would be left when it fits", async () => {
    const leave = { ...LEAVE, conflicting_shifts: [], balance_after: 8 };
    renderPage(<LeavePage />, ["leave.approve"], { "/leave-requests/": [leave] });
    fireEvent.click(await screen.findByRole("button", { name: "Approve leave for Asha Nurse" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/8 day\(s\) of this leave are left/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("checkbox", { name: /Approve anyway/ })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Approve leave" })).toBeEnabled();
  });
});

/** Like renderPage, with hospital-wide grants (setting entitlements is a hospital-wide power). */
function renderPageOrgWide(grants: string[], routes: Record<string, unknown>) {
  const fetchMock = renderPage(<LeavePage />, [], routes);
  cleanup();
  const user: CurrentUser = {
    id: "u1",
    email: "hr@synthetic.test",
    display_name: "Synthetic HR",
    staff_member_id: null,
    grants: grants.map((permission) => ({ permission, facility_id: null, department_id: null })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LeavePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}
