export type OpenRouterCost = {
  state: "pending" | "settled";
  currency: "USD";
  estimated_usd: string | null;
  reserved_usd: string | null;
  reported_usd: string | null;
  conversation_reported_usd: string | null;
  conversation_reserved_usd: string | null;
  conversation_state: "pending" | "settled" | "unknown";
};

export const pendingOpenRouterCost = (): OpenRouterCost => ({
  state: "pending", currency: "USD", estimated_usd: null, reserved_usd: null, reported_usd: null,
  conversation_reported_usd: null, conversation_reserved_usd: null, conversation_state: "unknown",
});

/** Keep monetary values exact and distinguish missing accounting from free usage. */
export function moneyText(value: unknown): string | null {
  return typeof value === "string" && value.length <= 128
    && /^(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value) ? value : null;
}

export function readOpenRouterCost(value: unknown): OpenRouterCost | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const item = value as Record<string, unknown>;
  if (item.currency !== "USD" || !["pending", "settled"].includes(String(item.state))) return null;
  const reported = moneyText(item.reported_usd);
  const conversationReported = moneyText(item.conversation_reported_usd);
  let conversationState: OpenRouterCost["conversation_state"] = "unknown";
  if (item.conversation_state === "pending") conversationState = "pending";
  if (item.conversation_state === "settled" && conversationReported !== null) conversationState = "settled";
  return {conversation_reported_usd: conversationReported,
    conversation_reserved_usd: moneyText(item.conversation_reserved_usd), conversation_state: conversationState,
    currency: "USD", state: item.state === "settled" && reported !== null ? "settled" : "pending",
    estimated_usd: moneyText(item.estimated_usd), reserved_usd: moneyText(item.reserved_usd), reported_usd: reported};
}

export type OpenRouterModel = {
  id: string; name: string; input_price_per_million: string | null;
  output_price_per_million: string | null; request_price: string | null;
  context_length: number; max_output_tokens: number; pricing_as_of: string;
};
export type OpenRouterStatus = {
  enabled: boolean; configured: boolean; library_available: boolean; available: boolean;
  authenticated: boolean | null; reason: string | null; pricing_as_of: string | null;
};
export type OpenRouterCatalog = {models: OpenRouterModel[]; pricing_as_of: string | null};

export type OpenRouterQuote = {
  estimated_usd: string; currency: "USD"; max_output_tokens: number;
  input_token_upper_bound: number; context_length: number; config_hash: string; quote_hash: string;
};

export function readOpenRouterQuote(value: unknown, expectedConfigHash: string | null | undefined): OpenRouterQuote {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid_quote");
  const item = value as Record<string, unknown>;
  const counts = [item.max_output_tokens, item.input_token_upper_bound, item.context_length];
  if (moneyText(item.estimated_usd) === null || item.currency !== "USD"
    || !expectedConfigHash || item.config_hash !== expectedConfigHash
    || typeof item.quote_hash !== "string" || !/^[a-f0-9]{64}$/.test(item.quote_hash)
    || counts.some(count => typeof count !== "number" || !Number.isSafeInteger(count) || count <= 0)) {
    throw new Error("invalid_quote");
  }
  return item as OpenRouterQuote;
}

export type OpenRouterMetadata = {
  requested_model: string | null; confirmed_model: string | null;
  confirmed_provider: string | null; generation_id: string | null;
};
export type OpenRouterUsage = Partial<Record<"prompt_tokens" | "completion_tokens" | "total_tokens", number>>;

/** Persist only bounded identity fields, never a raw provider response. */
export function readOpenRouterMetadata(value: unknown): OpenRouterMetadata {
  const item = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const safe = (field: string) => {
    const content = item[field];
    return typeof content === "string" && content.length <= 256
      && !/sk-or-v1-|sk-proj-|bearer\s+/i.test(content) ? content : null;
  };
  return {requested_model: safe("requested_model"), confirmed_model: safe("confirmed_model"),
    confirmed_provider: safe("confirmed_provider"), generation_id: safe("generation_id")};
}

export function readOpenRouterUsage(value: unknown, source: unknown): OpenRouterUsage | null {
  if (source !== "upstream" || !value || typeof value !== "object" || Array.isArray(value)) return null;
  const item = value as Record<string, unknown>;
  const usage: OpenRouterUsage = {};
  for (const key of ["prompt_tokens", "completion_tokens", "total_tokens"] as const) {
    const count = item[key];
    if (typeof count === "number" && Number.isSafeInteger(count) && count >= 0) usage[key] = count;
  }
  return Object.keys(usage).length ? usage : null;
}
