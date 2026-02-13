import { getApiBaseUrl } from "./env";

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

type ApiOptions = RequestInit & { skipBaseUrl?: boolean };

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiOptions = {},
): Promise<T | undefined> {
  const { skipBaseUrl, headers, cache, ...rest } = options;
  const baseUrl = skipBaseUrl ? "" : getApiBaseUrl();
  const target = baseUrl ? `${baseUrl}${path}` : path;

  let response: Response;
  try {
    response = await fetch(target, {
      ...rest,
      cache: cache ?? "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(headers || {}),
      },
    });
  } catch (error) {
    if (!skipBaseUrl && baseUrl && isLocalBase(baseUrl)) {
      response = await fetch(path, {
        ...rest,
        cache: cache ?? "no-store",
        headers: {
          "Content-Type": "application/json",
          ...(headers || {}),
        },
      });
    } else {
      throw error;
    }
  }

  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(
      `Request failed: ${response.status}`,
      response.status,
      safeParseJson(text),
    );
  }

  if (response.status === 204) {
    return undefined;
  }

  const json = await response.json();
  return json as T;
}

const safeParseJson = (payload: string) => {
  try {
    return JSON.parse(payload);
  } catch {
    return payload;
  }
};

const isLocalBase = (value: string) => {
  try {
    const parsed = new URL(value);
    const hostname = parsed.hostname;
    return (
      hostname === "localhost" ||
      hostname === "127.0.0.1" ||
      hostname === "[::1]" ||
      hostname === "wsl.localhost" ||
      hostname.endsWith(".localhost")
    );
  } catch {
    return false;
  }
};
