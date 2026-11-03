// Operator chat prefers the installed Saluki preset; registry artifacts stay intact.
export const SALUKI_GGUF = "hf.co/ConwayResearch/Underdog-Saluki-27B-1.0:Underdog-Saluki-27B-1.0-IQ2-mix.gguf";
const SALUKI_ALIAS = "saluki:latest";

type ChatModel = { name: string; provider?: string | null; runtime_id?: string; active?: boolean; selection_supported?: boolean; activation_supported?: boolean };

export function chatModelLabel(name: string, displayName?: string | null, provider?: string | null, unresolvedLabel = "unresolved variant"): string {
  if (provider && !["ollama", "vast_ollama"].includes(provider.toLowerCase())) return displayName || name;
  if (name.toLowerCase() === "gemma4:latest") return name + " (" + unresolvedLabel + ")";
  if (displayName && displayName !== name) return displayName;
  if (name === "gemma4:e4b") return "Gemma4 E4B IT Q4_K_M";
  if (name === "gemma4:12b-it-q4_K_M") return "Gemma4 12B IT Q4_K_M";
  return name === SALUKI_GGUF ? "saluki:IQ2-mix.gguf" : name;
}

export function isSelectableChatModel(model: ChatModel): boolean {
  if (model.selection_supported === false || model.activation_supported === false) return false;
  const provider = (model.runtime_id || model.provider || "").toLowerCase();
  return !(["ollama", "vast_ollama"].includes(provider) && model.name.toLowerCase() === "gemma4:latest");
}

export function preferChatModelAliases<T extends ChatModel>(models: readonly T[], selected?: string | null): T[] {
  const selectable = models.filter(isSelectableChatModel);
  const isOllama = (model: T) => (model.runtime_id || model.provider || "").toLowerCase() === "ollama";
  const alias = selectable.find((model) => isOllama(model) && model.name === SALUKI_ALIAS);
  const source = selectable.find((model) => isOllama(model) && model.name === SALUKI_GGUF);
  if (!alias || !source) return selectable;
  // Preserve the actual selected/active variant, including its vision projector.
  const keepSource = selected === SALUKI_GGUF || (selected !== SALUKI_ALIAS && source.active === true);
  const hidden = keepSource ? alias : source;
  return selectable.filter((model) => model !== hidden);
}
