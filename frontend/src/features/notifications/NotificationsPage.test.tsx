import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { NotificationsPage } from "./NotificationsPage";

const FAILED = {
  id: "n1",
  created_at: "2026-10-30T09:00:00Z",
  channel: "email",
  channel_label: "Email",
  category: "account",
  template: "identity.invitation",
  recipients: ["nurse@synthetic.test"],
  subject: "Activate your account",
  body: "Open this link:\nhttp://app.test/activate#token=[hidden]\n",
  status: "failed",
  status_label: "Failed, will retry",
  attempts: 1,
  last_error: "ConnectionRefusedError: smtp down",
  next_attempt_at: "2026-10-30T09:05:00Z",
  sent_at: null,
  skip_reason: "",
  can_send_again: true,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderPage(grants: string[]) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST" && url.endsWith("/send-again/")) return json({ ...FAILED, status: "sent", attempts: 2, can_send_again: false });
    if (init?.method === "POST") return json({ ...FAILED, id: "n2", status: "sent", subject: "test", last_error: "" }, 201);
    return json({ count: 1, next: null, previous: null, results: [FAILED] });
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
        <NotificationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const posted = (fetchMock: ReturnType<typeof renderPage>, ending: string) =>
  fetchMock.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith(ending));

describe("NotificationsPage (HIMS-NOTIF-001)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the log; the stored copy hides sign-in links; a failed message can be sent again", async () => {
    const fetchMock = renderPage(["notifications.view", "notifications.manage"]);
    const table = await screen.findByRole("table", { name: "Messages" });
    expect(await within(table).findByText("Failed, will retry")).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "Activate your account" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("#token=[hidden]");
    expect(dialog).toHaveTextContent("ConnectionRefusedError");
    fireEvent.click(within(dialog).getByRole("button", { name: "Send again now" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/n1/send-again/")).toBeTruthy());
  });

  it("sends a test SMS", async () => {
    const fetchMock = renderPage(["notifications.view", "notifications.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "Send a test message" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "Channel" }));
    fireEvent.click(await screen.findByRole("option", { name: "SMS" }));
    fireEvent.change(within(dialog).getByLabelText(/Mobile number/), { target: { value: "+919876543210" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Send test" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/notifications/test/")).toBeTruthy());
    expect(JSON.parse(String(posted(fetchMock, "/notifications/test/")![1]!.body))).toEqual({
      channel: "sms",
      to: "+919876543210",
    });
  });

  it("view-only people cannot send", async () => {
    renderPage(["notifications.view"]);
    await screen.findByRole("table", { name: "Messages" });
    expect(screen.queryByRole("button", { name: "Send a test message" })).not.toBeInTheDocument();
  });
});
