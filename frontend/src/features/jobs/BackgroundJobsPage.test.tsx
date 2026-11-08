import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { BackgroundJobsPage } from "./BackgroundJobsPage";

const FAILED = {
  id: "e1",
  event_type: "identity.invitation.issued",
  event_label: "Account invitation (sends the email)",
  occurred_at: "2026-11-08T09:00:00Z",
  status: "dead",
  status_label: "Dead (retries exhausted)",
  attempts: 12,
  available_at: "2026-11-08T12:00:00Z",
  last_error: "ConnectionError",
  aggregate_type: "invitation",
  aggregate_id: "i-1",
  resolved_at: null,
  resolved_by_name: null,
  resolution_note: "",
};
const HEALTH = {
  waiting: 1,
  oldest_waiting_minutes: 40,
  retrying: 1,
  stuck: 1,
  failed: 1,
  dismissed: 0,
  published_last_24h: 25,
  stuck_after_minutes: 15,
  retention_days: 30,
  max_attempts: 12,
  last_cleanup: { at: "2026-11-08T02:00:00Z", events_deleted: 140, markers_deleted: 140 },
  attention: ["1 event(s) failed after every retry and need a decision"],
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderPage(grants: string[], health: unknown = HEALTH) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST") return json({ ...FAILED, status: "pending", attempts: 0, resolution_note: "Fixed" });
    if (url.includes("/health/")) return json(health);
    return json([FAILED]);
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
      <MemoryRouter>
        <BackgroundJobsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const posted = (fetchMock: ReturnType<typeof renderPage>, ending: string) =>
  fetchMock.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith(ending));

describe("Background jobs (HIMS-PLAT-014)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows what needs a look and sends a failed event again with a reason", async () => {
    const fetchMock = renderPage(["platform.jobs.view", "platform.jobs.manage"]);
    expect(await screen.findByText(/failed after every retry and need a decision/)).toBeInTheDocument();
    expect(screen.getByText(/140 old event\(s\) removed/)).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Background events" });
    expect(await within(table).findByText("ConnectionError")).toBeInTheDocument();

    fireEvent.click(within(table).getByRole("button", { name: /^Send again:/ }));
    const dialog = await screen.findByRole("dialog");
    const send = within(dialog).getByRole("button", { name: "Send again" });
    expect(send).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Email server fixed" } });
    fireEvent.click(send);
    await vi.waitFor(() => expect(posted(fetchMock, "/background-jobs/e1/send-again/")).toBeTruthy());
    expect(JSON.parse(String(posted(fetchMock, "/background-jobs/e1/send-again/")![1]!.body))).toEqual({
      reason: "Email server fixed",
    });
  });

  it("dismissing asks for a reason too", async () => {
    const fetchMock = renderPage(["platform.jobs.view", "platform.jobs.manage"]);
    const table = await screen.findByRole("table", { name: "Background events" });
    fireEvent.click(await within(table).findByRole("button", { name: /^Dismiss:/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Invitation was for a test account" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Dismiss" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/background-jobs/e1/dismiss/")).toBeTruthy());
  });

  it("view-only people see everything but cannot decide", async () => {
    renderPage(["platform.jobs.view"], { ...HEALTH, attention: [], failed: 0 });
    expect(await screen.findByText("Everything is flowing: nothing needs a look.")).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Background events" });
    await within(table).findByText("ConnectionError");
    expect(within(table).queryByRole("button")).not.toBeInTheDocument();
  });
});
