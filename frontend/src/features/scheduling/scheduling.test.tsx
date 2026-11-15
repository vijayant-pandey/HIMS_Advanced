import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { localDate } from "../../components/dates";
import { currentUserKey } from "../auth/api";
import { MySchedulePage } from "../rosters/MySchedulePage";
import { addDays, mondayOf } from "../rosters/labels";
import { DoctorSchedulesPage } from "./DoctorSchedulesPage";

const MONDAY = mondayOf(localDate());
const NEXT_MONDAY = addDays(MONDAY, 7);
const DAYS = [0, 1, 2, 3, 4, 5, 6].map((n) => addDays(MONDAY, n));

function session(day: string, extra: Record<string, unknown> = {}) {
  return {
    source: "weekly",
    schedule_id: "sch-1",
    exception_id: null,
    staff_id: "st-ravi",
    department_id: "dep-1",
    department_name: "Cardiology",
    facility_id: "fac-1",
    day,
    starts_at: `${day}T03:30:00Z`,
    ends_at: `${day}T07:30:00Z`,
    hours: "09:00-13:00",
    slot_minutes: 10,
    extra_bookings_allowed: 2,
    note: "Room 4",
    status: "open",
    open_slots: 24,
    off: [],
    slots: [],
    ...extra,
  };
}

const PARTLY = session(DAYS[2]!, {
  status: "partly_off",
  open_slots: 12,
  off: [{ kind: "leave", hours: "11:00-13:00", reason: "Away: Committee", exception_id: "ex-1" }],
});
const SCHEDULE = {
  id: "sch-1",
  staff_id: "st-ravi",
  staff_name: "Ravi Kumar",
  department_id: "dep-1",
  department_name: "Cardiology",
  facility_id: "fac-1",
  weekday: 0,
  weekday_label: "Monday",
  start_time: "09:00:00",
  end_time: "13:00:00",
  hours: "09:00-13:00",
  slot_minutes: 10,
  extra_bookings_allowed: 2,
  valid_from: MONDAY,
  valid_until: null,
  is_active: true,
  note: "Room 4",
  end_reason: "",
  version: 3,
};
const AWAY = {
  id: "ex-1",
  kind: "leave",
  kind_label: "Doctor away (OPD leave)",
  staff_id: "st-ravi",
  staff_name: "Ravi Kumar",
  facility_id: "fac-1",
  facility_name: "Main Hospital",
  department_id: "dep-1",
  department_name: "Cardiology",
  start_date: DAYS[2],
  end_date: DAYS[2],
  start_time: "11:00:00",
  end_time: "13:00:00",
  hours: "11:00-13:00",
  slot_minutes: null,
  extra_bookings_allowed: null,
  reason: "Committee",
  status: "active",
  cancel_reason: "",
  version: 1,
};

function week(overrides: Record<string, unknown> = {}) {
  return {
    department_id: "dep-1",
    department_name: "Cardiology",
    facility_id: "fac-1",
    facility_name: "Main Hospital",
    start: MONDAY,
    days: DAYS,
    can_manage: true,
    can_close_facility: false,
    details: true,
    doctors: [
      {
        staff_id: "st-ravi",
        name: "Ravi Kumar",
        designation: "Consultant",
        weekly: [SCHEDULE],
        days: DAYS.map((day, n) => ({
          day,
          leave_asked: n === 4,
          sessions: n === 0 ? [session(day)] : n === 2 ? [PARTLY] : [],
        })),
      },
    ],
    exceptions: [AWAY],
    ...overrides,
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderPage(ui: ReactElement, grants: string[], routes: Record<string, unknown> = {}) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST" && url.includes("/schedule-exceptions/") && !url.includes("cancel"))
      return json({ exception: AWAY, affected: [session(DAYS[2]!)] }, 201);
    if (init?.method === "POST" || init?.method === "PATCH") return json([SCHEDULE], 201);
    for (const [path, body] of Object.entries(routes)) if (url.includes(path)) return json(body);
    if (url.includes("/doctor-schedules/week/")) return json(week());
    if (url.includes("/availability/"))
      return json({
        staff_id: "st-ravi",
        name: "Ravi Kumar",
        day: DAYS[2],
        leave_asked: false,
        sessions: [
          {
            ...PARTLY,
            slots: ["09:00", "09:10", "09:20"].map((time) => ({
              starts_at: `${DAYS[2]}T${time}:00+05:30`,
              ends_at: `${DAYS[2]}T${time}:00+05:30`,
              time,
              is_past: false,
            })),
          },
        ],
      });
    if (url.includes("/departments/"))
      return json({ count: 1, next: null, previous: null, results: [{ id: "dep-1", name: "Cardiology", facility_name: "Main Hospital", status: "active" }] });
    return json({});
  });
  const user: CurrentUser = {
    id: "u1",
    email: "head@synthetic.test",
    display_name: "Synthetic Head",
    staff_member_id: "st-head",
    grants: grants.map((permission) => ({ permission, facility_id: "fac-1", department_id: "dep-1" })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: false, required: false, verified: false, recovery_codes_remaining: 0, passkeys: 0 },
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

const sent = (fetchMock: ReturnType<typeof renderPage>, ending: string) => {
  const call = fetchMock.mock.calls.find(([url, init]) => init?.method && init.method !== "GET" && String(url).endsWith(ending));
  return call ? JSON.parse(String(call[1]!.body)) : undefined;
};

describe("Doctor schedules (HIMS-OPD-001)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows each doctor's sessions with their free slots and what takes them off", async () => {
    renderPage(<DoctorSchedulesPage />, ["appointments.view", "schedules.manage"]);
    const grid = await screen.findByRole("table", { name: "Doctor schedules for Cardiology" });
    expect(within(grid).getByText("09:00-13:00 · 24 slots")).toBeInTheDocument();
    expect(within(grid).getByText("09:00-13:00 · 12 slots")).toBeInTheDocument();
    expect(within(grid).getByText("11:00-13:00 off: Away: Committee")).toBeInTheDocument();
    expect(within(grid).getByText("Leave asked")).toBeInTheDocument();
    const weekly = screen.getByRole("table", { name: "Weekly sessions" });
    expect(weekly).toHaveTextContent("Monday 09:00-13:00");
    expect(weekly).toHaveTextContent("10 min · 2 extra");
    expect(screen.getByRole("table", { name: "Schedule exceptions" })).toHaveTextContent("Committee");
  });

  it("the front desk sees the slots and changes nothing", async () => {
    renderPage(<DoctorSchedulesPage />, ["appointments.view"], {
      "/doctor-schedules/week/": week({ can_manage: false, details: false }),
    });
    await screen.findByRole("table", { name: "Doctor schedules for Cardiology" });
    expect(screen.queryByRole("button", { name: "Add weekly session" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Doctor away" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^End / })).not.toBeInTheDocument();
  });

  it("opens a session to see its free slots", async () => {
    renderPage(<DoctorSchedulesPage />, ["appointments.view"]);
    fireEvent.click(await screen.findByRole("button", { name: /^09:00-13:00 · 12 slots, Ravi Kumar, .*, Partly off: see the slots$/ }));
    const slots = await screen.findByRole("list", { name: "Free slots" });
    expect(within(slots).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["09:00", "09:10", "09:20"]);
  });

  it("adds a weekly session on several weekdays", async () => {
    const fetchMock = renderPage(<DoctorSchedulesPage />, ["appointments.view", "schedules.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "Add weekly session" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByLabelText("Wed"));
    fireEvent.click(within(dialog).getByLabelText("Fri"));
    fireEvent.change(within(dialog).getByLabelText(/Note/), { target: { value: "Room 4" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/doctor-schedules/")).toBeTruthy());
    expect(sent(fetchMock, "/doctor-schedules/")).toMatchObject({
      staff: "st-ravi",
      department: "dep-1",
      weekdays: [0, 2, 4],
      start_time: "09:00",
      end_time: "13:00",
      slot_minutes: 10,
      valid_until: null,
      note: "Room 4",
    });
  });

  it("records a doctor away for part of a day and lists the sessions it takes off", async () => {
    const fetchMock = renderPage(<DoctorSchedulesPage />, ["appointments.view", "schedules.manage"], {
      "/doctor-schedules/week/": week({ start: NEXT_MONDAY, days: DAYS.map((d) => addDays(d, 7)) }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Doctor away" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/From/), { target: { value: "11:00" } });
    fireEvent.change(within(dialog).getByLabelText(/Until/), { target: { value: "13:00" } });
    fireEvent.change(within(dialog).getByLabelText(/Why/), { target: { value: "Committee" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Record" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/schedule-exceptions/")).toBeTruthy());
    expect(sent(fetchMock, "/schedule-exceptions/")).toMatchObject({
      kind: "leave",
      staff: "st-ravi",
      department: "dep-1",
      start_time: "11:00",
      end_time: "13:00",
      reason: "Committee",
    });
    expect(await screen.findByText(/1 session\(s\) are off/)).toBeInTheDocument();
  });

  it("closes the whole facility for a holiday only with a facility-wide grant", async () => {
    const fetchMock = renderPage(<DoctorSchedulesPage />, ["appointments.view", "schedules.manage"], {
      "/doctor-schedules/week/": week({ can_close_facility: true }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Holiday" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText(/Doctor/)).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByLabelText(/The whole facility/));
    fireEvent.change(within(dialog).getByLabelText(/Why/), { target: { value: "Diwali" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Record" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/schedule-exceptions/")).toBeTruthy());
    expect(sent(fetchMock, "/schedule-exceptions/")).toMatchObject({
      kind: "holiday",
      department: null,
      facility: "fac-1",
      staff: null,
      reason: "Diwali",
    });
  });

  it("ends a weekly session with a reason", async () => {
    const fetchMock = renderPage(<DoctorSchedulesPage />, ["appointments.view", "schedules.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "End Ravi Kumar Monday 09:00-13:00" }));
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "End session" });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Why/), { target: { value: "Moves to afternoons" } });
    fireEvent.click(submit);
    await vi.waitFor(() => expect(sent(fetchMock, "/doctor-schedules/sch-1/end/")).toBeTruthy());
    expect(sent(fetchMock, "/doctor-schedules/sch-1/end/")).toMatchObject({ version: 3, reason: "Moves to afternoons" });
  });

  it("shows doctors their own sessions on My schedule", async () => {
    renderPage(<MySchedulePage />, [], {
      "/my-opd-sessions/": {
        has_staff_record: true,
        start: MONDAY,
        days: DAYS.map((day, n) => ({ day, leave_asked: false, sessions: n === 2 ? [PARTLY] : [] })),
      },
      "/my-schedule/": { has_staff_record: true, name: "Ravi Kumar", postings: [], shifts: [], leave: [], leave_balances: [] },
    });
    const mine = await screen.findByRole("table", { name: "My OPD sessions" });
    expect(mine).toHaveTextContent("Cardiology");
    expect(mine).toHaveTextContent("12 × 10 min");
    expect(mine).toHaveTextContent("11:00-13:00 off: Away: Committee");
  });
});
