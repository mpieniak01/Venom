/**
 * Moduł: policy-utils - Utilities for policy gate UI
 */

export const POLICY_REASON_CODES = {
  POLICY_UNSAFE_CONTENT: "POLICY_UNSAFE_CONTENT",
  POLICY_TOOL_RESTRICTED: "POLICY_TOOL_RESTRICTED",
  POLICY_PROVIDER_RESTRICTED: "POLICY_PROVIDER_RESTRICTED",
  POLICY_MISSING_CONTEXT: "POLICY_MISSING_CONTEXT",
} as const;

export type PolicyReasonCode =
  (typeof POLICY_REASON_CODES)[keyof typeof POLICY_REASON_CODES];

/**
 * Returns a short badge label for policy block status
 * NOTE: Currently returns English labels. Could be enhanced with i18n in future.
 */
export function getPolicyBlockBadgeLabel(reasonCode?: string | null): string {
  if (!reasonCode) {
    return "Blocked by policy";
  }

  const labels: Record<string, string> = {
    POLICY_UNSAFE_CONTENT: "Unsafe content",
    POLICY_TOOL_RESTRICTED: "Tool restricted",
    POLICY_PROVIDER_RESTRICTED: "Provider restricted",
    POLICY_MISSING_CONTEXT: "Missing context",
  };

  return labels[reasonCode] || "Policy block";
}
