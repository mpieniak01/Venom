/** Public, browser-only transport helpers for optional modules (ABI 1.x). */
export function createBrowserUuid(webCrypto: Crypto = globalThis.crypto): string {
  if (typeof webCrypto?.randomUUID === "function") {
    return webCrypto.randomUUID();
  }
  // getRandomValues is available on HTTP origins; randomUUID requires a secure context.
  const bytes = webCrypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export type MicrophoneCapability = "available" | "insecure_context" | "unavailable";

export function getMicrophoneCapability(
  browser: Pick<Window, "isSecureContext" | "navigator"> | undefined = globalThis.window,
): MicrophoneCapability {
  if (browser?.isSecureContext === false) return "insecure_context";
  return typeof browser?.navigator.mediaDevices?.getUserMedia === "function"
    ? "available"
    : "unavailable";
}
