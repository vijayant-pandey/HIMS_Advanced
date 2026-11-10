import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { ThemeSelectionProvider } from "../../app/ThemeSelection";
import { PasskeysSection } from "../security/PasskeysSection";
import { currentUserKey } from "./api";
import { LoginPage } from "./LoginPage";
import { fromBase64url, passkeyErrorText, passkeysSupported, toBase64url } from "./webauthn";

/** Passkeys (HIMS-IAM-014). The browser's passkey API is replaced by a stand-in device. */

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const bytes = (...values: number[]) => new Uint8Array(values).buffer;

function fakeDevice() {
  const create = vi.fn(async (_options: CredentialCreationOptions) => ({
    id: "Y3JlZA",
    rawId: bytes(99, 114, 101, 100),
    type: "public-key",
    response: {
      clientDataJSON: bytes(1, 2),
      attestationObject: bytes(3, 4),
      getTransports: () => ["internal"],
    },
    getClientExtensionResults: () => ({}),
  }));
  const get = vi.fn(async (_options: CredentialRequestOptions) => ({
    id: "Y3JlZA",
    rawId: bytes(99, 114, 101, 100),
    type: "public-key",
    response: { clientDataJSON: bytes(5), authenticatorData: bytes(6), signature: bytes(7), userHandle: null },
    getClientExtensionResults: () => ({}),
  }));
  vi.stubGlobal("PublicKeyCredential", function PublicKeyCredential() {});
  Object.defineProperty(navigator, "credentials", { value: { create, get }, configurable: true });
  return { create, get };
}

const OPTIONS = {
  public_key: {
    challenge: "AQID",
    rp: { id: "localhost", name: "Synthetic Health HIMS" },
    user: { id: "BAUG", name: "admin@synthetic.test", displayName: "Admin" },
    pubKeyCredParams: [{ type: "public-key", alg: -7 }],
    excludeCredentials: [{ id: "Y3JlZA", type: "public-key", transports: ["internal"] }],
    allowCredentials: [{ id: "Y3JlZA", type: "public-key" }],
  },
};

const signedIn: CurrentUser = {
  id: "u1",
  email: "admin@synthetic.test",
  display_name: "Admin",
  staff_member_id: null,
  grants: [],
  organization: { display_name: "Synthetic Health", country: "IN" },
  mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 8, passkeys: 1 },
};

function renderWith(ui: React.ReactNode, user: CurrentUser | null = signedIn) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <ThemeSelectionProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={ui} />
            <Route path="/" element={<p>Home</p>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeSelectionProvider>,
  );
}

const posted = (fetchMock: ReturnType<typeof vi.spyOn>, ending: string) =>
  (fetchMock.mock.calls as [RequestInfo, RequestInit | undefined][]).find(
    ([url, init]) => init?.method === "POST" && String(url).endsWith(ending),
  );

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("base64url and the browser's passkey support", () => {
  it("round-trips bytes the way WebAuthn writes them", () => {
    const value = new Uint8Array([0, 251, 255, 62, 63]);
    const text = toBase64url(value);
    expect(text).not.toMatch(/[+/=]/);
    expect(new Uint8Array(fromBase64url(text))).toEqual(value);
  });

  it("says so when the browser has no passkeys, and turns device errors into plain words", () => {
    vi.stubGlobal("PublicKeyCredential", undefined);
    expect(passkeysSupported()).toBe(false);
    expect(passkeyErrorText(new DOMException("x", "NotAllowedError"))).toMatch(/cancelled or timed out/);
    expect(passkeyErrorText(new Error("server"))).toBeNull();
  });
});

describe("sign-in with a passkey", () => {
  function mockServer() {
    return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/auth/csrf/")) return new Response(null, { status: 204 });
      if (url.endsWith("/auth/login/")) return json(202, { mfa_required: true, passkey_available: true, detail: "x" });
      if (url.endsWith("/auth/login/passkey-options/")) return json(200, OPTIONS);
      if (url.endsWith("/auth/login/passkey/")) return json(200, signedIn);
      return json(200, {});
    });
  }

  async function passwordStep() {
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@synthetic.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByText("Two-factor sign-in");
  }

  it("offers the passkey after the password, sends the device's answer and signs in", async () => {
    const device = fakeDevice();
    const fetchMock = mockServer();
    renderWith(<LoginPage />, null);
    await passwordStep();
    expect(screen.getByLabelText("Authentication code")).toBeInTheDocument(); // the code still works
    fireEvent.click(screen.getByRole("button", { name: "Use a passkey" }));
    expect(await screen.findByText("Home")).toBeInTheDocument();
    const request = device.get.mock.calls[0]![0];
    expect(new Uint8Array(request.publicKey!.challenge as ArrayBuffer)).toEqual(new Uint8Array([1, 2, 3]));
    const sent = JSON.parse(String(posted(fetchMock, "/auth/login/passkey/")![1]!.body));
    expect(sent.credential).toMatchObject({ id: "Y3JlZA", rawId: "Y3JlZA", response: { signature: "Bw" } });
  });

  it("explains a cancelled passkey and leaves the code to use", async () => {
    const device = fakeDevice();
    device.get.mockRejectedValueOnce(new DOMException("cancelled", "NotAllowedError"));
    mockServer();
    renderWith(<LoginPage />, null);
    await passwordStep();
    fireEvent.click(screen.getByRole("button", { name: "Use a passkey" }));
    expect(await screen.findByText(/cancelled or timed out/)).toBeInTheDocument();
    expect(screen.getByLabelText("Authentication code")).toBeInTheDocument();
  });

  it("does not offer it in a browser without passkeys", async () => {
    vi.stubGlobal("PublicKeyCredential", undefined);
    mockServer();
    renderWith(<LoginPage />, null);
    await passwordStep();
    expect(screen.queryByRole("button", { name: "Use a passkey" })).toBeNull();
  });
});

describe("Passkeys on the Security page", () => {
  const LIST = [
    { id: "p1", name: "Work laptop", backed_up: false, created_at: "2026-11-10T09:00:00Z", last_used_at: null },
  ];

  function mockServer() {
    return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/auth/passkeys/add-options/")) return json(200, OPTIONS);
      if (url.endsWith("/auth/passkeys/add/")) return json(201, { ...LIST[0], id: "p2", name: "Phone" });
      if (url.endsWith("/remove/")) return new Response(null, { status: 204 });
      if (url.endsWith("/auth/passkeys/") && (init?.method ?? "GET") === "GET") return json(200, LIST);
      return json(200, signedIn);
    });
  }

  it("lists passkeys and adds one with a name", async () => {
    const device = fakeDevice();
    const fetchMock = mockServer();
    renderWith(<PasskeysSection />);
    const list = await screen.findByRole("list", { name: "Your passkeys" });
    expect(within(list).getByText("Work laptop")).toBeInTheDocument();
    expect(within(list).getByText(/not used yet/)).toBeInTheDocument();
    const add = screen.getByRole("button", { name: "Add a passkey" });
    expect(add).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Name for this passkey"), { target: { value: "Phone" } });
    fireEvent.click(add);
    expect(await screen.findByText(/Passkey added/)).toBeInTheDocument();
    const created = device.create.mock.calls[0]![0].publicKey!;
    expect(new Uint8Array(created.user.id as ArrayBuffer)).toEqual(new Uint8Array([4, 5, 6]));
    expect(created.excludeCredentials).toHaveLength(1);
    const sent = JSON.parse(String(posted(fetchMock, "/auth/passkeys/add/")![1]!.body));
    expect(sent).toMatchObject({ name: "Phone", credential: { response: { transports: ["internal"] } } });
  });

  it("removes one", async () => {
    fakeDevice();
    const fetchMock = mockServer();
    renderWith(<PasskeysSection />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove passkey Work laptop" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/auth/passkeys/p1/remove/")).toBeTruthy());
  });

  it("tells a browser without passkeys to keep using the code", async () => {
    vi.stubGlobal("PublicKeyCredential", undefined);
    mockServer();
    renderWith(<PasskeysSection />);
    expect(await screen.findByText(/This browser cannot use passkeys/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add a passkey" })).toBeNull();
  });
});
