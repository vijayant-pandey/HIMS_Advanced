/**
 * The browser side of passkeys (HIMS-IAM-014). The server sends WebAuthn options with binary values
 * as base64url text; the browser's API wants bytes, and its answer goes back as base64url text. No
 * library: these are the only conversions needed.
 */

type Json = Record<string, unknown>;

export function passkeysSupported(): boolean {
  return typeof window !== "undefined" && typeof window.PublicKeyCredential === "function" && !!navigator.credentials;
}

export function fromBase64url(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  const text = atob(base64);
  const bytes = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i);
  return bytes.buffer;
}

export function toBase64url(buffer: ArrayBuffer | ArrayBufferView): string {
  const bytes =
    buffer instanceof ArrayBuffer ? new Uint8Array(buffer) : new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  let text = "";
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function descriptors(list: unknown): PublicKeyCredentialDescriptor[] | undefined {
  if (!Array.isArray(list)) return undefined;
  return list.map((item: Json) => ({
    type: "public-key",
    id: fromBase64url(String(item.id)),
    transports: item.transports as AuthenticatorTransport[] | undefined,
  }));
}

function creationOptions(options: Json): PublicKeyCredentialCreationOptions {
  const user = options.user as Json;
  return {
    ...(options as unknown as PublicKeyCredentialCreationOptions),
    challenge: fromBase64url(String(options.challenge)),
    user: { ...(user as unknown as PublicKeyCredentialUserEntity), id: fromBase64url(String(user.id)) },
    excludeCredentials: descriptors(options.excludeCredentials),
  };
}

function requestOptions(options: Json): PublicKeyCredentialRequestOptions {
  return {
    ...(options as unknown as PublicKeyCredentialRequestOptions),
    challenge: fromBase64url(String(options.challenge)),
    allowCredentials: descriptors(options.allowCredentials),
  };
}

/** The device makes a new passkey for HIMS; returns its answer for /auth/passkeys/add/. */
export async function createPasskey(options: Json): Promise<Json> {
  const credential = (await navigator.credentials.create({ publicKey: creationOptions(options) })) as PublicKeyCredential | null;
  if (!credential) throw new Error("No passkey was made.");
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: toBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toBase64url(response.clientDataJSON),
      attestationObject: toBase64url(response.attestationObject),
      transports: typeof response.getTransports === "function" ? response.getTransports() : [],
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

/** The device signs the server's challenge with one of the person's passkeys. */
export async function answerWithPasskey(options: Json): Promise<Json> {
  const credential = (await navigator.credentials.get({ publicKey: requestOptions(options) })) as PublicKeyCredential | null;
  if (!credential) throw new Error("No passkey was used.");
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: toBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toBase64url(response.clientDataJSON),
      authenticatorData: toBase64url(response.authenticatorData),
      signature: toBase64url(response.signature),
      ...(response.userHandle ? { userHandle: toBase64url(response.userHandle) } : {}),
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

/** Words for when the person cancels or the device refuses (the browser's own message is technical). */
export function passkeyErrorText(error: unknown): string | null {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError") return "The passkey was cancelled or timed out. Try again.";
    if (error.name === "InvalidStateError") return "This device already has a passkey for your account here.";
    return "This device could not use a passkey. Use your code instead.";
  }
  return null;
}
