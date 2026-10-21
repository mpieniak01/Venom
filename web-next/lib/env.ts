import { applyHttpPolicyToUrl, buildHttpBaseUrl, isLocalOrPrivateHost } from "@/lib/url-policy";

const DEFAULT_API_PORT = 8800;

const getEnv = (key: string): string | undefined => {
  if (typeof process === "undefined") return undefined;
  // Next only exposes public variables referenced by their literal name.
  // Dynamic process.env[key] lookups are empty in the browser bundle.
  const publicValues: Record<string, string | undefined> = {
    NEXT_PUBLIC_TRANSPORT_PROFILE: process.env.NEXT_PUBLIC_TRANSPORT_PROFILE,
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE,
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_API_LOCALHOST_FALLBACK: process.env.NEXT_PUBLIC_API_LOCALHOST_FALLBACK,
    NEXT_PUBLIC_WS_BASE: process.env.NEXT_PUBLIC_WS_BASE,
    NEXT_PUBLIC_AUDIO_WS_BASE: process.env.NEXT_PUBLIC_AUDIO_WS_BASE,
    NEXT_PUBLIC_GEMMA4_API_BASE: process.env.NEXT_PUBLIC_GEMMA4_API_BASE,
  };
  return publicValues[key] ?? process.env[key];
};

const getBrowserWindow = (): Window | undefined => {
  if (globalThis.window === undefined) return undefined;
  return globalThis.window;
};

const isTruthy = (value: string | undefined): boolean => {
  const normalized = (value ?? "").trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
};

const isLocalhostFallbackEnabled = (): boolean =>
  isTruthy(getEnv("NEXT_PUBLIC_API_LOCALHOST_FALLBACK")) ||
  isTruthy(getEnv("API_LOCALHOST_FALLBACK"));

const sanitizeBase = (value: string): string => value.replace(/\/$/, "");

const toWsProtocol = (protocol: string): "wss:" | "ws:" =>
  protocol === "https:" || protocol === "wss:" ? "wss:" : "ws:";

const coerceUrlWithScheme = (value: string): string => {
  if (/^[a-z][a-z\d+.-]*:\/\//i.test(value)) {
    return value;
  }
  return `http://${value}`;
};

const normalizeWs = (url: string): string => {
  try {
    const parsed = new URL(coerceUrlWithScheme(url));
    parsed.protocol = toWsProtocol(parsed.protocol);
    return sanitizeBase(parsed.toString());
  } catch {
    const fallback = buildHttpBaseUrl("127.0.0.1", DEFAULT_API_PORT);
    return sanitizeBase(fallback.replace(/^https/, "wss").replace(/^http/, "ws"));
  }
};

const getEnvApiBase = (): string =>
  getEnv("NEXT_PUBLIC_API_BASE") ||
  getEnv("API_PROXY_TARGET") ||
  getEnv("NEXT_PUBLIC_API_URL") ||
  "";

const isTrustedLanBrowser = (): boolean =>
  Boolean(getBrowserWindow()) && getEnv("NEXT_PUBLIC_TRANSPORT_PROFILE") === "trusted_lan";

const resolveBrowserBase = (): string => {
  const envApiBase = getEnvApiBase();
  if (!envApiBase) return "";
  const browserWindow = getBrowserWindow();
  if (!browserWindow) return sanitizeBase(applyHttpPolicyToUrl(envApiBase));
  if (!envApiBase.startsWith("http")) return sanitizeBase(envApiBase);

  try {
    const parsed = new URL(envApiBase);
    if (
      isLocalOrPrivateHost(parsed.hostname) &&
      !isLocalOrPrivateHost(browserWindow.location.hostname)
    ) {
      return "";
    }
  } catch {
    return sanitizeBase(envApiBase);
  }

  return sanitizeBase(applyHttpPolicyToUrl(envApiBase));
};

const resolveDefaultLocalApiBase = (): string => {
  if (!isLocalhostFallbackEnabled()) return "";
  const browserWindow = getBrowserWindow();
  if (!browserWindow) return "";
  const hostname = browserWindow.location.hostname;
  if (isLocalOrPrivateHost(hostname)) {
    return buildHttpBaseUrl("127.0.0.1", DEFAULT_API_PORT);
  }
  return "";
};

const resolveBrowserWsBase = (): string => {
  const browserWindow = getBrowserWindow();
  if (!browserWindow) {
    return normalizeWs(buildHttpBaseUrl("127.0.0.1", DEFAULT_API_PORT));
  }
  return normalizeWs(browserWindow.location.origin);
};

export const getServerApiBaseUrl = (): string => {
  const envApiBase = getEnvApiBase();
  const explicit = envApiBase ? sanitizeBase(applyHttpPolicyToUrl(envApiBase)) : "";
  if (explicit) return explicit;
  return buildHttpBaseUrl("127.0.0.1", DEFAULT_API_PORT);
};

export const getApiBaseUrl = (): string => {
  if (isTrustedLanBrowser()) return "";
  const resolved = resolveBrowserBase();
  if (resolved) return sanitizeBase(resolved);
  const fallback = resolveDefaultLocalApiBase();
  return sanitizeBase(fallback);
};

export const getWsBaseUrl = (): string => {
  if (isTrustedLanBrowser()) return resolveBrowserWsBase();
  const explicit = getEnv("NEXT_PUBLIC_WS_BASE");
  if (explicit) return normalizeWs(explicit);
  const httpBase = getApiBaseUrl();
  if (!httpBase) {
    return resolveBrowserWsBase();
  }
  return normalizeWs(httpBase);
};

const buildWsEndpoint = (base: string, pathname: string): string => {
  try {
    const url = new URL(pathname, normalizeWs(base));
    url.protocol = toWsProtocol(url.protocol);
    return sanitizeBase(url.toString());
  } catch {
    const fallback = normalizeWs(base);
    return sanitizeBase(fallback.replace(/^https:/, "wss:").replace(/^http:/, "ws:"))
      .replace(/\/$/, "") + pathname;
  }
};

export const getAudioWsUrl = (): string => {
  const explicit = isTrustedLanBrowser() ? "" : getEnv("NEXT_PUBLIC_AUDIO_WS_BASE");
  return buildWsEndpoint(explicit || getWsBaseUrl(), "/ws/audio");
};

const DEFAULT_GEMMA4_PORT = 8014;

export const getGemma4ApiBaseUrl = (): string => {
  const explicit = getEnv("NEXT_PUBLIC_GEMMA4_API_BASE");
  if (explicit) return sanitizeBase(explicit);
  const httpBase = getApiBaseUrl();
  if (httpBase) {
    try {
      const url = new URL(httpBase.startsWith("http") ? httpBase : `http://${httpBase}`);
      url.port = String(DEFAULT_GEMMA4_PORT);
      return sanitizeBase(url.toString());
    } catch { /* fall through */ }
  }
  return buildHttpBaseUrl("127.0.0.1", DEFAULT_GEMMA4_PORT);
};
