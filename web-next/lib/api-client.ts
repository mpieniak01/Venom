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

const RETRYABLE_HTTP_STATUSES = new Set([500, 502, 503, 504]);
const RETRY_DELAYS_MS = [200, 500] as const;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const shouldRetryRequest = (method: string, status: number): boolean =>
  method === "GET" && RETRYABLE_HTTP_STATUSES.has(status);

const buildRequestHeaders = (headers?: HeadersInit): HeadersInit =>
  headers
    ? { "Content-Type": "application/json", ...headers }
    : { "Content-Type": "application/json" };

const shouldRetryNetworkError = (
  method: string,
  error: unknown,
  attempt: number,
  maxAttempts: number,
): boolean =>
  method === "GET" && error instanceof TypeError && attempt < maxAttempts - 1;

const createApiError = async (response: Response): Promise<ApiError> => {
  const text = await response.text();
  return new ApiError(
    `Request failed: ${response.status}`,
    response.status,
    safeParseJson(text),
  );
};

const parseApiResponse = async <T>(response: Response): Promise<T> => {
  if (response.status === 204) {
    return undefined as T;
  }
  const json = await response.json();
  return json as T;
};

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const { skipBaseUrl, headers, cache, ...rest } = options;
  const baseUrl = skipBaseUrl ? "" : getApiBaseUrl();
  const target = baseUrl ? `${baseUrl}${path}` : path;
  const requestHeaders = buildRequestHeaders(headers);
  const method = (rest.method ?? "GET").toUpperCase();
  let attempt = 0;
  const maxAttempts = RETRY_DELAYS_MS.length + 1;
  let lastError: unknown = null;

  while (attempt < maxAttempts) {
    try {
      const response = await fetch(target, {
        ...rest,
        cache: cache ?? "no-store",
        headers: requestHeaders,
      });

      if (!response.ok) {
        const apiError = await createApiError(response);
        if (shouldRetryRequest(method, response.status) && attempt < maxAttempts - 1) {
          await sleep(RETRY_DELAYS_MS[attempt] ?? 0);
          attempt += 1;
          continue;
        }
        throw apiError;
      }

      return await parseApiResponse<T>(response);
    } catch (error) {
      lastError = error;
      const retryableNetworkError = shouldRetryNetworkError(
        method,
        error,
        attempt,
        maxAttempts,
      );
      if (retryableNetworkError) {
        await sleep(RETRY_DELAYS_MS[attempt] ?? 0);
        attempt += 1;
        continue;
      }
      throw error;
    }
  }

  throw lastError instanceof Error ? lastError : new Error("API fetch failed");
}

const safeParseJson = (payload: string) => {
  try {
    return JSON.parse(payload);
  } catch {
    return payload;
  }
};
