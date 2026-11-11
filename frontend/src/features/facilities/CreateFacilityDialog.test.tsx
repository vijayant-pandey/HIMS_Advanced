import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { CreateFacilityDialog } from "./CreateFacilityDialog";

/** A new branch starts in the hospital's own country and time zone (found by HIMS-QA-003). */

function renderFor(country: "IN" | "US") {
  const user: CurrentUser = {
    id: "u1",
    email: "admin@synthetic.test",
    display_name: "Synthetic Admin",
    staff_member_id: null,
    grants: [{ permission: "facilities.manage", facility_id: null, department_id: null }],
    organization: { display_name: "Synthetic Health", country },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10, passkeys: 0 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <CreateFacilityDialog open onClose={() => {}} />
    </QueryClientProvider>,
  );
  return within(screen.getByRole("dialog"));
}

describe("New facility", () => {
  it("starts in the United States and Eastern time for a US hospital", () => {
    const dialog = renderFor("US");
    expect(dialog.getByRole("combobox", { name: "Country" })).toHaveTextContent("United States");
    expect(dialog.getByRole("textbox", { name: "Time zone (IANA)" })).toHaveValue("America/New_York");
  });

  it("starts in India for an Indian hospital", () => {
    const dialog = renderFor("IN");
    expect(dialog.getByRole("combobox", { name: "Country" })).toHaveTextContent("India");
    expect(dialog.getByRole("textbox", { name: "Time zone (IANA)" })).toHaveValue("Asia/Kolkata");
  });
});
