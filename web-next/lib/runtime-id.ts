const MULTI_RUNTIME_ID = "multi_runtime";
const LEGACY_MULTI_RUNTIME_ID = "gemma4_audio";

export function normalizeRuntimeId(value: string | null | undefined): string {
  const candidate = (value || "").trim().toLowerCase();
  if (!candidate) return "";
  const atIndex = candidate.indexOf("@");
  const base = atIndex >= 0 ? candidate.slice(0, atIndex) : candidate;
  if (base === LEGACY_MULTI_RUNTIME_ID) {
    return atIndex >= 0 ? `${MULTI_RUNTIME_ID}${candidate.slice(atIndex)}` : MULTI_RUNTIME_ID;
  }
  return candidate;
}

export function canonicalRuntimeId(value: string | null | undefined): string {
  const normalized = normalizeRuntimeId(value);
  const atIndex = normalized.indexOf("@");
  if (atIndex < 0) return normalized;
  return normalized.slice(0, atIndex);
}

export function isMultiRuntime(value: string | null | undefined): boolean {
  const normalized = canonicalRuntimeId(value);
  return normalized === MULTI_RUNTIME_ID;
}
