import { apiFetch } from "./api-client";

export const NATIVE_TEXT_RUNTIME = "omni-native-peft-text";
export type NativeTextIdentity = {
  runtime: string; runtime_id: string; adapter_id: string; weights_sha256: string;
  config_sha256: string; snapshot_sha256: string; input_messages_sha256?: string;
};
export type NativeTextAdapter = { adapter_id: string; label: string; weights_sha256: string };
export type NativeTextState = { selection: NativeTextIdentity | null; previous: NativeTextIdentity | null; persistent: false };
const prefix = "/api/v1/llm/native-text";
const digest = /^[a-f0-9]{64}$/;
export function isNativeTextRuntime(value?: string | null) { return value?.startsWith(NATIVE_TEXT_RUNTIME + ":") === true; }
export function readNativeTextIdentity(value: unknown): NativeTextIdentity {
  if (!value || typeof value !== "object") throw new Error("omni_native_text_selection_changed");
  const item = value as NativeTextIdentity;
  if (item.runtime !== NATIVE_TEXT_RUNTIME || typeof item.adapter_id !== "string"
    || !digest.test(item.weights_sha256) || !digest.test(item.config_sha256) || !digest.test(item.snapshot_sha256)
    || item.runtime_id !== NATIVE_TEXT_RUNTIME + ":" + item.adapter_id + ":" + item.weights_sha256) {
    throw new Error("omni_native_text_selection_changed");
  }
  return item;
}
function readState(value: NativeTextState): NativeTextState {
  return { selection: value.selection ? readNativeTextIdentity(value.selection) : null,
    previous: value.previous ? readNativeTextIdentity(value.previous) : null, persistent: false };
}
export async function fetchNativeTextState() { return readState(await apiFetch<NativeTextState>(prefix + "/state")); }
export async function fetchNativeTextCatalog() {
  return (await apiFetch<{adapters: NativeTextAdapter[]}>(prefix + "/catalog")).adapters;
}
export async function selectNativeText(adapter: string, current: NativeTextIdentity | null) {
  return readState(await apiFetch<NativeTextState>(prefix + "/selection", { method: "PUT",
    body: JSON.stringify({adapter_id: adapter, expected_runtime_id: current?.runtime_id ?? null}) }));
}
export async function rollbackNativeText(current: NativeTextIdentity) {
  return readState(await apiFetch<NativeTextState>(prefix + "/rollback", { method: "POST",
    body: JSON.stringify({expected_runtime_id: current.runtime_id}) }));
}
export function nativeTextQuality(item: NativeTextAdapter) {
  return item.adapter_id === "omni-p13-145" && item.weights_sha256 === "9f6863cda26a452e89085ea28628a57cd7f10742d9a0337ade100fd0eb58c493"
    ? "chat2.nativeText.reference" : "chat2.nativeText.unqualified";
}
export function nativeTextServer(selection: NativeTextIdentity) {
  return {active_server: NATIVE_TEXT_RUNTIME, active_model: selection.adapter_id,
    runtime_id: selection.runtime_id, config_hash: selection.config_sha256};
}
