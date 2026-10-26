// Operator chat prefers the installed Saluki preset; registry artifacts stay intact.
export const SALUKI_GGUF = "hf.co/ConwayResearch/Underdog-Saluki-27B-1.0:Underdog-Saluki-27B-1.0-IQ2-mix.gguf";
const SALUKI_ALIAS = "saluki:latest";

type ChatModel = { name: string; provider?: string | null; runtime_id?: string; active?: boolean };

export function chatModelLabel(name: string): string {
  return name === SALUKI_GGUF ? "saluki:IQ2-mix.gguf" : name;
}

export function preferChatModelAliases<T extends ChatModel>(models: readonly T[], selected?: string | null): T[] {
  const isOllama = (model: T) => (model.runtime_id || model.provider || "").toLowerCase() === "ollama";
  const alias = models.find((model) => isOllama(model) && model.name === SALUKI_ALIAS);
  const source = models.find((model) => isOllama(model) && model.name === SALUKI_GGUF);
  if (!alias || !source) return [...models];
  // Preserve the actual selected/active variant, including its vision projector.
  const keepSource = selected === SALUKI_GGUF || (selected !== SALUKI_ALIAS && source.active === true);
  const hidden = keepSource ? alias : source;
  return models.filter((model) => model !== hidden);
}
