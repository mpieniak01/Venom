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
 * Maps reason codes to user-friendly messages
 */
export function getPolicyBlockMessage(
  reasonCode?: string | null,
  defaultMessage?: string
): string {
  if (!reasonCode) {
    return defaultMessage || "Request blocked by policy gate";
  }

  const messages: Record<string, string> = {
    POLICY_UNSAFE_CONTENT:
      "🚫 Request blocked: Content may contain unsafe or inappropriate material",
    POLICY_TOOL_RESTRICTED:
      "🚫 Request blocked: The requested tool is restricted by policy",
    POLICY_PROVIDER_RESTRICTED:
      "🚫 Request blocked: The requested provider is restricted by policy",
    POLICY_MISSING_CONTEXT:
      "🚫 Request blocked: Required context is missing for this request",
  };

  return messages[reasonCode] || `🚫 Request blocked: ${reasonCode}`;
}

/**
 * Returns a short badge label for policy block status
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
