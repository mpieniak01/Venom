const PROD_ENVS = new Set(["production", "prod", "staging", "stage"]);
const VALID_POLICIES = new Set(["auto", "force_http", "force_https"]);

const normalize = (value: string | undefined, fallback: string): string => {
  const trimmed = (value || "").trim().toLowerCase();
  return trimmed || fallback;
};

const isPrivateIpv4 = (host: string): boolean => {
  const rawParts = host.split(".");
  if (rawParts.length !== 4) {
    return false;
  }
  if (!rawParts.every((part) => /^\d{1,3}$/.test(part))) {
    return false;
  }
  const parts = rawParts.map((part) => Number.parseInt(part, 10));
  if (parts.some((part) => part < 0 || part > 255)) {
    return false;
  }
  if (parts[0] === 10) return true;
  if (parts[0] === 127) return true;
  if (parts[0] === 192 && parts[1] === 168) return true;
  if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return true;
  return false;
};

export const isLocalOrPrivateHost = (host: string): boolean => {
  const hostname = host.trim().toLowerCase();
  if (!hostname) return false;
  if (hostname === "localhost" || hostname === "0.0.0.0" || hostname === "[::1]") {
    return true;
  }
  if (hostname.endsWith(".localhost") || hostname.endsWith(".local")) {
    return true;
  }
  return isPrivateIpv4(hostname);
};

export const getUrlSchemePolicy = (): "auto" | "force_http" | "force_https" => {
  const value = normalize(
    process.env.NEXT_PUBLIC_URL_SCHEME_POLICY || process.env.URL_SCHEME_POLICY,
    "auto"
  );
  if (VALID_POLICIES.has(value)) {
    return value as "auto" | "force_http" | "force_https";
  }
  return "auto";
};

export const getRuntimeEnv = (): string => {
  return normalize(process.env.NEXT_PUBLIC_ENV || process.env.NODE_ENV, "development");
};

export const resolveHttpScheme = (hostname: string): "http" | "https" => {
  const policy = getUrlSchemePolicy();
  if (policy === "force_http") return "http";
  if (policy === "force_https") return "https";
  if (isLocalOrPrivateHost(hostname)) return "http";
  return PROD_ENVS.has(getRuntimeEnv()) ? "https" : "http";
};

export const buildHttpBaseUrl = (hostname: string, port?: number): string => {
  const scheme = resolveHttpScheme(hostname);
  return port ? `${scheme}://${hostname}:${port}` : `${scheme}://${hostname}`;
};

export const applyHttpPolicyToUrl = (value: string): string => {
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return value;
    }
    parsed.protocol = `${resolveHttpScheme(parsed.hostname)}:`;
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return value;
  }
};
