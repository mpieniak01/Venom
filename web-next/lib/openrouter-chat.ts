export type OpenRouterCost = {
  state: "pending" | "settled";
  currency: "USD";
  estimated_usd: string | null;
  reserved_usd: string | null;
  reported_usd: string | null;
};

export const pendingOpenRouterCost = (): OpenRouterCost => ({
  state: "pending", currency: "USD", estimated_usd: null, reserved_usd: null, reported_usd: null,
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
  return {currency: "USD", state: item.state === "settled" && reported !== null ? "settled" : "pending",
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
