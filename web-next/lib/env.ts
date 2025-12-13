const fallbackApi = "http://localhost:8000";

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
    return "ws://localhost:8000";
  }
};

export const API_BASE_URL = (getEnv("NEXT_PUBLIC_API_BASE") ||
  getEnv("API_PROXY_TARGET") ||
  fallbackApi).replace(/\/$/, "");

export const WS_BASE_URL = normalizeWs(getEnv("NEXT_PUBLIC_WS_BASE") || API_BASE_URL);
