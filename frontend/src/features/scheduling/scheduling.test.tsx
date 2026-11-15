import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { localDate } from "../../components/dates";
import { currentUserKey } from "../auth/api";
import { MySchedulePage } from "../rosters/MySchedulePage";
import { addDays, mondayOf } from "../rosters/labels";
import { AppointmentsPage } from "./AppointmentsPage";
import { DoctorSchedulesPage } from "./DoctorSchedulesPage";
import { OpdQueuePage } from "./OpdQueuePage";

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
    booked: 0,
    extra_booked: 0,
    free_slots: 24,
    off: [],
    slots: [],
    ...extra,
  };
}

const PARTLY = session(DAYS[2]!, {
  status: "partly_off",
  open_slots: 12,
  booked: 2,
  free_slots: 10,
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

const BOOKED = {
  id: "ap-1",
  patient_id: "pt-asha",
  patient_name: "Asha Kumar",
  patient_mrn: "MRN-00000007",
  patient_restricted: false,
  staff_id: "st-ravi",
  staff_name: "Ravi Kumar",
  department_id: "dep-1",
  department_name: "Cardiology",
  facility_id: "fac-1",
  starts_at: `${DAYS[2]}T03:30:00Z`,
  ends_at: `${DAYS[2]}T03:40:00Z`,
  local_date: DAYS[2],
  time: "09:00",
  kind: "new",
  kind_label: "New",
  source: "front_desk",
  source_label: "At the front desk",
  status: "booked",
  status_label: "Booked",
  reason: "Chest pain",
  is_extra: false,
  rescheduled_from_id: null,
  rescheduled_to_id: null,
  booked_by_name: "Synthetic Desk",
  created_at: `${DAYS[0]}T03:30:00Z`,
  cancel_reason: "",
  cancel_reason_label: "",
  cancel_note: "",
  cancelled_at: null,
  token_number: null,
  checked_in_at: null,
  called_at: null,
  seen_at: null,
  version: 2,
};

function slotsAt(day: string, booked: string[]) {
  return ["09:00", "09:10", "09:20"].map((time) => ({
    starts_at: `${day}T${time}:00+05:30`,
    ends_at: `${day}T${time}:00+05:30`,
    time,
    is_past: false,
    is_booked: booked.includes(time),
  }));
}

function dayView(overrides: Record<string, unknown> = {}) {
  return {
    department_id: "dep-1",
    department_name: "Cardiology",
    facility_id: "fac-1",
    facility_name: "Main Hospital",
    day: DAYS[2],
    can_book: true,
    doctors: [
      {
        staff_id: "st-ravi",
        name: "Ravi Kumar",
        designation: "Consultant",
        leave_asked: false,
        sessions: [{ ...session(DAYS[2]!), booked: 1, free_slots: 2, slots: slotsAt(DAYS[2]!, ["09:00"]) }],
      },
    ],
    appointments: [BOOKED, { ...BOOKED, id: "ap-0", time: "09:10", status: "cancelled", status_label: "Cancelled", cancel_reason: "patient_request", cancel_reason_label: "The patient asked" }],
    ...overrides,
  };
}

const APPOINTMENT_ROUTES = {
  "/appointments/day/": dayView(),
  "/appointments/to-rebook/": [{ appointment: { ...BOOKED, id: "ap-9", patient_name: "Bina Rao", patient_mrn: "MRN-00000009" }, why: "Away: Conference" }],
  "/patients/": {
    count: 1,
    next: null,
    previous: null,
    results: [{ id: "pt-asha", name: "Asha Kumar", mrn: "MRN-00000007", age: "40 y", sex: "female", hidden: false }],
  },
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderPage(
  ui: ReactElement,
  grants: string[],
  routes: Record<string, unknown> = {},
  state: unknown = null,
) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST" && url.includes("/schedule-exceptions/") && !url.includes("cancel"))
      return json({ exception: AWAY, affected: [session(DAYS[2]!)], bookings: [BOOKED] }, 201);
    if (init?.method === "POST" && url.includes("/appointments/")) return json(BOOKED, 201);
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
      <MemoryRouter initialEntries={[{ pathname: "/", state }]}>{ui}</MemoryRouter>
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
    expect(within(grid).getByText("09:00-13:00 · 12 slots · 2 booked")).toBeInTheDocument();
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
    fireEvent.click(await screen.findByRole("button", { name: /^09:00-13:00 · 12 slots · 2 booked, Ravi Kumar, .*, Partly off: see the slots$/ }));
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
    expect(screen.getByText(/1 booked patient\(s\) to move or cancel/)).toBeInTheDocument();
    expect(screen.getByText(/Asha Kumar \(MRN-00000007\) with Ravi Kumar/)).toBeInTheDocument();
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
    expect(mine).toHaveTextContent("12 × 10 min · 2 booked");
    expect(mine).toHaveTextContent("11:00-13:00 off: Away: Committee");
  });
});

describe("Appointments (HIMS-OPD-002)", () => {
  afterEach(() => vi.restoreAllMocks());
  const grants = ["appointments.view", "appointments.manage"];

  it("shows each doctor's slots, free or booked, the day's appointments and the patients to move", async () => {
    renderPage(<AppointmentsPage />, grants, APPOINTMENT_ROUTES);
    const slots = await screen.findByRole("list", { name: "Slots, Ravi Kumar, 09:00-13:00" });
    expect(within(slots).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "09:00 booked",
      "09:10",
      "09:20",
    ]);
    expect(screen.getByText(/09:00-13:00 · 1 booked · 2 free/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Appointments in Cardiology" });
    expect(table).toHaveTextContent("Asha Kumar (MRN-00000007)");
    expect(table).toHaveTextContent("Cancelled (The patient asked)");
    const toMove = screen.getByRole("table", { name: "Appointments to move" });
    expect(toMove).toHaveTextContent("Bina Rao (MRN-00000009)");
    expect(toMove).toHaveTextContent("Away: Conference");
  });

  it("books a free slot for a patient found by search", async () => {
    const fetchMock = renderPage(<AppointmentsPage />, grants, APPOINTMENT_ROUTES);
    fireEvent.click(await screen.findByRole("button", { name: "09:10 free: book with Ravi Kumar" }));
    const dialog = await screen.findByRole("dialog");
    const book = within(dialog).getByRole("button", { name: "Book" });
    expect(book).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Find the patient/), { target: { value: "Asha" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Search" }));
    fireEvent.click(await within(dialog).findByLabelText(/Asha Kumar · MRN-00000007/));
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Chest pain" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Book" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/appointments/")).toBeTruthy());
    expect(sent(fetchMock, "/appointments/")).toMatchObject({
      patient: "pt-asha",
      staff: "st-ravi",
      department: "dep-1",
      starts_at: `${DAYS[2]}T09:10:00+05:30`,
      kind: "new",
      source: "front_desk",
      reason: "Chest pain",
      extra: false,
    });
  });

  it("books the patient chosen in the chart, and over the slots when the session allows it", async () => {
    const fetchMock = renderPage(<AppointmentsPage />, grants, APPOINTMENT_ROUTES, {
      patient: { id: "pt-asha", name: "Asha Kumar", mrn: "MRN-00000007" },
    });
    expect(await screen.findByText(/Booking for Asha Kumar \(MRN-00000007\)/)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Book over the slots (2 left)" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Patient: Asha Kumar (MRN-00000007)");
    fireEvent.click(within(dialog).getByRole("button", { name: "Book" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/appointments/")).toBeTruthy());
    expect(sent(fetchMock, "/appointments/")).toMatchObject({
      patient: "pt-asha",
      starts_at: `${DAYS[2]}T09:00:00+05:30`,
      extra: true,
    });
  });

  it("cancels with the reason and moves to another free slot", async () => {
    const fetchMock = renderPage(<AppointmentsPage />, grants, APPOINTMENT_ROUTES);
    const table = await screen.findByRole("table", { name: "Appointments in Cardiology" });
    fireEvent.click(within(table).getByRole("button", { name: "Cancel Asha Kumar, 09:00" }));
    let dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel appointment" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/appointments/ap-1/cancel/")).toBeTruthy());
    expect(sent(fetchMock, "/appointments/ap-1/cancel/")).toMatchObject({ version: 2, reason: "patient_request" });
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    // Wait for it: while the closing dialog fades out, the page behind it is still hidden.
    fireEvent.click(await within(table).findByRole("button", { name: "Move Asha Kumar, 09:00" }));
    dialog = await screen.findByRole("dialog");
    fireEvent.mouseDown(await within(dialog).findByLabelText(/Free slot/));
    fireEvent.click(await screen.findByRole("option", { name: "09:20 (09:00-13:00)" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Move" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/appointments/ap-1/reschedule/")).toBeTruthy());
    expect(sent(fetchMock, "/appointments/ap-1/reschedule/")).toMatchObject({
      version: 2,
      starts_at: `${DAYS[2]}T09:20:00+05:30`,
      staff: "st-ravi",
      extra: false,
    });
  });

  it("the head of department sees the day and books nothing", async () => {
    renderPage(<AppointmentsPage />, ["appointments.view"], {
      ...APPOINTMENT_ROUTES,
      "/appointments/day/": dayView({ can_book: false }),
    });
    await screen.findByRole("list", { name: "Slots, Ravi Kumar, 09:00-13:00" });
    expect(screen.queryByRole("button", { name: /book with/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Move / })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Book over the slots/ })).not.toBeInTheDocument();
  });
});

describe("OPD queue (HIMS-OPD-003)", () => {
  afterEach(() => vi.restoreAllMocks());
  const grants = ["appointments.view", "appointments.manage"];
  const TODAY = localDate();
  const person = (id: string, name: string, mrn: string, extra: Record<string, unknown>) => ({
    ...BOOKED,
    id,
    patient_id: `pt-${id}`,
    patient_name: name,
    patient_mrn: mrn,
    local_date: TODAY,
    ...extra,
  });
  const arrived = new Date(Date.now() - 12 * 60_000).toISOString();
  const QUEUE = {
    department_id: "dep-1",
    department_name: "Cardiology",
    facility_id: "fac-1",
    facility_name: "Main Hospital",
    day: TODAY,
    is_today: true,
    can_manage: true,
    doctors: [
      {
        staff_id: "st-ravi",
        name: "Ravi Kumar",
        designation: "Consultant",
        leave_asked: false,
        sessions: [session(TODAY)],
      },
    ],
    appointments: [
      person("ap-1", "Asha Kumar", "MRN-1", {
        status: "in_consultation",
        token_number: 1,
        checked_in_at: arrived,
        called_at: arrived,
      }),
      person("ap-2", "Bina Rao", "MRN-2", { status: "checked_in", token_number: 2, checked_in_at: arrived }),
      person("ap-3", "Esha Shah", "MRN-3", {
        status: "checked_in",
        token_number: 3,
        checked_in_at: arrived,
        source: "walk_in",
        source_label: "Walk-in",
        version: 1,
      }),
      person("ap-4", "Chitra Das", "MRN-4", {
        status: "booked",
        time: "09:30",
        starts_at: "2020-01-01T04:00:00Z",
        version: 5,
      }),
      person("ap-5", "Dev Iyer", "MRN-5", { status: "booked", time: "12:30", starts_at: "2999-01-01T07:00:00Z" }),
      person("ap-6", "Farah Ali", "MRN-6", { status: "no_show", status_label: "Did not come" }),
      person("ap-7", "Gita Moved", "MRN-7", {
        status: "cancelled",
        cancel_reason: "rescheduled",
        cancel_reason_label: "Moved to another time",
      }),
    ],
  };
  const ROUTES = { ...APPOINTMENT_ROUTES, "/appointments/queue/": QUEUE };

  it("shows each doctor's patients by token: with the doctor, waiting, still to come, did not come", async () => {
    renderPage(<OpdQueuePage />, grants, ROUTES);
    const table = await screen.findByRole("table", { name: "Patients of Ravi Kumar" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0]!.textContent)).toEqual(["1", "2", "3", "—", "—", "—"]);
    expect(rows[0]).toHaveTextContent("With the doctor");
    expect(rows[1]).toHaveTextContent("Waiting 12 min");
    expect(rows[2]).toHaveTextContent("Walk-in");
    expect(rows[3]).toHaveTextContent("Still to come");
    expect(rows[5]).toHaveTextContent("Did not come");
    expect(table).not.toHaveTextContent("Gita Moved"); // moved before the day: not in the queue
    const queue = screen.getByRole("region", { name: "Queue, Ravi Kumar" });
    expect(queue).toHaveTextContent("Waiting 2");
    expect(queue).toHaveTextContent("Seen 0");
  });

  it("checks a patient in, calls the next token, marks seen and did not come", async () => {
    const fetchMock = renderPage(<OpdQueuePage />, grants, ROUTES);
    fireEvent.click(await screen.findByRole("button", { name: "Check in Chitra Das" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/appointments/ap-4/check-in/")).toEqual({ version: 5 }));
    fireEvent.click(screen.getByRole("button", { name: "Call next for Ravi Kumar" }));
    await vi.waitFor(() =>
      expect(sent(fetchMock, "/appointments/call-next/")).toEqual({ department: "dep-1", staff: "st-ravi" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Seen: Asha Kumar" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/appointments/ap-1/seen/")).toEqual({ version: 2 }));
    fireEvent.click(screen.getByRole("button", { name: "Did not come: Chitra Das" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/appointments/ap-4/no-show/")).toEqual({ version: 5 }));
    // Only once the time has passed; a waiting patient may leave; a missed one may be undone.
    expect(screen.queryByRole("button", { name: "Did not come: Dev Iyer" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Left before being seen: Esha Shah" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/appointments/ap-3/left/")).toEqual({ version: 1, note: "" }));
    expect(screen.getByRole("button", { name: "Undo did not come: Farah Ali" })).toBeInTheDocument();
  });

  it("checks in a walk-in found by search", async () => {
    const fetchMock = renderPage(<OpdQueuePage />, grants, ROUTES);
    fireEvent.click(await screen.findByRole("button", { name: "Walk in for Ravi Kumar" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Check in" })).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Find the patient/), { target: { value: "Asha" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Search" }));
    fireEvent.click(await within(dialog).findByLabelText(/Asha Kumar · MRN-00000007/));
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Fever" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Check in" }));
    await vi.waitFor(() => expect(sent(fetchMock, "/appointments/walk-in/")).toBeTruthy());
    expect(sent(fetchMock, "/appointments/walk-in/")).toEqual({
      patient: "pt-asha",
      staff: "st-ravi",
      department: "dep-1",
      kind: "new",
      reason: "Fever",
    });
  });

  it("asks for today on the facility's clock, not the browser's", async () => {
    const fetchMock = renderPage(<OpdQueuePage />, grants, ROUTES);
    await screen.findByRole("table", { name: "Patients of Ravi Kumar" });
    const asked = fetchMock.mock.calls.map(([url]) => String(url)).find((url) => url.includes("/appointments/queue/"));
    expect(asked).not.toContain("date=");
    expect(screen.getByLabelText("Day")).toHaveValue(TODAY); // the day the server answered for
  });

  it("the head of department sees the queue and moves nothing; another day is shown as it was", async () => {
    renderPage(<OpdQueuePage />, ["appointments.view"], {
      ...ROUTES,
      "/appointments/queue/": { ...QUEUE, can_manage: false, is_today: false },
    });
    await screen.findByRole("table", { name: "Patients of Ravi Kumar" });
    expect(screen.getByText(/is shown as it was/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Call next/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Check in/ })).not.toBeInTheDocument();
  });
});
