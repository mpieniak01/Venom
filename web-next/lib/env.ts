import { applyHttpPolicyToUrl, buildHttpBaseUrl, isLocalOrPrivateHost } from "@/lib/url-policy";

const DEFAULT_API_PORT = 8000;

const getEnv = (key: string): string | undefined => {
  if (typeof process === "undefined") return undefined;
  return process.env[key];
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

const normalizeWs = (url: string): string => {
  try {
    const parsed = new URL(url);
    parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
    return sanitizeBase(parsed.toString());
  } catch {
    const fallback = buildHttpBaseUrl("127.0.0.1", DEFAULT_API_PORT);
    return sanitizeBase(fallback.replace(/^http/, "ws"));
  }
};

const getEnvApiBase = (): string =>
  getEnv("NEXT_PUBLIC_API_BASE") ||
  getEnv("API_PROXY_TARGET") ||
  getEnv("NEXT_PUBLIC_API_URL") ||
  "";

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
  const origin = browserWindow.location.origin;
  try {
    const parsed = new URL(origin);
    if (isLocalOrPrivateHost(parsed.hostname) && parsed.port && Number(parsed.port) !== DEFAULT_API_PORT) {
      parsed.port = String(DEFAULT_API_PORT);
      return normalizeWs(parsed.toString());
    }
  } catch {
    return sanitizeBase(origin.replace(/^http/, "ws"));
  }
  return sanitizeBase(origin.replace(/^http/, "ws"));
};

export const getServerApiBaseUrl = (): string => {
  const envApiBase = getEnvApiBase();
  const explicit = envApiBase ? sanitizeBase(applyHttpPolicyToUrl(envApiBase)) : "";
  if (explicit) return explicit;
  return buildHttpBaseUrl("127.0.0.1", DEFAULT_API_PORT);
};

export const getApiBaseUrl = (): string => {
  const resolved = resolveBrowserBase();
  if (resolved) return sanitizeBase(resolved);
  const fallback = resolveDefaultLocalApiBase();
  return sanitizeBase(fallback);
};

export const getWsBaseUrl = (): string => {
  const explicit = getEnv("NEXT_PUBLIC_WS_BASE");
  if (explicit) return normalizeWs(explicit);
  const httpBase = getApiBaseUrl();
  if (!httpBase) {
    return resolveBrowserWsBase();
  }
  return normalizeWs(httpBase);
};
