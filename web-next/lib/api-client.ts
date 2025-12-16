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
): Promise<T> {
  const { skipBaseUrl, headers, cache, ...rest } = options;
  const target = skipBaseUrl ? path : `${getApiBaseUrl()}${path}`;

  const response = await fetch(target, {
    ...rest,
    cache: cache ?? "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(headers || {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(
      `Request failed: ${response.status}`,
      response.status,
      safeParseJson(text),
    );
  }

  if (response.status === 204) {
    return undefined as T;
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
