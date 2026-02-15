export type SlashCommand = {
  id: string;
  command: string;
  label: string;
  detail: string;
  type: "provider" | "tool" | "action";
  value: string;
};

export const SLASH_COMMANDS: SlashCommand[] = [
  { id: "gem", command: "/gem", label: "Gemini", detail: "LLM API (Google)", type: "provider", value: "gem" },
  { id: "gpt", command: "/gpt", label: "GPT", detail: "LLM API (OpenAI)", type: "provider", value: "gpt" },
  { id: "clear", command: "/clear", label: "Nowa sesja", detail: "Wyczyść kontekst czatu", type: "action", value: "clear" },
  { id: "assistant", command: "/assistant", label: "Assistant", detail: "Operacje asystenta", type: "tool", value: "assistant" },
  { id: "browser", command: "/browser", label: "Browser", detail: "Akcje w przegladarce", type: "tool", value: "browser" },
  { id: "chrono", command: "/chrono", label: "Chrono", detail: "Czas i daty", type: "tool", value: "chrono" },
  { id: "complexity", command: "/complexity", label: "Complexity", detail: "Estymacje zlozonosci", type: "tool", value: "complexity" },
  { id: "compose", command: "/compose", label: "Compose", detail: "Skladanie/transformacje", type: "tool", value: "compose" },
  { id: "core", command: "/core", label: "Core", detail: "Operacje systemowe", type: "tool", value: "core" },
  { id: "docs", command: "/docs", label: "Docs", detail: "Dokumentacja/markdown", type: "tool", value: "docs" },
  { id: "file", command: "/file", label: "File", detail: "Operacje na plikach", type: "tool", value: "file" },
  { id: "git", command: "/git", label: "Git", detail: "Operacje git", type: "tool", value: "git" },
  { id: "github", command: "/github", label: "GitHub", detail: "GitHub API", type: "tool", value: "github" },
  { id: "gcal", command: "/gcal", label: "Calendar", detail: "Google Calendar", type: "tool", value: "gcal" },
  { id: "hf", command: "/hf", label: "HuggingFace", detail: "HuggingFace API", type: "tool", value: "hf" },
  { id: "input", command: "/input", label: "Input", detail: "Mysz/klawiatura", type: "tool", value: "input" },
  { id: "media", command: "/media", label: "Media", detail: "Media: obraz/audio", type: "tool", value: "media" },
  { id: "parallel", command: "/parallel", label: "Parallel", detail: "Rownolegla egzekucja", type: "tool", value: "parallel" },
  { id: "platform", command: "/platform", label: "Platform", detail: "Integracje platformowe", type: "tool", value: "platform" },
  { id: "render", command: "/render", label: "Render", detail: "Render tabel/markdown", type: "tool", value: "render" },
  { id: "research", command: "/research", label: "Research", detail: "Research i zrodla", type: "tool", value: "research" },
  { id: "shell", command: "/shell", label: "Shell", detail: "Polecenia shell", type: "tool", value: "shell" },
  { id: "test", command: "/test", label: "Test", detail: "Testy i raporty", type: "tool", value: "test" },
  { id: "web", command: "/web", label: "Web", detail: "Wyszukiwanie web", type: "tool", value: "web" },
];

export type ParsedSlashCommand = {
  cleaned: string;
  forcedTool?: string;
  forcedProvider?: string;
  sessionReset?: boolean;
};

export function parseSlashCommand(input: string): ParsedSlashCommand {
  const trimmed = input.trimStart();
  if (!trimmed.startsWith("/")) {
    return { cleaned: input };
  }
  const match = /^\/([a-zA-Z0-9_-]+)\b/.exec(trimmed);
  if (!match) return { cleaned: input };
  const token = match[1];
  const rest = trimmed.slice(match[0].length).trimStart();
  const command = SLASH_COMMANDS.find((entry) => entry.value === token);
  if (!command) {
    return { cleaned: input };
  }
  const base = {
    cleaned: rest,
    forcedTool: command.type === "tool" ? command.value : undefined,
    forcedProvider: command.type === "provider" ? command.value : undefined,
  };
  if (command.type === "action" && command.value === "clear") {
    return { ...base, sessionReset: true };
  }
  return base;
}

export function filterSlashSuggestions(input: string, limit = 3): SlashCommand[] {
  const trimmed = input.trimStart();
  if (!trimmed.startsWith("/")) return [];
  if (/^\/\S+\s+/.test(trimmed)) return [];
  const query = trimmed.slice(1).split(/\s+/)[0] || "";
  const lowered = query.toLowerCase();
  const matches = SLASH_COMMANDS.filter((entry) =>
    entry.value.startsWith(lowered),
  );
  return matches.slice(0, limit);
}
