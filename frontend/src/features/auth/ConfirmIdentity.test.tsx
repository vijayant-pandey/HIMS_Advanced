import { QueryClient, QueryClientProvider, useMutation } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api } from "../../api/client";
import type { CurrentUser } from "../../api/types";
import { SensitiveActionsSection } from "../security/SensitiveActionsSection";
import { currentUserKey } from "./api";
import { ConfirmedDownloadButton, ConfirmIdentityProvider } from "./ConfirmIdentity";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const REFUSED = { title: "Please confirm it's you", status: 403, code: "REAUTH_REQUIRED" };

function status(extra: Record<string, unknown> = {}) {
  return {
    enabled: true,
    confirmed: false,
    confirmed_until: null,
    window_minutes: 15,
    needs_code: true,
    passkey_available: false,
    ...extra,
  };
}

/** A pretend server: the sensitive call is refused until the right password arrives. */
function server() {
  let confirmed = false;
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/auth/confirm-identity/end/")) {
      confirmed = false;
      return json(status());
    }
    if (url.endsWith("/auth/confirm-identity/")) {
      if (init?.method !== "POST")
        return json(status({ confirmed, confirmed_until: confirmed ? "2026-11-05T10:15:00Z" : null }));
      const body = JSON.parse(String(init.body)) as { password: string; code: string };
      if (body.password !== "right" || body.code !== "123456")
        return json({ title: "Not confirmed", status: 400, code: "REAUTH_FAILED", detail: "That was not accepted." }, 400);
      confirmed = true;
      return json(status({ confirmed: true, confirmed_until: "2026-11-05T10:15:00Z" }));
    }
    if (url.endsWith("/sensitive/")) return confirmed ? json({ done: true }) : json(REFUSED, 403);
    return json({});
  });
}

function SensitiveButton() {
  const action = useMutation({ mutationFn: () => api.post<{ done: boolean }>("/sensitive/", { keep: "me" }) });
  return (
    <>
      <button onClick={() => action.mutate()}>Do it</button>
      {action.isSuccess && <p>It worked</p>}
      {action.isError && <p>It failed: {action.error.message}</p>}
    </>
  );
}

function renderIt(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  queryClient.setQueryData(currentUserKey, {
    id: "u1",
    email: "admin@synthetic.test",
    display_name: "Synthetic Admin",
    staff_member_id: null,
    grants: [],
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10, passkeys: 0 },
  } as CurrentUser);
  render(
    <QueryClientProvider client={queryClient}>
      <ConfirmIdentityProvider>{ui}</ConfirmIdentityProvider>
    </QueryClientProvider>,
  );
}

function enter(password: string, code: string) {
  fireEvent.change(screen.getByLabelText(/Your password/), { target: { value: password } });
  fireEvent.change(screen.getByLabelText(/Authenticator code/), { target: { value: code } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
}

describe("Confirm it's you (HIMS-IAM-007)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("asks when the server refuses, then repeats the same request by itself", async () => {
    const fetchMock = server();
    renderIt(<SensitiveButton />);
    fireEvent.click(screen.getByRole("button", { name: "Do it" }));
    expect(await screen.findByRole("heading", { name: "Confirm it's you" })).toBeInTheDocument();
    enter("right", "123456");
    expect(await screen.findByText("It worked")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Confirm it's you" })).toBeNull();
    const calls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/sensitive/"));
    expect(calls).toHaveLength(2);
    expect(JSON.parse(String(calls[1]![1]!.body))).toEqual({ keep: "me" });
  });

  it("shows a wrong password in the dialog and stays open with the code cleared", async () => {
    server();
    renderIt(<SensitiveButton />);
    fireEvent.click(screen.getByRole("button", { name: "Do it" }));
    await screen.findByRole("heading", { name: "Confirm it's you" });
    enter("wrong", "123456");
    expect(await screen.findByText("That was not accepted.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Authenticator code/)).toHaveValue("");
    expect(screen.queryByText("It worked")).toBeNull();
  });

  it("cancelling gives up the action with the server's message", async () => {
    server();
    renderIt(<SensitiveButton />);
    fireEvent.click(screen.getByRole("button", { name: "Do it" }));
    await screen.findByRole("heading", { name: "Confirm it's you" });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(await screen.findByText(/It failed/)).toBeInTheDocument();
  });

  it("two requests at once share one dialog", async () => {
    server();
    renderIt(
      <>
        <SensitiveButton />
        <SensitiveButton />
      </>,
    );
    for (const button of screen.getAllByRole("button", { name: "Do it" })) fireEvent.click(button);
    await screen.findByRole("heading", { name: "Confirm it's you" });
    enter("right", "123456");
    await waitFor(() => expect(screen.getAllByText("It worked")).toHaveLength(2));
  });

  it("a download link asks first and does not follow the link if cancelled", async () => {
    server();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    renderIt(<ConfirmedDownloadButton href="/api/v1/x.csv">Download CSV</ConfirmedDownloadButton>);
    const link = screen.getByRole("link", { name: "Download CSV" });
    fireEvent.click(link);
    await screen.findByRole("heading", { name: "Confirm it's you" });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Confirm it's you" })).toBeNull());
    expect(assign).not.toHaveBeenCalled();

    fireEvent.click(link);
    await screen.findByRole("heading", { name: "Confirm it's you" });
    enter("right", "123456");
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/api/v1/x.csv"));
    vi.unstubAllGlobals();
  });

  it("the Security page section confirms and ends", async () => {
    server();
    renderIt(<SensitiveActionsSection />);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm now" }));
    await screen.findByRole("heading", { name: "Confirm it's you" });
    enter("right", "123456");
    fireEvent.click(await screen.findByRole("button", { name: "End now" }));
    expect(await screen.findByRole("button", { name: "Confirm now" })).toBeInTheDocument();
  });
});
