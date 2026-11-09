import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { CurrentUser, MessageTemplate } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { MessageTemplatesPage } from "./MessageTemplatesPage";

const INVITE: MessageTemplate = {
  id: "t1",
  key: "identity.invitation",
  name: "Account invitation",
  when: "Someone is given an account.",
  category: "account",
  subject: "Activate your {{hospital}} account",
  body: "Hello {{name}}, open {{link}}",
  standard_subject: "Activate your {{hospital}} account",
  standard_body: "Hello {{name}}, open {{link}}",
  is_customised: false,
  variables: [
    { name: "name", description: "The person's name", required: false },
    { name: "link", description: "The activation link", required: true },
  ],
  version: 2,
  updated_at: "2026-11-09T08:00:00Z",
  updated_by_name: null,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function problem(field: string, message: string) {
  return json({ title: "Invalid", status: 400, code: "VALIDATION_ERROR", errors: [{ field, message, code: "invalid" }] }, 400);
}

function renderPage(grants: string[], template: MessageTemplate = INVITE, refuse = false) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/preview/")) {
      return refuse
        ? problem("body", "This message must keep {{link}}: it is useless without it.")
        : json({ subject: "Activate your Synthetic Health account", body: "Hello Asha Verma, open https://hims.example" });
    }
    if (url.endsWith("/reset/")) return json({ ...template, is_customised: false });
    if (init?.method === "PATCH") {
      return refuse ? problem("body", "{{patient}} is not available in this message.") : json({ ...template, is_customised: true });
    }
    return json([template]);
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
      <MessageTemplatesPage />
    </QueryClientProvider>,
  );
  return fetchMock;
}

const CAN_CHANGE = ["notifications.view", "notifications.templates.manage"];
const called = (fetchMock: ReturnType<typeof renderPage>, method: string, ending: string) =>
  fetchMock.mock.calls.find(([url, init]) => init?.method === method && String(url).endsWith(ending));

describe("Message wording (HIMS-NOTIF-003)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists every message and whether its wording was changed", async () => {
    renderPage(CAN_CHANGE);
    const table = await screen.findByRole("table", { name: "Message wording" });
    expect(within(table).getByText("Someone is given an account.")).toBeInTheDocument();
    expect(within(table).getByText("Standard")).toBeInTheDocument();
  });

  it("shows the placeholders, marks the one that must stay, and saves the change with its version", async () => {
    const fetchMock = renderPage(CAN_CHANGE);
    fireEvent.click(await screen.findByRole("button", { name: "Account invitation" }));
    const dialog = await screen.findByRole("dialog");
    const placeholders = within(dialog).getByRole("list", { name: "Placeholders" });
    expect(within(placeholders).getByText(/The activation link \(must stay\)/)).toBeInTheDocument();
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Message" }), { target: { value: "Dear {{name}}: {{link}}" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => {
      const call = called(fetchMock, "PATCH", "/t1/");
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        version: 2,
        subject: "Activate your {{hospital}} account",
        body: "Dear {{name}}: {{link}}",
      });
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("previews with made-up details", async () => {
    renderPage(CAN_CHANGE);
    fireEvent.click(await screen.findByRole("button", { name: "Account invitation" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Preview" }));
    const preview = await within(dialog).findByRole("region", { name: "Preview" });
    expect(preview).toHaveTextContent("Hello Asha Verma");
    expect(preview).toHaveTextContent("Activate your Synthetic Health account");
  });

  it("shows the server's reason next to the message when wording is refused", async () => {
    renderPage(CAN_CHANGE, INVITE, true);
    fireEvent.click(await screen.findByRole("button", { name: "Account invitation" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText(/\{\{patient\}\} is not available/)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("goes back to the standard wording only when it was changed", async () => {
    const fetchMock = renderPage(CAN_CHANGE, { ...INVITE, is_customised: true });
    fireEvent.click(await screen.findByRole("button", { name: "Account invitation" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Use the standard wording" }));
    await waitFor(() => expect(called(fetchMock, "POST", "/t1/reset/")).toBeTruthy());
  });

  it("someone who may only look can read and preview, not change", async () => {
    renderPage(["notifications.view"]);
    fireEvent.click(await screen.findByRole("button", { name: "Account invitation" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("textbox", { name: "Message" })).toBeDisabled();
    expect(within(dialog).queryByRole("button", { name: "Save" })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Preview" })).toBeInTheDocument();
  });
});
