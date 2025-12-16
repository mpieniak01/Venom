export type LogEntryType = {
  id: string;
  ts: number;
  payload: unknown;
};

export type LogPayload = {
  message?: string;
  level?: string;
  type?: string;
  details?: unknown;
};

export function isLogPayload(value: unknown): value is LogPayload {
  return typeof value === "object" && value !== null;
}

export function formatLogPayload(payload: unknown) {
  if (typeof payload === "string") return payload;
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}
