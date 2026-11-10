import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { CompliancePage } from "./CompliancePage";

/** Retention tab (HIMS-COMP-006). Synthetic data. */

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const category = (overrides: Record<string, unknown>) => ({
  table: "user_sessions",
  what: "Sign-ins that ended before the cut-off.",
  minimum_days: 365,
  keep_days: null,
  pending_keep_days: null,
  pending_from: null,
  updated_by_name: null,
  updated_at: "2026-11-10T09:00:00Z",
  version: 1,
  would_delete: 0,
  held: 0,
  skipped: "No period set: kept for ever.",
  ...overrides,
});

const STATUS = {
  categories: [
    category({ category: "sign_ins", label: "Sign-in register", keep_days: 400, version: 3, would_delete: 12, held: 2, skipped: "" }),
    category({
      category: "messages",
      label: "Message log (emails and SMS)",
      what: "Messages sent before the cut-off.",
      minimum_days: 90,
      keep_days: 400,
      pending_keep_days: 120,
      pending_from: "2026-11-17T09:00:00Z",
      version: 2,
      skipped: "",
    }),
  ],
  active_holds: 1,
  wait_days: 7,
  last_run: null,
};

const HOLD = {
  id: "h1",
  reference: "Matter 2026-14",
  reason: "Expected dispute",
  categories: ["sign_ins"],
  subject_name: "Synthetic Nurse",
  subject_email: "nurse@synthetic.test",
  is_active: true,
  placed_by_name: "Synthetic Officer",
  placed_at: "2026-11-09T10:00:00Z",
  released_by_name: null,
  released_at: null,
  release_reason: "",
  version: 1,
};

const RUN = {
  id: "run1",
  started_at: "2026-11-10T02:00:00Z",
  finished_at: "2026-11-10T02:00:03Z",
  trigger: "scheduled",
  trigger_label: "Daily job",
  run_by_name: null,
  deleted_total: 7,
  details: {
    sign_ins: { keep_days: 400, older_than: "x", skipped: "", deleted: 7, held: 2, more_left: true, period_applied_now: false },
  },
};

function renderTab(grants: string[]) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST" && url.endsWith("/retention/run/")) return json({ ...RUN, id: "run2", deleted_total: 3 }, 201);
    if (init?.method === "POST" && url.includes("/retention/periods/")) return json(STATUS);
    if (init?.method === "POST" && url.endsWith("/legal-holds/")) return json(HOLD, 201);
    if (init?.method === "POST" && url.endsWith("/release/")) return json({ ...HOLD, is_active: false });
    if (url.includes("/retention-runs/")) return json([RUN]);
    if (url.includes("/retention/")) return json(STATUS);
    if (url.includes("/legal-holds/")) return json([HOLD]);
    if (url.includes("/compliance-summary/"))
      return json({
        country: "IN",
        requirements_total: 0,
        requirements_by_status: {},
        risks_open: 0,
        risks_high: 0,
        incidents_open: 0,
        notifications_overdue: 0,
      });
    return json([]);
  });
  const user: CurrentUser = {
    id: "u1",
    email: "officer@synthetic.test",
    display_name: "Synthetic Officer",
    staff_member_id: null,
    grants: grants.map((permission) => ({ permission, facility_id: null, department_id: null })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10, passkeys: 0 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/compliance"]}>
        <CompliancePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("tab", { name: "Retention" }));
  return fetchMock;
}

const posted = (fetchMock: ReturnType<typeof vi.spyOn>, ending: string) => {
  const call = (fetchMock.mock.calls as [RequestInfo, RequestInit | undefined][]).find(
    ([url, init]) => init?.method === "POST" && String(url).endsWith(ending),
  );
  return call?.[1]?.body ? JSON.parse(String(call[1].body)) : call ? {} : undefined;
};

afterEach(() => vi.restoreAllMocks());

const MANAGE = ["compliance.view", "compliance.manage"];

describe("Retention tab", () => {
  it("shows each kind with its period, the waiting change, the preview, holds and runs", async () => {
    renderTab(["compliance.view"]);
    const table = await screen.findByRole("table", { name: "Retention periods" });
    const signIns = within(table).getByText("Sign-in register").closest("tr")!;
    expect(within(signIns).getByText("400 days")).toBeInTheDocument();
    expect(within(signIns).getByText("12")).toBeInTheDocument();
    expect(within(signIns).getByText("2")).toBeInTheDocument();
    const messages = within(table).getByText("Message log (emails and SMS)").closest("tr")!;
    expect(within(messages).getByText(/120 days from/)).toBeInTheDocument();
    expect(screen.getByText(/1 legal hold\(s\) active/)).toBeInTheDocument();
    const holds = await screen.findByRole("table", { name: "Legal holds" });
    expect(within(holds).getByText("Matter 2026-14")).toBeInTheDocument();
    expect(within(holds).getByText("Synthetic Nurse (nurse@synthetic.test)")).toBeInTheDocument();
    const runs = await screen.findByRole("table", { name: "Purge runs" });
    expect(within(runs).getByText("Daily job")).toBeInTheDocument();
    expect(within(runs).getByText(/7 \(more next run\)/)).toBeInTheDocument();
    // Viewers change nothing.
    expect(screen.queryByRole("button", { name: /Change period/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Run the purge now" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Place a legal hold" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Release legal hold/ })).toBeNull();
  });

  it("changes a period, refusing less than the minimum", async () => {
    const fetchMock = renderTab(MANAGE);
    fireEvent.click(await screen.findByRole("button", { name: "Change period: Sign-in register" }));
    const dialog = await screen.findByRole("dialog");
    const days = within(dialog).getByLabelText("Keep for (days)");
    fireEvent.change(days, { target: { value: "30" } });
    expect(within(dialog).getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.change(days, { target: { value: "730" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(posted(fetchMock, "/retention/periods/sign_ins/")).toEqual({ keep_days: 730, version: 3 }));
  });

  it("keeps for ever, or cancels a shorter period that is waiting", async () => {
    const fetchMock = renderTab(MANAGE);
    fireEvent.click(await screen.findByRole("button", { name: "Change period: Message log (emails and SMS)" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/120 days is waiting to apply/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel it" }));
    await waitFor(() => expect(posted(fetchMock, "/retention/periods/messages/")).toEqual({ keep_days: 400, version: 2 }));
  });

  it("places a legal hold on chosen kinds and one account", async () => {
    const fetchMock = renderTab(MANAGE);
    fireEvent.click(await screen.findByRole("button", { name: "Place a legal hold" }));
    const dialog = await screen.findByRole("dialog");
    const place = within(dialog).getByRole("button", { name: "Place the hold" });
    expect(place).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Reference/), { target: { value: "Matter 2026-15" } });
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Investigation" } });
    fireEvent.click(within(dialog).getByLabelText("Message log (emails and SMS)"));
    fireEvent.change(within(dialog).getByLabelText(/Only records about this account/), {
      target: { value: "nurse@synthetic.test" },
    });
    fireEvent.click(place);
    await waitFor(() =>
      expect(posted(fetchMock, "/legal-holds/")).toEqual({
        reference: "Matter 2026-15",
        reason: "Investigation",
        categories: ["messages"],
        subject_email: "nurse@synthetic.test",
      }),
    );
  });

  it("releases a hold only with a reason", async () => {
    const fetchMock = renderTab(MANAGE);
    fireEvent.click(await screen.findByRole("button", { name: "Release legal hold Matter 2026-14" }));
    const dialog = await screen.findByRole("dialog");
    const release = within(dialog).getByRole("button", { name: "Release" });
    expect(release).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Why the hold can end/), { target: { value: "Settled" } });
    fireEvent.click(release);
    await waitFor(() => expect(posted(fetchMock, "/legal-holds/h1/release/")).toEqual({ version: 1, reason: "Settled" }));
  });

  it("runs the purge now and says how much went", async () => {
    const fetchMock = renderTab(MANAGE);
    fireEvent.click(await screen.findByRole("button", { name: "Run the purge now" }));
    expect(await screen.findByText("Purge run: 3 record(s) deleted.")).toBeInTheDocument();
    expect(posted(fetchMock, "/retention/run/")).toEqual({});
  });
});
