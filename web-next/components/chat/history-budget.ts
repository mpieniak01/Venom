export type ChatHistoryTurn = { role: "user" | "assistant"; content: string; material_ids?: string[] };
/** Keep recent complete turns within the API budget; the visible transcript remains intact. */
export function boundChatHistory(history: ChatHistoryTurn[], currentLength = 0): ChatHistoryTurn[] {
  const pairs: ChatHistoryTurn[][] = [];
  let user: ChatHistoryTurn | null = null;
  for (const turn of history) {
    if (!turn.content) continue;
    if (turn.role === "user") user = turn;
    else if (user) { pairs.push([user, turn]); user = null; }
  }
  let chars = 0; const selected: ChatHistoryTurn[][] = [];
  const budget = Math.max(0, 50000 - currentLength);
  for (let index = pairs.length - 1; index >= 0 && selected.length < 10; index--) {
    const pair = pairs[index]; const size = pair.reduce((total, turn) => total + turn.content.length, 0);
    if (chars + size > budget) break;
    chars += size; selected.unshift(pair.map(turn => ({ ...turn, ...(turn.material_ids ? { material_ids: [...turn.material_ids] } : {}) })));
  }
  return selected.flat();
}
