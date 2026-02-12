import assert from "node:assert/strict";
import test from "node:test";

import {
  getPolicyBlockMessage,
  getPolicyBlockBadgeLabel,
  POLICY_REASON_CODES,
} from "@/lib/policy-utils";

test("getPolicyBlockMessage returns correct message for POLICY_UNSAFE_CONTENT", () => {
  const message = getPolicyBlockMessage(POLICY_REASON_CODES.POLICY_UNSAFE_CONTENT);
  assert.match(message, /unsafe or inappropriate/i);
  assert.ok(message.includes("🚫"));
});

test("getPolicyBlockMessage returns correct message for POLICY_TOOL_RESTRICTED", () => {
  const message = getPolicyBlockMessage(POLICY_REASON_CODES.POLICY_TOOL_RESTRICTED);
  assert.match(message, /tool is restricted/i);
  assert.ok(message.includes("🚫"));
});

test("getPolicyBlockMessage returns correct message for POLICY_PROVIDER_RESTRICTED", () => {
  const message = getPolicyBlockMessage(POLICY_REASON_CODES.POLICY_PROVIDER_RESTRICTED);
  assert.match(message, /provider is restricted/i);
  assert.ok(message.includes("🚫"));
});

test("getPolicyBlockMessage returns correct message for POLICY_MISSING_CONTEXT", () => {
  const message = getPolicyBlockMessage(POLICY_REASON_CODES.POLICY_MISSING_CONTEXT);
  assert.match(message, /missing/i);
  assert.ok(message.includes("🚫"));
});

test("getPolicyBlockMessage returns default message when reason code is null", () => {
  const message = getPolicyBlockMessage(null);
  assert.strictEqual(message, "Request blocked by policy gate");
});

test("getPolicyBlockMessage returns custom default message when provided", () => {
  const customDefault = "Custom blocked message";
  const message = getPolicyBlockMessage(null, customDefault);
  assert.strictEqual(message, customDefault);
});

test("getPolicyBlockMessage returns fallback for unknown reason code", () => {
  const message = getPolicyBlockMessage("UNKNOWN_REASON");
  assert.ok(message.includes("🚫"));
  assert.ok(message.includes("UNKNOWN_REASON"));
});

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
