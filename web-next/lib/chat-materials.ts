import { apiFetch } from "./api-client";
export type ChatMaterial = { id: string; session_id: string; name: string; mime_type: string; size_bytes: number;
  kind: "document" | "image"; status: "ready"; created_at: string; preview_url: string };
export type MaterialCapabilities = { document: boolean; image: boolean; audio: boolean; video: boolean;
  max_bytes: number; max_document_chars: number; runtime_id: string | null; config_hash: string | null; model: string | null };
export function materialMime(file: Pick<File, "name" | "type">) {
  const extension = file.name.split(".").pop()?.toLowerCase();
  const known: Record<string, string> = { txt: "text/plain", md: "text/markdown", csv: "text/csv", json: "application/json", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" };
  return known[extension ?? ""] ?? file.type;
}
export function listChatMaterials(session: string, signal?: AbortSignal) {
  return apiFetch<{ materials: ChatMaterial[] }>("/api/v1/chat/materials?session_id=" + encodeURIComponent(session), { signal });
}
export function uploadChatMaterial(session: string, file: File, signal: AbortSignal) {
  return apiFetch<ChatMaterial>("/api/v1/chat/materials?session_id=" + encodeURIComponent(session) + "&name=" + encodeURIComponent(file.name), {
    method: "POST", headers: { "Content-Type": materialMime(file) }, body: file, signal,
  });
}
export function removeChatMaterial(session: string, id: string, signal?: AbortSignal) {
  return apiFetch<void>("/api/v1/chat/materials/" + encodeURIComponent(id) + "?session_id=" + encodeURIComponent(session), { method: "DELETE", signal });
}
export function readMaterialCapabilities(model: string, signal: AbortSignal) {
  return apiFetch<MaterialCapabilities>("/api/v1/chat/materials/capabilities?model=" + encodeURIComponent(model), { signal });
}
export function materialBlocked(items: ChatMaterial[], capabilities: MaterialCapabilities | null, direct: boolean) {
  if (!items.length) return false;
  if (!direct || !capabilities) return true;
  return items.some(item => item.kind === "image" ? !capabilities.image : !capabilities.document);
}
