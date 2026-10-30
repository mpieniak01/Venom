/** Display rounding only; retain the original quote for budgets and orders. */
export function formatVastUsd(value: string | null | undefined, unknown: string): string {
  if (value == null || value.trim() === "") return unknown;
  const amount = Number(value);
  return Number.isFinite(amount) && amount >= 0 ? amount.toFixed(4) : unknown;
}
