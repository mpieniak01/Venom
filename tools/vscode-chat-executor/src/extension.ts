import * as vscode from 'vscode';
import { execFile, spawn } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { promisify } from 'node:util';
import {
  LEGACY_TOOL_NAME,
  buildSystemPrompt,
  dispatchTool,
  isPathWithinRoot,
  resolveWorkspacePath,
} from './core/command-execution';

const execFileAsync = promisify(execFile);
const MAX_ITERATIONS = 5;
const DEFAULT_SEARCH_TIMEOUT_MS = 10_000;

// ---------------------------------------------------------------------------
// Konfiguracja i workspace root
// ---------------------------------------------------------------------------

function getConfig<T>(key: string, fallback: T): T {
  return vscode.workspace.getConfiguration('venom.execution').get<T>(key) ?? fallback;
}

async function resolveRepoRoot(): Promise<string | undefined> {
  const configured = getConfig<string>('repoRoot', '').trim();
  if (configured) return configured;
  const candidate = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!candidate) return undefined;
  try {
    const { stdout } = await execFileAsync('git', ['rev-parse', '--show-toplevel'], { cwd: candidate });
    return stdout.trim() || candidate;
  } catch {
    return candidate;
  }
}

// ---------------------------------------------------------------------------
// Git – rozszerzona allowlista
// ---------------------------------------------------------------------------

const GIT_ALLOWLIST = new Set([
  'git status --short --branch',
  'git status',
  'git diff --shortstat',
  'git diff --stat',
  'git diff HEAD --name-only',
  'git ls-files',
  'git ls-tree HEAD',
  'git ls-tree --name-only HEAD',
  'git branch --show-current',
  'git rev-parse --show-toplevel',
  'git rev-parse --short HEAD',
  'git log --oneline -5',
  'git log --oneline -10',
  'git log --oneline -20',
  'git show --stat HEAD',
  'git stash list',
]);

function tokenizeCommandArgs(command: string): string[] {
  const tokens: string[] = [];
  const matcher = /"([^"\\]*(?:\\.[^"\\]*)*)"|'([^'\\]*(?:\\.[^'\\]*)*)'|([^\s]+)/g;
  let match: RegExpExecArray | null;
  while ((match = matcher.exec(command)) !== null) {
    const value = match[1] ?? match[2] ?? match[3] ?? '';
    const normalized = value.replace(/\\(["'\\])/g, '$1');
    if (normalized) {
      tokens.push(normalized);
    }
  }
  return tokens;
}

async function runGitCommand(cwd: string, command: string): Promise<string> {
  const rawCommand = command.trim();
  const allowlistKey = rawCommand.replace(/\s+/g, ' ');
  if (!allowlistKey.startsWith('git ')) {
    throw new Error(`Dozwolone są tylko komendy git: "${allowlistKey}"`);
  }
  if (!GIT_ALLOWLIST.has(allowlistKey)) {
    const decision = await vscode.window.showWarningMessage(
      `Komenda poza allowlistą: "${allowlistKey}". Uruchomić mimo to?`,
      { modal: true },
      'Uruchom mimo to',
      'Anuluj',
    );
    if (decision !== 'Uruchom mimo to') {
      throw new Error(`Anulowano komendę poza allowlistą: "${allowlistKey}"`);
    }
  }
  const [bin, ...args] = tokenizeCommandArgs(rawCommand);
  if (!bin) {
    throw new Error('Komenda git nie może być pusta.');
  }
  const { stdout, stderr } = await execFileAsync(bin, args, { cwd });
  return [stdout, stderr?.trim()].filter(Boolean).join('\n').trim();
}

// ---------------------------------------------------------------------------
// Code search – rg wrapper
// ---------------------------------------------------------------------------

const SKIP_DIRS = ['.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', 'out', 'dist', 'models_cache', 'models'];

async function searchCode(cwd: string, query: string, pathGlob?: string, maxResults = 10): Promise<string> {
  const searchTimeoutMs = Math.max(1_000, getConfig<number>('searchTimeoutMs', DEFAULT_SEARCH_TIMEOUT_MS));
  const skipArgs = SKIP_DIRS.flatMap(d => ['--glob', `!${d}`, '--glob', `!**/${d}/**`]);
  const args = [
    '--json',
    '--ignore-case',
    `--max-count=${maxResults}`,
    '--context=2',
    ...skipArgs,
  ];
  if (pathGlob) args.push('--glob', pathGlob);
  args.push(query, cwd);

  return new Promise<string>((resolve) => {
    let settled = false;
    let buffer = '';
    const lines: string[] = [];
    const proc = spawn('rg', args, { cwd });
    const finish = (msg: string) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(msg);
    };
    const flushBuffer = () => {
      const tail = buffer.trim();
      if (tail) lines.push(tail);
      buffer = '';
    };
    proc.stdout.setEncoding('utf8');
    proc.stdout.on('data', (d: string) => {
      buffer += d;
      const chunks = buffer.split('\n');
      buffer = chunks.pop() ?? '';
      for (const line of chunks) lines.push(line);
    });
    proc.on('close', () => {
      flushBuffer();
      const results: string[] = [];
      let count = 0;
      for (const line of lines) {
        const l = line.trim();
        if (!l) continue;
        try {
          const entry = JSON.parse(l) as { type: string; data: { path: { text: string }; line_number: number; lines: { text: string } } };
          if (entry.type === 'match') {
            const { path: { text: file }, line_number: ln, lines: { text } } = entry.data;
            results.push(`[${file}:${ln}] ${text.trimEnd()}`);
            count++;
            if (count >= maxResults) break;
          }
        } catch { /* skip malformed */ }
      }
      finish(results.length > 0 ? results.join('\n') : 'Brak wyników.');
    });
    proc.on('error', () => finish('Błąd: ripgrep nie znaleziony. Zainstaluj: sudo apt install ripgrep'));
    const timer = setTimeout(() => {
      proc.kill();
      finish(`Timeout wyszukiwania (${searchTimeoutMs}ms).`);
    }, searchTimeoutMs);
  });
}

// ---------------------------------------------------------------------------
// File read z kontekstem
// ---------------------------------------------------------------------------

async function readFileContext(filePath: string, line: number, contextLines: number, workspaceRoot?: string): Promise<string> {
  if (workspaceRoot && !isPathWithinRoot(workspaceRoot, filePath)) {
    return `Błąd odczytu pliku: ścieżka poza workspace (${filePath})`;
  }
  try {
    const content = await fs.readFile(filePath, 'utf8');
    const all = content.split('\n');
    const start = Math.max(0, line - contextLines - 1);
    const end = Math.min(all.length, line + contextLines);
    return all
      .slice(start, end)
      .map((text, i) => {
        const ln = start + i + 1;
        const marker = ln === line ? '→' : ' ';
        return `${marker} ${String(ln).padStart(4)}: ${text}`;
      })
      .join('\n');
  } catch (e) {
    return `Błąd odczytu pliku: ${e instanceof Error ? e.message : String(e)}`;
  }
}

// ---------------------------------------------------------------------------
// Safe shell exec (opt-in przez konfigurację)
// ---------------------------------------------------------------------------

const EXEC_SAFE_PATTERNS = [
  /^pytest$/,
  /^python$/,
  /^make$/,
  /^npm$/,
  /^ruff$/,
  /^mypy$/,
];

async function execSafe(cwd: string, command: string): Promise<string> {
  const allowExec = getConfig<boolean>('allowExec', false);
  if (!allowExec) {
    return 'Wykonanie komend zablokowane. Włącz w ustawieniach: venom.execution.allowExec = true';
  }
  const norm = command.trim().replace(/\s+/g, ' ');
  if (!norm) {
    return 'Komenda nie może być pusta.';
  }
  if (/[;&|><`$\\\n\r]/.test(norm)) {
    return `Komenda zawiera niedozwolone metaznaki shella: "${norm}".`;
  }

  const parts = norm.split(' ').filter(Boolean);
  const [bin, ...args] = parts;
  const allowedBin = EXEC_SAFE_PATTERNS.some(p => p.test(bin));
  const allowed =
    allowedBin && (
      bin === 'pytest' ||
      bin === 'mypy' ||
      (bin === 'python' && args.length >= 2 && args[0] === '-m' && args[1] === 'pytest') ||
      (bin === 'make' && args.length === 1 && /^test-[\w-]+$/.test(args[0])) ||
      (bin === 'npm' && args.length === 1 && args[0] === 'test') ||
      (bin === 'ruff' && args.length >= 1 && args[0] === 'check')
    );
  if (!allowed) {
    return `Komenda nie jest na liście dozwolonych: "${norm}". Dozwolone: pytest, make test-*, ruff check, mypy.`;
  }
  try {
    const { stdout, stderr } = await execFileAsync(bin, args, { cwd, timeout: 30_000 });
    return [stdout, stderr?.trim()].filter(Boolean).join('\n').trim() || '(brak outputu)';
  } catch (e) {
    return `Błąd: ${e instanceof Error ? e.message : String(e)}`;
  }
}

// ---------------------------------------------------------------------------
// Tool result helper
// ---------------------------------------------------------------------------

function toolResultToText(result: vscode.LanguageModelToolResult): string {
  return result.content
    .map(part => (part instanceof vscode.LanguageModelTextPart ? part.value : typeof part === 'string' ? part : ''))
    .filter(Boolean)
    .join('\n')
    .trim();
}

// ---------------------------------------------------------------------------
// Dispatch narzędzi
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Agentic loop handler
// ---------------------------------------------------------------------------

async function venomAgentHandler(
  request: vscode.ChatRequest,
  _ctx: vscode.ChatContext,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken
): Promise<void> {
  const cwd = await resolveRepoRoot();
  if (!cwd) {
    stream.markdown('Brak otwartego workspace. Otwórz folder repo i spróbuj ponownie.');
    return;
  }

  const maxIter = getConfig<number>('maxIterations', MAX_ITERATIONS);
  const allowExec = getConfig<boolean>('allowExec', false);
  const messages: vscode.LanguageModelChatMessage[] = [
    vscode.LanguageModelChatMessage.User(buildSystemPrompt(cwd, allowExec)),
    vscode.LanguageModelChatMessage.User(request.prompt),
  ];

  // Narzędzia rejestrowane przez extension (filtr po prefikcie venom_)
  const tools = vscode.lm.tools.filter(
    t => t.name.startsWith('venom_') || t.name === LEGACY_TOOL_NAME
  );

  let iterations = 0;

  while (iterations < maxIter) {
    if (token.isCancellationRequested) break;
    iterations++;

    let response: vscode.LanguageModelChatResponse;
    try {
      response = await request.model.sendRequest(messages, { tools }, token);
    } catch (e) {
      stream.markdown(`Błąd komunikacji z modelem: ${e instanceof Error ? e.message : String(e)}`);
      return;
    }

    const toolCalls: Array<{ part: vscode.LanguageModelToolCallPart; result: string }> = [];
    const assistantTextParts: string[] = [];
    let hasToolCall = false;

    for await (const chunk of response.stream) {
      if (token.isCancellationRequested) break;
      if (chunk instanceof vscode.LanguageModelTextPart) {
        assistantTextParts.push(chunk.value);
        stream.markdown(chunk.value);
      } else if (chunk instanceof vscode.LanguageModelToolCallPart) {
        hasToolCall = true;
        stream.progress(`Venom: wywołuję ${chunk.name}…`);
        let toolOutput: string;
        try {
          // Próba przez lm.invokeTool (dla zarejestrowanych narzędzi)
          const invoked = await vscode.lm.invokeTool(
            chunk.name,
            { input: chunk.input as Record<string, unknown>, toolInvocationToken: request.toolInvocationToken }
          );
          toolOutput = toolResultToText(invoked);
        } catch {
          // Fallback: bezpośredni dispatch
          toolOutput = await dispatchTool(chunk.name, chunk.input as Record<string, unknown>, cwd, {
            runGitCommand,
            searchCode,
            readFileContext,
            execSafe,
          });
        }
        toolCalls.push({ part: chunk, result: toolOutput });
      }
    }

    if (!hasToolCall) {
      // Brak tool callów = finalna odpowiedź, koniec pętli
      break;
    }

    // Dodaj odpowiedź asystenta (z tool callami) + wyniki do historii
    const assistantParts: Array<vscode.LanguageModelTextPart | vscode.LanguageModelToolCallPart> = [];
    const assistantText = assistantTextParts.join('');
    if (assistantText.trim()) {
      assistantParts.push(new vscode.LanguageModelTextPart(assistantText));
    }
    assistantParts.push(
      ...toolCalls.map(tc => new vscode.LanguageModelToolCallPart(tc.part.callId, tc.part.name, tc.part.input))
    );
    messages.push(
      vscode.LanguageModelChatMessage.Assistant(assistantParts)
    );
    messages.push(
      vscode.LanguageModelChatMessage.User(
        toolCalls.map(tc => new vscode.LanguageModelToolResultPart(tc.part.callId, [new vscode.LanguageModelTextPart(tc.result)]))
      )
    );
  }

  if (iterations >= maxIter) {
    stream.markdown(`\n\n⚠️ Przekroczono limit iteracji (${maxIter}). Ostatnia odpowiedź może być niekompletna.`);
  }
}

// ---------------------------------------------------------------------------
// Rejestracja narzędzi i participanta
// ---------------------------------------------------------------------------

export function activate(context: vscode.ExtensionContext) {

  // --- Narzędzie: venom_git_status ---
  context.subscriptions.push(
    vscode.lm.registerTool<{ command: string }>('venom_git_status', {
      async invoke(options) {
        const root = await resolveRepoRoot();
        if (!root) return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart('Brak workspace.')]);
        const command = options.input.command ?? 'git status --short --branch';
        try {
          const out = await runGitCommand(root, command);
          return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(`REPO_ROOT=${root}\n${out}`)]);
        } catch (e) {
          return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(`Błąd: ${e instanceof Error ? e.message : String(e)}`)]);
        }
      },
      prepareInvocation(options) {
        const cmd = String(options.input.command ?? '').trim();
        return {
          invocationMessage: `Venom git: ${cmd}`,
          confirmationMessages: { title: 'Venom Git Tool', message: `Uruchomić: ${cmd}?` }
        };
      }
    })
  );

  // --- Narzędzie: run_git_status (backward-compat alias) ---
  context.subscriptions.push(
    vscode.lm.registerTool<{ command: string }>(LEGACY_TOOL_NAME, {
      async invoke(options) {
        const root = await resolveRepoRoot();
        if (!root) return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart('Brak workspace.')]);
        const command = options.input.command ?? 'git status --short --branch';
        try {
          const out = await runGitCommand(root, command);
          return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(`REPO_ROOT=${root}\n${out}`)]);
        } catch (e) {
          return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(`Błąd: ${e instanceof Error ? e.message : String(e)}`)]);
        }
      },
      prepareInvocation(options) {
        const cmd = String(options.input.command ?? '').trim();
        return { invocationMessage: `Venom wykonuje lokalnie: ${cmd}` };
      }
    })
  );

  // --- Narzędzie: venom_search_code ---
  context.subscriptions.push(
    vscode.lm.registerTool<{ query: string; path_glob?: string; max_results?: number }>('venom_search_code', {
      async invoke(options) {
        const root = await resolveRepoRoot();
        if (!root) return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart('Brak workspace.')]);
        const result = await searchCode(root, options.input.query, options.input.path_glob, options.input.max_results ?? 10);
        return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(result)]);
      },
      prepareInvocation(options) {
        return { invocationMessage: `Venom przeszukuje kod: "${options.input.query}"` };
      }
    })
  );

  // --- Narzędzie: venom_read_file ---
  context.subscriptions.push(
    vscode.lm.registerTool<{ file_path: string; line: number; context_lines?: number }>('venom_read_file', {
      async invoke(options) {
        const root = await resolveRepoRoot();
        if (!root) return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart('Brak workspace.')]);
        const file = resolveWorkspacePath(root, options.input.file_path);
        if (!file) {
          return new vscode.LanguageModelToolResult([
            new vscode.LanguageModelTextPart(`Błąd odczytu pliku: ścieżka poza workspace (${options.input.file_path})`)
          ]);
        }
        const result = await readFileContext(file, options.input.line, options.input.context_lines ?? 5, root);
        return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(result)]);
      },
      prepareInvocation(options) {
        return { invocationMessage: `Venom czyta plik: ${options.input.file_path}:${options.input.line}` };
      }
    })
  );

  // --- Narzędzie: venom_exec_safe ---
  context.subscriptions.push(
    vscode.lm.registerTool<{ command: string }>('venom_exec_safe', {
      async invoke(options) {
        const root = await resolveRepoRoot();
        if (!root) return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart('Brak workspace.')]);
        const result = await execSafe(root, options.input.command);
        return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(result)]);
      },
      prepareInvocation(options) {
        return {
          invocationMessage: `Venom exec: ${options.input.command}`,
          confirmationMessages: {
            title: 'Venom Safe Exec',
            message: `Uruchomić komendę: ${options.input.command}?`
          }
        };
      }
    })
  );

  // --- Participant: @venom-agent (jeden, z agentic loop) ---
  const participant = vscode.chat.createChatParticipant('venom.agent', venomAgentHandler);
  participant.iconPath = new vscode.ThemeIcon('robot');
  context.subscriptions.push(participant);

  // --- Komenda: Venom Run Git Status (backward-compat) ---
  context.subscriptions.push(
    vscode.commands.registerCommand('venom.execution.runGitStatus', async () => {
      const root = await resolveRepoRoot();
      if (!root) { vscode.window.showErrorMessage('Brak otwartego workspace.'); return; }
      try {
        const out = await runGitCommand(root, 'git status --short --branch');
        await vscode.env.clipboard.writeText(out);
        vscode.window.showInformationMessage('Git status skopiowany do schowka.');
      } catch (e) {
        vscode.window.showErrorMessage(`Błąd: ${e instanceof Error ? e.message : String(e)}`);
      }
    })
  );
}

export function deactivate() { /* no-op */ }
