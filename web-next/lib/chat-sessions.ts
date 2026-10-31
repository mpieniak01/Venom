export type ChatSessionSummary = { id: string; title: string; updatedAt: string };
const KEY = "venom-chat-sessions";
export function readChatSessions(): ChatSessionSummary[] {
  try {
    const value: unknown = JSON.parse(globalThis.window?.localStorage.getItem(KEY) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is ChatSessionSummary => !!item && typeof item === "object" && typeof item.id === "string" && typeof item.title === "string" && typeof item.updatedAt === "string").slice(0, 100);
  } catch { return []; }
}
export function rememberChatSession(id: string, title?: string) {
  if (!id) return;
  try {
    const previous = readChatSessions();
    const existing = previous.find(item => item.id === id);
    const next = { id, title: title?.trim().slice(0, 80) || existing?.title || "", updatedAt: new Date().toISOString() };
    globalThis.window.localStorage.setItem(KEY, JSON.stringify([next, ...previous.filter(item => item.id !== id)].slice(0, 100)));
  } catch { /* history remains available from its session-owned store */ }
}
