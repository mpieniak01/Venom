const DEFAULT_API_PORT = 8000;

const getEnv = (key: string): string | undefined => {
  if (typeof process === "undefined") return undefined;
  return process.env[key];
};

const normalizeWs = (url: string): string => {
  try {
    const parsed = new URL(url);
    parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return `ws://127.0.0.1:${DEFAULT_API_PORT}`;
  }
};

const envApiBase =
  getEnv("NEXT_PUBLIC_API_BASE") || getEnv("API_PROXY_TARGET") || "";

const sanitizeBase = (value: string): string => value.replace(/\/$/, "");

const isLocalhost = (hostname: string): boolean =>
  hostname === "localhost" ||
  hostname === "127.0.0.1" ||
  hostname === "[::1]" ||
  hostname === "wsl.localhost" ||
  hostname.endsWith(".localhost");

const resolveBrowserBase = (): string => {
  if (!envApiBase) return "";
  if (typeof window === "undefined") return sanitizeBase(envApiBase);
  if (!envApiBase.startsWith("http")) return sanitizeBase(envApiBase);

  try {
    const parsed = new URL(envApiBase);
    if (isLocalhost(parsed.hostname) && !isLocalhost(window.location.hostname)) {
      return "";
    }
  } catch {
    return sanitizeBase(envApiBase);
  }

  return sanitizeBase(envApiBase);
};

const resolveBrowserWsBase = (): string => {
  if (typeof window === "undefined") {
    return `ws://127.0.0.1:${DEFAULT_API_PORT}`;
  }
  const origin = window.location.origin;
  try {
    const parsed = new URL(origin);
    if (
      isLocalhost(parsed.hostname) &&
      parsed.port &&
      Number(parsed.port) !== DEFAULT_API_PORT
    ) {
      parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
      parsed.port = String(DEFAULT_API_PORT);
      return sanitizeBase(parsed.toString());
    }
  } catch {
    return sanitizeBase(origin.replace(/^http/, "ws"));
  }
  return sanitizeBase(origin.replace(/^http/, "ws"));
};

export const getApiBaseUrl = (): string => sanitizeBase(resolveBrowserBase());

export const getWsBaseUrl = (): string => {
  const explicit = getEnv("NEXT_PUBLIC_WS_BASE");
  if (explicit) return normalizeWs(explicit);
  const httpBase = getApiBaseUrl();
  if (!httpBase) {
    return resolveBrowserWsBase();
  }
  return normalizeWs(httpBase);
};
