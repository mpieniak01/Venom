import { isGuardedChatRuntime } from "./remote-chat";

export type VastChatTurn = { role: "user" | "assistant"; content: string };

export function vastChatHistoryKey(runtime: string | null | undefined, model: string, session: string | null, configHash?: string | null): string | null {
  return isGuardedChatRuntime(runtime) && model && session
    ? JSON.stringify([runtime, model, session, configHash ?? null]) : null;
}

export function appendVastChatTurn(previous: VastChatTurn[], prompt: string, answer: string): VastChatTurn[] {
  const result: VastChatTurn[] = [...previous, {role: "user", content: prompt}, {role: "assistant", content: answer}];
  while (result.length > 20 || result.reduce((size, turn) => size + turn.content.length, 0) > 50000) result.splice(0, 2);
  return result;
}
