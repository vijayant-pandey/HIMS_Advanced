import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { CompliancePage } from "./CompliancePage";
import { ReportIncidentDialog } from "./ReportIncidentDialog";

const REQUIREMENT = {
  id: "q1",
  code: "CERTIN-REPORTING",
  jurisdiction: "IN",
  regulation: "CERT-In Directions (28 April 2022)",
  citation: "IT Act section 70B(6)",
  title: "Report cyber incidents within 6 hours",
  summary: "Report listed cyber incidents within 6 hours.",
  hims_support: "Incident log sets a 6-hour deadline.",
  status: "implemented",
  status_label: "Implemented, not verified",
  owner: "",
  evidence: "",
  next_review_on: null,
  reviewed_by_name: null,
  reviewed_at: null,
  version: 3,
};
const RISK = {
  id: "r1",
  code: "R-001",
  title: "Stolen staff password",
  description: "d",
  category: "access",
  likelihood: 4,
  impact: 4,
  score: 16,
  treatment: "mitigate",
  treatment_label: "Reduce it",
  mitigation: "Two-factor",
  status: "treating",
  status_label: "Being treated",
  owner: "",
  review_on: null,
  acceptance_reason: "",
  version: 1,
};
const INCIDENT = {
  id: "i1",
  title: "Lost laptop",
  description: "Left on a train",
  severity: "high",
  severity_label: "High",
  status: "reported",
  status_label: "Reported",
  detected_at: "2026-11-04T10:00:00Z",
  occurred_at: null,
  personal_data_affected: false,
  people_affected: null,
  actions_taken: "",
  closure_summary: "",
  closed_at: null,
  reported_by_name: "Plain Staff",
  version: 2,
  notifications: [
    {
      id: "n1",
      kind: "cert_in",
      kind_label: "India: CERT-In report",
      due_at: "2026-11-04T16:00:00Z",
      status: "pending",
      status_label: "To do",
      is_overdue: true,
      done_at: null,
      done_by_name: null,
      reference: "",
      note: "",
    },
  ],
};

const BROWSER_REPORT = {
  id: "b1",
  day: "2026-11-04",
  directive: "script-src-elem",
  blocked: "https://blocked.example",
  page_path: "/staff/{id}",
  occurrences: 3,
  last_seen_at: "2026-11-04T10:00:00Z",
  reviewed_by_name: null,
  reviewed_at: null,
  review_note: "",
  version: 2,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const DATABASE_CHECKS = [
  { key: "separate_users", label: "The app connects as its own user, not as the owner", passed: true, detail: "app connects as hims_local_dev_app" },
  { key: "evidence_protected", label: "The app cannot change, delete or empty the audit log and other evidence", passed: true, detail: "add-only: audit_events" },
];
let databaseAccess: unknown = {
  separated: true,
  set_up: true,
  developer_pc: true,
  connected_as: "hims_local_dev_app",
  app_user: "hims_local_dev_app",
  readonly_user: "hims_local_dev_readonly",
  breakglass_user: "hims_local_dev_breakglass",
  checks: DATABASE_CHECKS,
};

function renderIt(ui: React.ReactElement, grants: string[], entry = "/compliance") {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST" && url.endsWith("/security-incidents/"))
      return json({ id: "new-ref", title: "x", detected_at: "2026-11-04T10:00:00Z" }, 201);
    if (init?.method === "POST") return json(INCIDENT);
    if (init?.method === "PATCH") return json(REQUIREMENT);
    if (url.includes("/compliance-summary/"))
      return json({
        country: "IN",
        requirements_total: 21,
        requirements_by_status: { implemented: 2, not_started: 12, in_progress: 7 },
        risks_open: 15,
        risks_high: 9,
        incidents_open: 1,
        notifications_overdue: 1,
      });
    if (url.includes("/compliance-requirements/")) return json([REQUIREMENT]);
    if (url.includes("/compliance-risks/")) return json([RISK]);
    if (url.includes("/security-incidents/")) return json([INCIDENT]);
    if (url.includes("/security/database-access/")) return json(databaseAccess);
    if (url.includes("/security/status/"))
      return json({
        policy_mode: "enforcing",
        proxies_configured: false,
        your_address: "203.0.113.9",
        reports_to_review: 1,
      });
    if (url.includes("/browser-security-reports/")) return json([BROWSER_REPORT]);
    return json({});
  });
  const user: CurrentUser = {
    id: "u1",
    email: "officer@synthetic.test",
    display_name: "Synthetic Officer",
    staff_member_id: null,
    grants: grants.map((permission) => ({ permission, facility_id: null, department_id: null })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const MANAGE = ["compliance.view", "compliance.manage"];
const sent = (fetchMock: ReturnType<typeof renderIt>, method: string, ending: string) =>
  fetchMock.mock.calls.find(([url, init]) => init?.method === method && String(url).endsWith(ending));

describe("CompliancePage (HIMS-COMP)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the summary, warns about overdue notices and updates a requirement", async () => {
    const fetchMock = renderIt(<CompliancePage />, MANAGE);
    expect(await screen.findByText(/1 legal notification\(s\) are overdue/)).toBeInTheDocument();
    expect(screen.getByText("21 requirements")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Report cyber incidents within 6 hours" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Who answers for it"), { target: { value: "Synthetic Officer" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(sent(fetchMock, "PATCH", "/compliance-requirements/q1/")).toBeTruthy());
    expect(JSON.parse(String(sent(fetchMock, "PATCH", "/compliance-requirements/q1/")![1]!.body))).toMatchObject({
      version: 3,
      owner: "Synthetic Officer",
    });
  });

  it("lists risks; view-only people cannot add", async () => {
    renderIt(<CompliancePage />, ["compliance.view"]);
    fireEvent.click(await screen.findByRole("tab", { name: "Risks" }));
    expect(await screen.findByText("Stolen staff password")).toBeInTheDocument();
    expect(screen.getByText("16")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add a risk" })).not.toBeInTheDocument();
  });

  it("opens an incident from an alert link and records a legal notice", async () => {
    const fetchMock = renderIt(<CompliancePage />, MANAGE, "/compliance?incident=i1");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Left on a train")).toBeInTheDocument();
    expect(within(dialog).getByText("Overdue")).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Reference: India: CERT-In report"), { target: { value: "ACK-77" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Mark done" }));
    await vi.waitFor(() => expect(sent(fetchMock, "POST", "/security-incidents/i1/notifications/n1/")).toBeTruthy());
    expect(JSON.parse(String(sent(fetchMock, "POST", "/security-incidents/i1/notifications/n1/")![1]!.body))).toEqual({
      status: "done",
      reference: "ACK-77",
      note: "",
    });
  });

  it("anyone can report an incident and gets a reference", async () => {
    const fetchMock = renderIt(<ReportIncidentDialog onClose={() => {}} />, []);
    const dialog = await screen.findByRole("dialog");
    const send = within(dialog).getByRole("button", { name: "Send report" });
    expect(send).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/What happened/), { target: { value: "Lost laptop" } });
    fireEvent.change(within(dialog).getByLabelText(/Details/), { target: { value: "Left on a train" } });
    fireEvent.click(send);
    expect(await within(dialog).findByText(/Reference: new-ref/)).toBeInTheDocument();
    expect(sent(fetchMock, "POST", "/security-incidents/")![1]!.headers).toBeTruthy();
  });
});

describe("Browser protection tab", () => {
  it("lists what was blocked and sends the review with its version", async () => {
    const fetchMock = renderIt(<CompliancePage />, ["compliance.view", "compliance.manage"]);
    fireEvent.click(await screen.findByRole("tab", { name: "Browser protection" }));
    const table = await screen.findByRole("table", { name: "What browsers blocked" });
    expect(within(table).getByText("https://blocked.example")).toBeInTheDocument();
    expect(await screen.findByText("203.0.113.9")).toBeInTheDocument();
    expect(screen.getByText("Blocking is on for the admin console and server pages.")).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: /^Mark reviewed/ }));
    await waitFor(() => {
      const review = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/b1/review/"));
      expect(JSON.parse(String(review?.[1]?.body))).toEqual({ version: 2 });
    });
  });

  it("does not offer the review without compliance.manage", async () => {
    renderIt(<CompliancePage />, ["compliance.view"]);
    fireEvent.click(await screen.findByRole("tab", { name: "Browser protection" }));
    const table = await screen.findByRole("table", { name: "What browsers blocked" });
    expect(within(table).getByText("Not reviewed")).toBeInTheDocument();
    expect(within(table).queryByRole("button")).toBeNull();
  });
});

describe("Database access tab (HIMS-OPS-007)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows that the app runs with its own limited database user", async () => {
    renderIt(<CompliancePage />, ["compliance.view"]);
    fireEvent.click(await screen.findByRole("tab", { name: "Database access" }));
    expect(await screen.findByText("Database access is separated: every check passed.")).toBeInTheDocument();
    const checks = screen.getByRole("list", { name: "Database access checks" });
    expect(checks).toHaveTextContent("cannot change, delete or empty the audit log");
    expect(screen.getByText(/hims_local_dev_breakglass \(break-glass/)).toBeInTheDocument();
  });

  it("on a developer PC not yet set up, explains how to set it up", async () => {
    databaseAccess = {
      separated: false,
      set_up: false,
      developer_pc: true,
      connected_as: "postgres",
      app_user: "hims_local_dev_app",
      readonly_user: "hims_local_dev_readonly",
      breakglass_user: "hims_local_dev_breakglass",
      checks: [{ ...DATABASE_CHECKS[0], passed: false, detail: "the app's own database user has not been set up yet" }],
    };
    renderIt(<CompliancePage />, ["compliance.view"]);
    fireEvent.click(await screen.findByRole("tab", { name: "Database access" }));
    expect(await screen.findByText(/Not set up on this computer yet/)).toBeInTheDocument();
    expect(screen.getByText("python manage.py setup_database_roles --write-env")).toBeInTheDocument();
  });
});
