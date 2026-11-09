import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { BedBoard, BoardBed, BoardWard } from "../../api/types";
import { BedBoardPage, since } from "./BedBoardPage";

function bed(id: string, code: string, status: string, extra: Partial<BoardBed> = {}): BoardBed {
  return {
    id,
    code,
    bed_type: "general",
    status,
    status_reason: "",
    status_changed_at: "2026-11-09T08:00:00Z",
    version: 3,
    room_code: "r1",
    room_name: "Room 1",
    is_isolation_capable: false,
    ...extra,
  };
}

function ward(id: string, name: string, beds: BoardBed[], extra: Partial<BoardWard> = {}): BoardWard {
  const counts: Record<string, number> = {};
  for (const b of beds) counts[b.status] = (counts[b.status] ?? 0) + 1;
  return {
    id,
    code: id,
    name,
    ward_type: "general",
    building_name: "Main Block",
    floor_name: "Second floor",
    floor_level: 2,
    department: null,
    department_name: null,
    gender_restriction: "any",
    age_group: "any",
    can_change_status: true,
    bed_counts: counts,
    beds,
    ...extra,
  };
}

const BOARD: BedBoard = {
  generated_at: "2026-11-09T10:00:00Z",
  facilities: [
    { id: "f1", code: "fac-a", name: "Facility A" },
    { id: "f2", code: "fac-b", name: "Facility B" },
  ],
  facility: "f1",
  bed_counts: { available: 2, maintenance: 1 },
  available_by_type: { general: 1, icu: 1 },
  wards: [
    ward("w-gen", "General Ward", [
      bed("b1", "b01", "available"),
      bed("b2", "b02", "maintenance", { status_reason: "Broken side rail" }),
    ]),
    ward(
      "w-icu",
      "Cardiac ICU",
      [bed("b3", "c01", "available", { bed_type: "icu", is_isolation_capable: true })],
      { department_name: "Cardiology", gender_restriction: "female", can_change_status: false },
    ),
  ],
};

const HISTORY = [
  {
    id: "h1",
    from_status: "available",
    to_status: "maintenance",
    reason: "Broken side rail",
    changed_by_name: "Ward Clerk",
    changed_at: "2026-11-09T08:00:00Z",
  },
];

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderPage(board: BedBoard = BOARD) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/history/")) return json(HISTORY);
    if (url.includes("/status/") && init?.method === "POST") return json(bed("b2", "b02", "available"));
    if (url.includes("/bed-board/")) return json(board);
    return json({});
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <BedBoardPage />
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("Bed board (HIMS-FAC-008)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows every ward with its beds, counts and what is available now", async () => {
    renderPage();
    const general = await screen.findByRole("region", { name: "General Ward" });
    expect(within(general).getByText("1 available · 1 maintenance")).toBeInTheDocument();
    expect(within(general).getByRole("button", { name: /Bed B02.*General · Room R1.*Maintenance.*for \d/ })).toBeInTheDocument();
    const icu = screen.getByRole("region", { name: "Cardiac ICU" });
    expect(within(icu).getByText(/Cardiology/)).toBeInTheDocument();
    expect(within(icu).getByText("Female only")).toBeInTheDocument();
    expect(within(icu).getByText(/Isolation/)).toBeInTheDocument();
    expect(screen.getByText(/Available now: General 1 · ICU 1/)).toBeInTheDocument();
  });

  it("filters by status, bed type and isolation rooms", async () => {
    renderPage();
    await screen.findByRole("region", { name: "General Ward" });
    fireEvent.click(screen.getByRole("button", { name: "Maintenance: 1" }));
    expect(screen.queryByRole("region", { name: "Cardiac ICU" })).toBeNull();
    expect(screen.getByRole("button", { name: /Bed B02/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Bed B01/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "All: 3" }));
    fireEvent.click(screen.getByLabelText("Isolation rooms only"));
    expect(screen.queryByRole("region", { name: "General Ward" })).toBeNull();
    expect(screen.getByRole("button", { name: /Bed C01/ })).toBeInTheDocument();
  });

  it("opens a bed with its history and changes the status with its version", async () => {
    const fetchMock = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Bed B02/ }));
    const dialog = await screen.findByRole("dialog");
    const history = await within(dialog).findByRole("list", { name: "Status history" });
    expect(within(history).getByText("Available → Maintenance: Broken side rail")).toBeInTheDocument();
    expect(within(history).getByText(/Ward Clerk/)).toBeInTheDocument();
    fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "Status" }));
    fireEvent.click(await screen.findByRole("option", { name: "Available" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => {
      const sent = fetchMock.mock.calls.find(([url, init]) => String(url).includes("/b2/status/") && init?.method === "POST");
      expect(JSON.parse(String(sent?.[1]?.body))).toEqual({ version: 3, status: "available", reason: "" });
    });
  });

  it("shows the status only, without a form, where the person cannot change it", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Bed C01/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Only people who manage this ward's beds can change it/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Save" })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("asks for another facility's board when one is chosen", async () => {
    const fetchMock = renderPage();
    await screen.findByRole("region", { name: "General Ward" });
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Facility" }));
    fireEvent.click(await screen.findByRole("option", { name: "Facility B" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/bed-board/?facility=f2"))).toBe(true),
    );
  });

  it("explains when there is nothing to show", async () => {
    renderPage({ ...BOARD, facilities: [], facility: null, wards: [], bed_counts: {}, available_by_type: {} });
    expect(await screen.findByText(/No facility to show/)).toBeInTheDocument();
  });

  it("says how long a bed has had its status", () => {
    const now = new Date("2026-11-09T10:00:00Z").getTime();
    expect(since("2026-11-09T09:55:00Z", now)).toBe("for 5 min");
    expect(since("2026-11-09T07:00:00Z", now)).toBe("for 3 h");
    expect(since("2026-11-06T10:00:00Z", now)).toBe("for 3 days");
  });
});
