import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { HomePage } from "./HomePage";

function renderHome(user: CurrentUser) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/staff" element={<p>Staff page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const baseUser: CurrentUser = {
  id: "u1",
  email: "new@synthetic.test",
  display_name: "New Person",
  staff_member_id: null,
  grants: [],
  mfa: { enabled: false, required: false, verified: false, recovery_codes_remaining: 0 },
};

describe("HomePage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the no-access page with the audit reference for users without roles", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ reference: "ref-1234-abcd" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    renderHome(baseUser);

    expect(screen.getByText(/don't have access to any area/)).toBeInTheDocument();
    expect(await screen.findByText("ref-1234-abcd")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/v1/auth/no-access-report/");
  });

  it("sends users with access to the first page they may open", () => {
    renderHome({
      ...baseUser,
      grants: [{ permission: "staff.view", facility_id: null, department_id: null }],
    });
    expect(screen.getByText("Staff page")).toBeInTheDocument();
  });
});
