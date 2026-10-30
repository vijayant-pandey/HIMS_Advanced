import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AuditIntegrityDetailPage, AuditIntegrityPage } from "./AuditIntegrityPage";

const HEAD = "ab12".repeat(16);
const PASSED = {
  id: "c1",
  started_at: "2026-10-30T09:00:00Z",
  finished_at: "2026-10-30T09:00:02Z",
  trigger: "scheduled",
  trigger_label: "Daily automatic check",
  requested_by_name: null,
  outcome: "passed",
  events_sealed: 4,
  entries_checked: 1234,
  last_sequence: 1234,
  chain_head: HEAD,
  problem_count: 0,
  unsealed_overdue: 0,
};
const FAILED = {
  ...PASSED,
  id: "c2",
  trigger: "on_demand",
  trigger_label: "Started by a person",
  requested_by_name: "Synthetic Auditor",
  outcome: "failed",
  problem_count: 2,
  problems: [
    {
      kind: "event_changed",
      text: "This event was changed after it was sealed.",
      sequence: 17,
      event_id: "e17",
      action: "facility.updated",
      action_label: "Facility changed",
      occurred_at: "2026-10-29T10:00:00+00:00",
    },
    {
      kind: "links_missing",
      text: "Links of the chain are missing (sealed events were removed).",
      sequence: 20,
      last_missing: 22,
    },
  ],
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderAt(path: string, overrides: { status?: unknown; list?: unknown } = {}) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST") return json({ ...PASSED, id: "c3", problems: [] }, 201);
    if (url.includes("/status/"))
      return json(
        overrides.status ?? {
          sealed_events: 1234,
          last_sealed_at: "2026-10-30T09:00:01Z",
          chain_head: HEAD,
          waiting_to_be_sealed: 2,
          key_id: "k1",
          check_interval_hours: 24,
          last_check: PASSED,
        },
      );
    if (url.includes("/audit-integrity-checks/c2/")) return json(FAILED);
    return json(overrides.list ?? [PASSED]);
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/audit/integrity" element={<AuditIntegrityPage />} />
          <Route path="/audit/integrity/:id" element={<AuditIntegrityDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("AuditIntegrityPage (HIMS-SEC-010)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the latest result, the chain fingerprint and past checks", async () => {
    renderAt("/audit/integrity");
    expect(await screen.findByText("Records sealed")).toBeInTheDocument();
    expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
    expect(screen.getByText(HEAD)).toBeInTheDocument();
    expect(screen.getByText("k1")).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Past integrity checks" });
    expect(table).toHaveTextContent("Daily automatic check");
    expect(table).toHaveTextContent("1,234");
    expect(screen.queryByText(/possible security incident/)).not.toBeInTheDocument();
  });

  it("runs a check now", async () => {
    const fetchMock = renderAt("/audit/integrity", {
      status: {
        sealed_events: 0,
        last_sealed_at: null,
        chain_head: "",
        waiting_to_be_sealed: 5,
        key_id: "local",
        check_interval_hours: 24,
        last_check: null,
      },
      list: [],
    });
    expect(await screen.findByText("Never checked")).toBeInTheDocument();
    expect(await screen.findByText("No checks yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check now" }));
    expect(await screen.findByText(/Passed: 1,234 record\(s\) checked, nothing was changed\./)).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(post![0])).toMatch(/\/audit-integrity-checks\/$/);
  });

  it("warns loudly when the latest check found problems", async () => {
    renderAt("/audit/integrity", {
      status: {
        sealed_events: 1234,
        last_sealed_at: null,
        chain_head: HEAD,
        waiting_to_be_sealed: 0,
        key_id: "k1",
        check_interval_hours: 24,
        last_check: FAILED,
      },
    });
    expect(await screen.findByText(/possible security incident/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Details" })).toHaveAttribute("href", "/audit/integrity/c2");
  });

  it("lists each problem in plain words", async () => {
    renderAt("/audit/integrity/c2");
    const table = await screen.findByRole("table", { name: "Problems found" });
    expect(table).toHaveTextContent("This event was changed after it was sealed.");
    expect(table).toHaveTextContent("Record #17");
    expect(table).toHaveTextContent("Facility changed");
    expect(table).toHaveTextContent("Records #20 to #22");
    expect(screen.getByText(/possible security incident/)).toBeInTheDocument();
    expect(screen.getByText(/Started by a person \(Synthetic Auditor\)/)).toBeInTheDocument();
  });
});
