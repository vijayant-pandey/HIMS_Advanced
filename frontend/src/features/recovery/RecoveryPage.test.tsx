import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { RecoveryPage, RestoreDrillPage } from "./RecoveryPage";

const BACKUP = {
  id: "b1",
  created_at: "2026-11-08T09:00:00Z",
  created_by_name: "Synthetic Admin",
  name: "hims-local-20261108-090000",
  environment: "local",
  release: "unversioned",
  dump_bytes: 2 * 1024 * 1024,
  tables: 64,
  rows: 1234,
  documents: 3,
  documents_bytes: 1024 * 1024,
  seconds: 1.4,
  last_drill_outcome: null,
};
// Check names come from the API (apps/recovery/services.py CHECK_LABELS).
const AUDIT_LINKS_CHECK = "audit_relationships";
const DRILL = {
  id: "d1",
  started_at: "2026-11-08T09:05:00Z",
  finished_at: "2026-11-08T09:05:04Z",
  trigger: "on_demand",
  trigger_label: "Started by a person",
  requested_by_name: "Synthetic Admin",
  outcome: "failed",
  backup: "b1",
  backup_name: BACKUP.name,
  backup_created_at: BACKUP.created_at,
  restore_seconds: 3.2,
  backup_age_minutes: 5,
  problem_count: 1,
  restored_database: "hims_drill_20261108",
  checks: [
    { key: "tables", label: "Every table came back with the same rows", passed: true, detail: "64 table(s), 1234 row(s)" },
    {
      key: AUDIT_LINKS_CHECK,
      label: "Audit records still linked: chain to records, records to people, audit tables still append-only",
      passed: false,
      detail: "audit_events.audit_events_append_only no longer protects the audit log",
    },
  ],
};
const STATUS = {
  can_run_here: true,
  backup_folder: "C:/HIMS/backend/backups/local",
  tools: "PostgreSQL install folder",
  tools_problem: "",
  drill_interval_days: 90,
  drill_overdue: true,
  last_backup: BACKUP,
  last_drill: null,
  last_passed_drill: null,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderAt(path: string, grants: string[], status: unknown = STATUS) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST" && url.endsWith("/restore-drills/")) return json({ ...DRILL, outcome: "passed", problem_count: 0 }, 201);
    if (init?.method === "POST") return json(BACKUP, 201);
    if (url.includes("/backups/status/")) return json(status);
    if (url.includes("/restore-drills/d1/")) return json(DRILL);
    if (url.includes("/restore-drills/")) return json([DRILL]);
    return json([BACKUP]);
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
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/recovery" element={<RecoveryPage />} />
          <Route path="/recovery/drills/:id" element={<RestoreDrillPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const posted = (fetchMock: ReturnType<typeof renderAt>, ending: string) =>
  fetchMock.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith(ending));

describe("Backups and restore drills (HIMS-OPS-009)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("says a drill is due, makes a backup and runs a drill on it", async () => {
    const fetchMock = renderAt("/recovery", ["recovery.view", "recovery.manage"]);
    expect(await screen.findByText("Restore drill due")).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Backups" });
    expect(await within(table).findByText("Not restored yet")).toBeInTheDocument();
    expect(table).toHaveTextContent("3.0 MB");

    fireEvent.click(screen.getByRole("button", { name: "Make a backup now" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/backups/")).toBeTruthy());
    expect(await screen.findByText(/Now run a restore drill on it/)).toBeInTheDocument();

    fireEvent.click(within(table).getByRole("button", { name: `Run a restore drill on ${BACKUP.name}` }));
    await vi.waitFor(() => expect(posted(fetchMock, "/restore-drills/")).toBeTruthy());
    expect(JSON.parse(String(posted(fetchMock, "/restore-drills/")![1]!.body))).toEqual({ backup: "b1" });
    expect(await screen.findByText(/Restore drill passed: everything came back in 3.2 s/)).toBeInTheDocument();
  });

  it("auditors see the evidence but no buttons", async () => {
    renderAt("/recovery", ["recovery.view"]);
    const drills = await screen.findByRole("table", { name: "Restore drills" });
    expect(await within(drills).findByText("Failed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Make a backup now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run a restore drill/ })).not.toBeInTheDocument();
  });

  it("in a hosted environment explains that the cloud takes the backups", async () => {
    renderAt("/recovery", ["recovery.view", "recovery.manage"], { ...STATUS, can_run_here: false });
    expect(await screen.findByText(/cloud database service takes the backups/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Make a backup now" })).toBeDisabled();
  });

  it("a failed drill lists every check and says not to rely on the backup", async () => {
    renderAt("/recovery/drills/d1", ["recovery.view"]);
    expect(await screen.findByText(/Do not rely on it/)).toBeInTheDocument();
    const checks = screen.getByRole("list", { name: "Checks" });
    expect(checks).toHaveTextContent("Every table came back with the same rows");
    expect(checks).toHaveTextContent("no longer protects the audit log");
  });
});
