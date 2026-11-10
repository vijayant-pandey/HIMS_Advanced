import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { CurrentUser, Equipment } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { EquipmentPage } from "./EquipmentPage";

const VENT: Equipment = {
  id: "e1",
  asset_tag: "ICU-VENT-01",
  name: "Ventilator",
  category: "life_support",
  category_label: "Life support (ventilator, defibrillator)",
  facility: "f1",
  facility_name: "Facility A",
  department: "d1",
  department_name: "Cardiology",
  ward: null,
  ward_name: null,
  room: null,
  room_name: null,
  location_note: "Store 2",
  manufacturer: "Acme",
  model_name: "V100",
  serial_number: "SN-1",
  status: "maintenance",
  status_label: "Under maintenance",
  status_reason: "Battery fault",
  status_changed_at: "2026-11-09T08:00:00Z",
  purchased_on: null,
  warranty_until: null,
  last_service_on: "2026-05-01",
  next_service_due: "2026-11-01",
  last_calibrated_on: null,
  next_calibration_due: null,
  due_state: "overdue",
  notes: "",
  version: 3,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-11-09T08:00:00Z",
};

const VISIT = {
  id: "v1",
  kind: "service",
  kind_label: "Service",
  performed_on: "2026-05-01",
  performed_by: "Acme Biomed",
  notes: "New filter",
  next_due: "2026-11-01",
  recorded_by_name: "Ward Clerk",
  recorded_at: "2026-05-01T10:00:00Z",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function user(grants: CurrentUser["grants"]): CurrentUser {
  return {
    id: "u1",
    email: "officer@synthetic.test",
    display_name: "Synthetic Officer",
    staff_member_id: null,
    grants,
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: false, verified: true, recovery_codes_remaining: 10, passkeys: 0 },
  };
}

type Grant = CurrentUser["grants"][number];

const MANAGER: Grant[] = [
  { permission: "equipment.view", facility_id: null, department_id: null },
  { permission: "equipment.manage", facility_id: null, department_id: null },
];

function renderPage(grants = MANAGER, items: Equipment[] = [VENT]) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/organization/letterhead/")) {
      return json({ display_name: "Synthetic Health", legal_name: "Synthetic", lines: ["1 Synthetic Road"], has_logo: false, version: 1 });
    }
    if (url.includes("/history/")) return json([VISIT]);
    if (url.includes("/service-records/")) return json(VISIT, 201);
    if (init?.method === "POST" || init?.method === "PATCH") return json(VENT, 201);
    if (url.includes("/facilities/") && url.includes("/locations/")) return json({ buildings: [] });
    if (url.includes("/facilities/")) {
      return json({ count: 1, next: null, previous: null, results: [{ id: "f1", name: "Facility A" }] });
    }
    if (url.includes("/departments/")) {
      return json({ count: 1, next: null, previous: null, results: [{ id: "d1", name: "Cardiology" }] });
    }
    return json({ count: items.length, next: null, previous: null, results: items });
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user(grants));
  render(
    <QueryClientProvider client={queryClient}>
      <EquipmentPage />
    </QueryClientProvider>,
  );
  return fetchMock;
}

const sent = (fetchMock: ReturnType<typeof renderPage>, ending: string) => {
  const call = fetchMock.mock.calls.find(([url, init]) => init?.method && init.method !== "GET" && String(url).endsWith(ending));
  return call ? (JSON.parse(String(call[1]?.body)) as Record<string, unknown>) : undefined;
};

describe("Equipment register (HIMS-FAC-009)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists what, where, status and when it is due", async () => {
    renderPage();
    const table = await screen.findByRole("table", { name: "Equipment" });
    const row = (await within(table).findByRole("button", { name: "ICU-VENT-01" })).closest("tr")!;
    expect(row).toHaveTextContent("Ventilator");
    expect(row).toHaveTextContent("Cardiology · Store 2");
    expect(row).toHaveTextContent("Under maintenance");
    expect(row).toHaveTextContent("Overdue");
  });

  it("works when Add is pressed before the facilities have loaded", async () => {
    let release = () => {};
    const waiting = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = renderPage();
    const answer = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input).includes("/facilities/") && !String(input).includes("/locations/")) await waiting;
      return answer(input, init);
    });
    fireEvent.click(await screen.findByRole("button", { name: "Add equipment" }));
    const form = await screen.findByRole("dialog");
    fireEvent.change(within(form).getByLabelText(/Asset tag/), { target: { value: "pump-2" } });
    fireEvent.change(within(form).getByRole("textbox", { name: /^Name/ }), { target: { value: "Pump" } });
    release();
    const add = within(form).getByRole("button", { name: "Add" });
    await waitFor(() => expect(add).not.toBeDisabled());
    fireEvent.click(add);
    await waitFor(() => expect(sent(fetchMock, "/equipment/")).toMatchObject({ facility: "f1", asset_tag: "pump-2" }));
  });

  it("asks the server to filter", async () => {
    const fetchMock = renderPage();
    await screen.findByRole("table", { name: "Equipment" });
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "vent" } });
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Due" }));
    fireEvent.click(await screen.findByRole("option", { name: "Overdue" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes("search=vent") && String(url).includes("due=overdue")),
      ).toBe(true),
    );
  });

  it("shows the details and the visits, and records a visit", async () => {
    const fetchMock = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "ICU-VENT-01" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Battery fault")).toBeInTheDocument();
    const visits = await within(dialog).findByRole("list", { name: "Visits" });
    expect(within(visits).getByText(/Service on .*Acme Biomed/)).toBeInTheDocument();
    expect(within(visits).getByText(/Recorded by Ward Clerk/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Record a visit" }));
    const form = screen.getAllByRole("dialog").at(-1)!;
    fireEvent.change(within(form).getByLabelText(/Done by/), { target: { value: "Acme" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent(fetchMock, "/e1/service-records/")).toMatchObject({ kind: "service", performed_by: "Acme" }));
  });

  it("needs a reason to take equipment out of service", async () => {
    const fetchMock = renderPage(MANAGER, [{ ...VENT, status: "in_service", status_label: "In service", status_reason: "" }]);
    fireEvent.click(await screen.findByRole("button", { name: "ICU-VENT-01" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Change status" }));
    const form = screen.getAllByRole("dialog").at(-1)!;
    fireEvent.mouseDown(within(form).getByRole("combobox", { name: "Status" }));
    fireEvent.click(await screen.findByRole("option", { name: "Out of service" }));
    const save = within(form).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    fireEvent.change(within(form).getByLabelText(/Reason/), { target: { value: "Cracked screen" } });
    fireEvent.click(save);
    await waitFor(() =>
      expect(sent(fetchMock, "/e1/status/")).toEqual({ version: 3, status: "out_of_service", reason: "Cracked screen" }),
    );
  });

  it("adds equipment; empty dates and locations go as empty", async () => {
    const fetchMock = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Add equipment" }));
    const form = await screen.findByRole("dialog");
    const add = within(form).getByRole("button", { name: "Add" });
    expect(add).toBeDisabled();
    fireEvent.change(within(form).getByLabelText(/Asset tag/), { target: { value: "pump-1" } });
    fireEvent.change(within(form).getByRole("textbox", { name: /^Name/ }), { target: { value: "Pump" } });
    await waitFor(() => expect(add).not.toBeDisabled());
    fireEvent.click(add);
    await waitFor(() =>
      expect(sent(fetchMock, "/equipment/")).toMatchObject({
        facility: "f1",
        asset_tag: "pump-1",
        name: "Pump",
        department: null,
        next_service_due: null,
      }),
    );
  });

  it("someone who may only look gets no buttons to change anything", async () => {
    renderPage([{ permission: "equipment.view", facility_id: null, department_id: null }]);
    expect(screen.queryByRole("button", { name: "Add equipment" })).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "ICU-VENT-01" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("button", { name: "Edit" })).toBeNull();
    expect(within(dialog).queryByRole("button", { name: "Record a visit" })).toBeNull();
  });

  it("a department grant changes only that department's equipment", async () => {
    const grants: Grant[] = [
      { permission: "equipment.view", facility_id: "f1", department_id: null },
      { permission: "equipment.manage", facility_id: "f1", department_id: "d1" },
    ];
    renderPage(grants, [VENT, { ...VENT, id: "e2", asset_tag: "OTHER-1", department: "d2" }]);
    fireEvent.click(await screen.findByRole("button", { name: "OTHER-1" }));
    const other = await screen.findByRole("dialog");
    expect(within(other).queryByRole("button", { name: "Edit" })).toBeNull();
    fireEvent.click(within(other).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "ICU-VENT-01" }));
    expect(within(await screen.findByRole("dialog")).getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  it("a retired item takes no visits", async () => {
    renderPage(MANAGER, [{ ...VENT, status: "retired", status_label: "Retired", due_state: "" }]);
    fireEvent.click(await screen.findByRole("button", { name: "ICU-VENT-01" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("button", { name: "Record a visit" })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Change status" })).toBeInTheDocument();
  });

  it("prints with the letterhead", async () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    renderPage();
    const letterhead = await screen.findByTestId("print-letterhead");
    expect(letterhead).toHaveTextContent("Synthetic Health");
    expect(letterhead).toHaveTextContent("1 Synthetic Road");
    expect(letterhead).toHaveTextContent("Equipment register");
    fireEvent.click(screen.getByRole("button", { name: "Print" }));
    expect(print).toHaveBeenCalled();
  });
});
