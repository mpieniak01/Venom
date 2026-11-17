/** Remote paid requests require an immutable identity and must never be retried. */
export function isOpenRouterRuntime(runtime: string | null | undefined): boolean {
  return runtime === "openrouter" || runtime?.startsWith("openrouter@") === true;
}

export function isGuardedChatRuntime(runtime: string | null | undefined): boolean {
  return isOpenRouterRuntime(runtime) || runtime?.startsWith("ollama@vast:") === true || runtime?.startsWith("omni-native-peft-text:") === true;
}

export function allowsOpenRouterChat(runtime: string, direct: boolean): boolean {
  return !isOpenRouterRuntime(runtime) || direct;
}
