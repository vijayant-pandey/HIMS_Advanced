import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { PerformanceCheckPage, PerformancePage } from "./PerformancePage";

/** Performance screen (HIMS-DATA-002, HIMS-OPS-017; areas: HIMS-DATA-003). Synthetic data. */

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const check = (overrides: Record<string, unknown>) => ({
  id: "c1",
  kind: "indexes",
  kind_label: "Index check (query plans)",
  started_at: "2026-11-10T09:00:00Z",
  finished_at: "2026-11-10T09:00:05Z",
  trigger: "volume",
  trigger_label: "Volume check (throw-away copy with synthetic records)",
  requested_by_name: null,
  outcome: "passed",
  database: "hims_volume (throw-away copy, synthetic records)",
  environment: "local",
  release: "",
  dataset_rows: 3_400_000,
  problem_count: 0,
  summary: "22 of 22 queries use their index in time",
  ...overrides,
});

const INDEX_CHECK = check({});
const TIMES = check({
  id: "c2",
  kind: "response_times",
  kind_label: "Response times",
  outcome: "failed",
  problem_count: 1,
  summary: "23 of 24 screens within their target",
});

const STATUS = {
  can_measure_here: true,
  page_target_ms: 300,
  search_target_ms: 500,
  last_index_check: INDEX_CHECK,
  last_response_times: TIMES,
  last_volume_index_check: INDEX_CHECK,
  last_volume_response_times: TIMES,
};

const DETAIL = {
  ...TIMES,
  dataset: { audit_events: 2_000_000, user_sessions: 300_000 },
  query_results: [],
  screen_results: [
    {
      key: "audit_newest",
      label: "Audit log (newest first)",
      path: "/api/v1/audit-events/",
      status: 200,
      samples: 20,
      p50_ms: 120,
      p95_ms: 640,
      max_ms: 700,
      queries: 6,
      target_ms: 500,
      passed: false,
      detail: "p95 640 ms is over the 500 ms target.",
    },
  ],
};

const query = (key: string, label: string, area: string, passed: boolean) => ({
  key,
  label,
  area,
  table: area === "Patients" ? "patients" : "audit_events",
  table_rows: 500_000,
  expected_indexes: [`${key}_idx`],
  indexes_used: passed ? [`${key}_idx`] : [],
  full_reads: passed ? [] : ["patients"],
  ms: passed ? 0.4 : 180,
  budget_ms: 100,
  rows: 25,
  passed,
  detail: passed ? "" : "Reads patients without the expected index (500,000 rows).",
});

const INDEX_DETAIL = {
  ...INDEX_CHECK,
  id: "c4",
  outcome: "failed",
  problem_count: 1,
  summary: "2 of 3 queries use their index in time",
  dataset: { patients: 500_000 },
  query_results: [
    query("audit_newest", "Audit log: newest events first", "Audit log", true),
    query("patient_by_mrn", "Patient search: exact MRN", "Patients", true),
    query("patient_list", "Patients: newest registrations first", "Patients", false),
  ],
  screen_results: [],
};

function renderPage(grants: string[], path = "/performance") {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST") return json({ ...INDEX_CHECK, id: "c3", dataset: {}, query_results: [], screen_results: [] }, 201);
    if (url.includes("/performance-checks/status/")) return json(STATUS);
    if (url.includes("/performance-checks/c2/")) return json(DETAIL);
    if (url.includes("/performance-checks/c4/")) return json(INDEX_DETAIL);
    return json([INDEX_CHECK, TIMES]);
  });
  const user: CurrentUser = {
    id: "u1",
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
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/performance" element={<PerformancePage />} />
          <Route path="/performance/:id" element={<PerformanceCheckPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

afterEach(() => vi.restoreAllMocks());

describe("Performance", () => {
  it("shows the targets, the latest volume results and every check; viewers cannot run one", async () => {
    renderPage(["platform.performance.view"]);
    expect(await screen.findByText("300 ms")).toBeInTheDocument();
    expect(screen.getByText("500 ms")).toBeInTheDocument();
    expect(screen.getAllByText("22 of 22 queries use their index in time").length).toBeGreaterThan(0);
    const table = await screen.findByRole("table", { name: "Performance checks" });
    expect(within(table).getByText("Response times")).toBeInTheDocument();
    expect(within(table).getByText("Failed")).toBeInTheDocument();
    expect(within(table).getAllByText("3,400,000")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Run the index check now" })).toBeNull();
  });

  it("runs the index check now and links to its result", async () => {
    const fetchMock = renderPage(["platform.performance.view", "platform.performance.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "Run the index check now" }));
    expect(await screen.findByText(/Index check passed/)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => init?.method === "POST" && String(url).endsWith("/performance-checks/"),
        ),
      ).toBe(true),
    );
  });

  it("shows each screen's times against its target", async () => {
    renderPage(["platform.performance.view"], "/performance/c2");
    const table = await screen.findByRole("table", { name: "Screens" });
    const row = within(table).getByText("Audit log (newest first)").closest("tr")!;
    expect(within(row).getByText("640 ms")).toBeInTheDocument();
    expect(within(row).getByText("Failed")).toBeInTheDocument();
    expect(within(row).getByText(/over the 500 ms target/)).toBeInTheDocument();
    expect(screen.getByText(/audit_events 2,000,000/)).toBeInTheDocument();
  });

  it("groups the queries by area and shows one area at a time", async () => {
    renderPage(["platform.performance.view"], "/performance/c4");
    const table = await screen.findByRole("table", { name: "Queries" });
    expect(within(table).getAllByRole("row")).toHaveLength(4); // header + 3
    const areas = screen.getByRole("group", { name: "Show one area" });
    const patients = within(areas).getByRole("button", { name: "Patients: 1 of 2 OK" });
    expect(within(areas).getByRole("button", { name: "Audit log: 1 of 1 OK" })).toBeInTheDocument();
    fireEvent.click(patients);
    expect(patients).toHaveAttribute("aria-pressed", "true");
    expect(within(table).queryByText("Audit log: newest events first")).toBeNull();
    expect(within(table).getByText("Patients: newest registrations first")).toBeInTheDocument();
    expect(within(table).getByText(/without the expected index/)).toBeInTheDocument();
    fireEvent.click(within(areas).getByRole("button", { name: "All areas" }));
    expect(within(table).getAllByRole("row")).toHaveLength(4);
  });
});
