import assert from "node:assert/strict";
import test from "node:test";

import {
  getPolicyBlockBadgeLabel,
  POLICY_REASON_CODES,
} from "@/lib/policy-utils";

test("getPolicyBlockBadgeLabel returns correct label for POLICY_UNSAFE_CONTENT", () => {
  const label = getPolicyBlockBadgeLabel(POLICY_REASON_CODES.POLICY_UNSAFE_CONTENT);
  assert.strictEqual(label, "Unsafe content");
});

test("getPolicyBlockBadgeLabel returns correct label for POLICY_TOOL_RESTRICTED", () => {
  const label = getPolicyBlockBadgeLabel(POLICY_REASON_CODES.POLICY_TOOL_RESTRICTED);
  assert.strictEqual(label, "Tool restricted");
});

test("getPolicyBlockBadgeLabel returns correct label for POLICY_PROVIDER_RESTRICTED", () => {
  const label = getPolicyBlockBadgeLabel(POLICY_REASON_CODES.POLICY_PROVIDER_RESTRICTED);
  assert.strictEqual(label, "Provider restricted");
});

test("getPolicyBlockBadgeLabel returns correct label for POLICY_MISSING_CONTEXT", () => {
  const label = getPolicyBlockBadgeLabel(POLICY_REASON_CODES.POLICY_MISSING_CONTEXT);
  assert.strictEqual(label, "Missing context");
});

test("getPolicyBlockBadgeLabel returns default label when reason code is null", () => {
  const label = getPolicyBlockBadgeLabel(null);
  assert.strictEqual(label, "Blocked by policy");
});

test("getPolicyBlockBadgeLabel returns fallback for unknown reason code", () => {
  const label = getPolicyBlockBadgeLabel("UNKNOWN_REASON");
  assert.strictEqual(label, "Policy block");
});
