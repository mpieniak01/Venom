// Operator choices use explicit model identities; moving aliases remain diagnostic.
export const SALUKI_GGUF = "hf.co/ConwayResearch/Underdog-Saluki-27B-1.0:Underdog-Saluki-27B-1.0-IQ2-mix.gguf";
const MOVING_OPERATOR_ALIASES = new Set(["gemma4:latest"]);
const DIAGNOSTIC_ALIASES = new Set(["gemma4:latest", "saluki:latest", "qwen3.5:latest"]);

type ChatModel = { name: string; provider?: string | null; runtime_id?: string; active?: boolean; selection_supported?: boolean; activation_supported?: boolean };

export function chatModelLabel(name: string, displayName?: string | null, provider?: string | null, unresolvedLabel = "unresolved variant"): string {
  if (provider && !["ollama", "vast_ollama"].includes(provider.toLowerCase())) return displayName || name;
  if (MOVING_OPERATOR_ALIASES.has(name.toLowerCase())) return name + " (" + unresolvedLabel + ")";
  if (displayName && displayName !== name && displayName !== name + " (unresolved variant)") return displayName;
  if (DIAGNOSTIC_ALIASES.has(name.toLowerCase())) return name + " (" + unresolvedLabel + ")";
  if (name === "gemma4:e4b") return "Gemma4 E4B IT";
  if (name === "gemma4:12b-it-q4_K_M") return "Gemma4 12B IT Q4_K_M";
  return name === SALUKI_GGUF ? "Underdog Saluki 27B 1.0 IQ2-mix GGUF" : name;
}

export function isSelectableChatModel(model: ChatModel): boolean {
  if (model.selection_supported === false || model.activation_supported === false) return false;
  const provider = (model.runtime_id || model.provider || "").toLowerCase();
  return !(["ollama", "vast_ollama"].includes(provider) && MOVING_OPERATOR_ALIASES.has(model.name.toLowerCase()));
}

export function preferChatModelAliases<T extends ChatModel>(models: readonly T[], selected?: string | null): T[];
export function preferChatModelAliases<T extends ChatModel>(models: readonly T[]): T[] {
  // Verified alias-to-source resolution belongs to the metadata catalog. The
  // frontend never hides a GGUF source just because a latest preset exists.
  return models.filter(isSelectableChatModel);
}
