import { takeInvitationTokenFromUrl } from "./invitationToken";

describe("takeInvitationTokenFromUrl", () => {
  it("reads the token from the fragment and removes it from the address bar", () => {
    window.history.replaceState(null, "", "/activate#token=abc%3A123");
    expect(takeInvitationTokenFromUrl()).toBe("abc:123");
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/activate");
  });

  it("returns null when there is no token", () => {
    window.history.replaceState(null, "", "/activate");
    expect(takeInvitationTokenFromUrl()).toBeNull();
  });
});
