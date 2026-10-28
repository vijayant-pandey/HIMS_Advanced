import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { AuditEvent } from "../../api/types";
import { AuditLogPage } from "./AuditLogPage";

const EVENT: AuditEvent = {
  id: "e1",
  occurred_at: "2026-10-28T09:30:00Z",
  facility_id: "f1",
  facility_name: "Main Hospital",
  actor_type: "user",
  actor_id: "u1",
  actor_name: "Synthetic Admin",
  actor_email: "admin@synthetic.test",
  action: "facility.updated",
  action_label: "Facility changed",
  category: "Hospital setup",
  resource_type: "facility",
  resource_id: "f1",
  outcome: "success",
  reason: "",
  request_id: "ref-4242-abcd-0000",
  ip_address: "127.0.0.1",
  changes: { before: { phone: "" }, after: { phone: "+91-80-0000" } },
  metadata: {},
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderAt(path = "/audit") {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/audit-events/actions/"))
      return json([
        { action: "auth.login", label: "Signed in", category: "Sign-in and security" },
        { action: "facility.updated", label: "Facility changed", category: "Hospital setup" },
      ]);
    return json({ count: 1, next: null, previous: null, results: [EVENT] });
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AuditLogPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const searches = (fetchMock: ReturnType<typeof renderAt>) =>
  fetchMock.mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.includes("/audit-events/?") || url.endsWith("/audit-events/"));

describe("AuditLogPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("searches only when asked (every search is itself audited)", async () => {
    const fetchMock = renderAt();
    fireEvent.change(screen.getByLabelText("Person"), { target: { value: "admin" } });
    expect(searches(fetchMock)).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("Facility changed")).toBeInTheDocument();
    expect(screen.getByText("Synthetic Admin (admin@synthetic.test)")).toBeInTheDocument();
    const [url] = searches(fetchMock);
    expect(url).toContain("person=admin");
    expect(url).toContain("page_size=50");
    expect(url).not.toContain("request_id=");
  });

  it("opens a reference number straight from the link", async () => {
    const fetchMock = renderAt("/audit?request_id=ref-4242-abcd-0000");
    expect(await screen.findByText("Facility changed")).toBeInTheDocument();
    expect(searches(fetchMock)[0]).toContain("request_id=ref-4242-abcd-0000");
  });

  it("limits events to the chosen area and offers a CSV of the same filters", async () => {
    renderAt();
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Area" }));
    fireEvent.click(await screen.findByRole("option", { name: "Sign-in and security" }));
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Event" }));
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByRole("option", { name: "Signed in" })).toBeInTheDocument();
    expect(within(listbox).queryByRole("option", { name: "Facility changed" })).not.toBeInTheDocument();
    fireEvent.click(within(listbox).getByRole("option", { name: "Signed in" }));

    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    const download = await screen.findByRole("link", { name: "Download CSV" });
    expect(download.getAttribute("href")).toBe(
      "/api/v1/audit-events/export/?category=auth&action=auth.login",
    );
  });

  it("shows what changed, before and after", async () => {
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.click(await screen.findByText("Facility changed"));
    const dialog = await screen.findByRole("dialog");
    const changes = within(dialog).getByRole("table", { name: "What changed" });
    expect(within(changes).getByText("phone")).toBeInTheDocument();
    expect(within(changes).getByText("+91-80-0000")).toBeInTheDocument();
    expect(within(dialog).getByText("ref-4242-abcd-0000")).toBeInTheDocument();
  });
});
