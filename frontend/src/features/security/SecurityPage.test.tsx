import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { ThemeSelectionProvider } from "../../app/ThemeSelection";
import { currentUserKey } from "../auth/api";
import { LoginPage } from "../auth/LoginPage";
import { RequireAuth } from "../auth/RequireAuth";
import { SecurityPage } from "./SecurityPage";

vi.mock("qrcode", () => ({ default: { toDataURL: () => Promise.resolve("data:image/png;base64,QR") } }));

const admin: CurrentUser = {
  id: "u1",
  email: "admin@synthetic.test",
  display_name: "Admin",
  staff_member_id: null,
  grants: [{ permission: "platform.admin_console", facility_id: null, department_id: null }],
  mfa: { enabled: false, required: true, verified: false, recovery_codes_remaining: 0 },
};

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderAt(path: string, user: CurrentUser | null, routes: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  return render(
    <ThemeSelectionProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>{routes}</Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeSelectionProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("two-factor sign-in (HIMS-IAM-005)", () => {
  it("sends a privileged user without two-factor to the Security page", () => {
    renderAt(
      "/facilities",
      admin,
      <Route element={<RequireAuth />}>
        <Route path="/facilities" element={<p>Facilities</p>} />
        <Route path="/security" element={<p>Security page</p>} />
      </Route>,
    );
    expect(screen.getByText("Security page")).toBeInTheDocument();
  });

  it("sets up two-factor: key, first code, then backup codes", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json(201, { secret: "ABCDEFGHIJKLMNOP", otpauth_uri: "otpauth://totp/x" }))
      .mockResolvedValueOnce(json(200, { recovery_codes: ["aaaaa-bbbbb", "ccccc-ddddd"] }))
      .mockResolvedValue(json(200, { ...admin, mfa: { ...admin.mfa, enabled: true, verified: true } }));
    renderAt("/security", admin, <Route path="/security" element={<SecurityPage />} />);

    expect(screen.getByText("Required for your role")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Set up two-factor sign-in" }));
    expect(await screen.findByTestId("manual-key")).toHaveTextContent("ABCD EFGH IJKL MNOP");
    expect(await screen.findByAltText(/QR code/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("6-digit code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Turn on" }));
    expect(await screen.findByTestId("recovery-codes")).toHaveTextContent("aaaaa-bbbbb");
    expect(fetchMock.mock.calls[1]![0]).toBe("/api/v1/auth/mfa/confirm/");
  });

  it("asks for the code after the password when two-factor is on", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).endsWith("/auth/csrf/")
        ? new Response(null, { status: 204 })
        : json(202, { mfa_required: true, detail: "Enter the 6-digit code" }),
    );
    renderAt("/login", null, <Route path="/login" element={<LoginPage />} />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@synthetic.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Two-factor sign-in")).toBeInTheDocument();
    expect(screen.getByLabelText("Authentication code")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Use a backup code/ }));
    expect(screen.getByLabelText("Backup code")).toBeInTheDocument();
  });
});
