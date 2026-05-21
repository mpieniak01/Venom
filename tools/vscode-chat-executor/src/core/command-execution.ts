import * as path from "node:path";

export const LEGACY_TOOL_NAME = "run_git_status";

export type ToolInput = Record<string, unknown>;

export type CommandExecutorDeps = {
  runGitCommand: (cwd: string, command: string) => Promise<string>;
  searchCode: (
    cwd: string,
    query: string,
    pathGlob?: string,
    maxResults?: number
  ) => Promise<string>;
  readFileContext: (
    filePath: string,
    line: number,
    contextLines: number,
    workspaceRoot?: string
  ) => Promise<string>;
  execSafe: (cwd: string, command: string) => Promise<string>;
};

export function isPathWithinRoot(root: string, target: string): boolean {
  const rel = path.relative(path.resolve(root), path.resolve(target));
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

export function resolveWorkspacePath(root: string, inputPath: string): string | undefined {
  const workspaceRoot = path.resolve(root);
  const resolved = path.resolve(workspaceRoot, inputPath);
  return isPathWithinRoot(workspaceRoot, resolved) ? resolved : undefined;
}

export function buildSystemPrompt(cwd: string, allowExec: boolean): string {
  const execNote = allowExec
    ? "Możesz uruchamiać komendy przez venom_exec_safe (pytest, make test-*, ruff, mypy)."
    : "Wykonanie komend shell jest wyłączone (venom.execution.allowExec=false).";
  return [
    `Jesteś asystentem programisty Venom dla projektu w workspace: ${cwd}.`,
    "Zawsze wywołuj narzędzia zamiast zgadywać o kodzie lub stanie repo.",
    "Dla pytań o kod: wywołaj venom_search_code.",
    "Dla pytań o status/diff/log git: wywołaj venom_git_status.",
    "Dla pytań o zawartość pliku: wywołaj venom_read_file.",
    execNote,
    "Odpowiadaj po polsku, chyba że użytkownik pisze po angielsku.",
    "Nie generuj listy komend jako finalnej odpowiedzi – wywołaj narzędzie i pokaż evidence.",
  ].join("\n");
}

export async function dispatchTool(
  name: string,
  input: ToolInput,
  cwd: string,
  deps: CommandExecutorDeps
): Promise<string> {
  switch (name) {
    case "venom_git_status":
    case LEGACY_TOOL_NAME: {
      const command = String(input.command ?? "git status --short --branch");
      const out = await deps.runGitCommand(cwd, command);
      return `REPO_ROOT=${cwd}\n${out}`;
    }
    case "venom_search_code": {
      const query = String(input.query ?? "");
      const glob = input.path_glob !== undefined ? String(input.path_glob) : undefined;
      const max = typeof input.max_results === "number" ? input.max_results : 10;
      return deps.searchCode(cwd, query, glob, max);
    }
    case "venom_read_file": {
      const file = String(input.file_path ?? "");
      const line = typeof input.line === "number" ? input.line : 1;
      const ctx = typeof input.context_lines === "number" ? input.context_lines : 5;
      const resolved = resolveWorkspacePath(cwd, file);
      if (!resolved) {
        return `Błąd odczytu pliku: ścieżka poza workspace (${file})`;
      }
      return deps.readFileContext(resolved, line, ctx, cwd);
    }
    case "venom_exec_safe": {
      const cmd = String(input.command ?? "");
      return deps.execSafe(cwd, cmd);
    }
    default:
      return `Nieznane narzędzie: ${name}`;
  }
}
