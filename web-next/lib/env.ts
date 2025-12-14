const DEFAULT_API_PORT = 8000;
const LOCAL_FALLBACK = `http://127.0.0.1:${DEFAULT_API_PORT}`;

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

const resolveBrowserBase = (): string => {
  if (envApiBase) return sanitizeBase(envApiBase);
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "https:" : "http:";
    const host = window.location.hostname;
    // Przy HTTPS unikamy odwołań do http://*, aby nie blokować danych (mixed content).
    if (protocol === "https:") {
      return "";
    }
    return `${protocol}//${host}:${DEFAULT_API_PORT}`;
  }
  return LOCAL_FALLBACK;
};

const resolveBrowserWsBase = (): string => {
  if (typeof window === "undefined") {
    return `ws://127.0.0.1:${DEFAULT_API_PORT}`;
  }
  const origin = window.location.origin.replace(/^http/, "ws");
  return `${origin}/ws`;
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
