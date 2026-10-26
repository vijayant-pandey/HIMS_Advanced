/**
 * Activation links look like `/activate#token=...`. The fragment is never sent to any server
 * (spec 29.1), so we read it in the browser and then remove it from the address bar and
 * history.
 */
export function takeInvitationTokenFromUrl(): string | null {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const token = params.get("token");
  if (token) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }
  return token;
}
