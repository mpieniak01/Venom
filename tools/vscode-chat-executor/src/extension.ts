import * as vscode from 'vscode';
import { execFile, spawn } from 'node:child_process';
import * as fs from 'node:fs/promises';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const MAX_ITERATIONS = 5;
const LEGACY_TOOL_NAME = 'run_git_status'; // backward-compat alias

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
  'git branch --show-current',
  'git rev-parse --short HEAD',
  'git log --oneline -5',
  'git log --oneline -10',
  'git log --oneline -20',
  'git show --stat HEAD',
  'git stash list',
]);

async function runGitCommand(cwd: string, command: string): Promise<string> {
  const normalized = command.trim().replace(/\s+/g, ' ');
  if (!GIT_ALLOWLIST.has(normalized)) {
    throw new Error(`Komenda git poza allowlista: "${normalized}"`);
  }
  const [bin, ...args] = normalized.split(' ');
  const { stdout, stderr } = await execFileAsync(bin, args, { cwd });
  return [stdout, stderr?.trim()].filter(Boolean).join('\n').trim();
}

// ---------------------------------------------------------------------------
// Code search – rg wrapper
// ---------------------------------------------------------------------------

const SKIP_DIRS = ['.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', 'out', 'dist', 'models_cache', 'models'];

async function searchCode(cwd: string, query: string, pathGlob?: string, maxResults = 10): Promise<string> {
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
    const lines: string[] = [];
    const proc = spawn('rg', args, { cwd });
    proc.stdout.setEncoding('utf8');
    proc.stdout.on('data', (d: string) => lines.push(...d.split('\n')));
    proc.on('close', () => {
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
      resolve(results.length > 0 ? results.join('\n') : 'Brak wyników.');
    });
    proc.on('error', () => resolve('Błąd: ripgrep nie znaleziony. Zainstaluj: sudo apt install ripgrep'));
    setTimeout(() => { proc.kill(); resolve('Timeout wyszukiwania (10s).'); }, 10_000);
  });
}

// ---------------------------------------------------------------------------
// File read z kontekstem
// ---------------------------------------------------------------------------

async function readFileContext(filePath: string, line: number, contextLines: number): Promise<string> {
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
  /^pytest(\s+.*)?$/,
  /^python -m pytest(\s+.*)?$/,
  /^make test-[\w-]+$/,
  /^npm test$/,
  /^ruff check(\s+.*)?$/,
  /^mypy(\s+.*)?$/,
];

async function execSafe(cwd: string, command: string): Promise<string> {
  const allowExec = getConfig<boolean>('allowExec', false);
  if (!allowExec) {
    return 'Wykonanie komend zablokowane. Włącz w ustawieniach: venom.execution.allowExec = true';
  }
  const norm = command.trim();
  const allowed = EXEC_SAFE_PATTERNS.some(p => p.test(norm));
  if (!allowed) {
    return `Komenda nie jest na liście dozwolonych: "${norm}". Dozwolone: pytest, make test-*, ruff check, mypy.`;
  }
  try {
    const { stdout, stderr } = await execFileAsync('bash', ['-c', norm], { cwd, timeout: 30_000 });
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

async function dispatchTool(
  name: string,
  input: Record<string, unknown>,
  cwd: string
): Promise<string> {
  switch (name) {
    case 'venom_git_status':
    case LEGACY_TOOL_NAME: {
      const command = String(input.command ?? 'git status --short --branch');
      const out = await runGitCommand(cwd, command);
      return `REPO_ROOT=${cwd}\n${out}`;
    }
    case 'venom_search_code': {
      const query = String(input.query ?? '');
      const glob = input.path_glob !== undefined ? String(input.path_glob) : undefined;
      const max = typeof input.max_results === 'number' ? input.max_results : 10;
      return searchCode(cwd, query, glob, max);
    }
    case 'venom_read_file': {
      const file = String(input.file_path ?? '');
      const line = typeof input.line === 'number' ? input.line : 1;
      const ctx = typeof input.context_lines === 'number' ? input.context_lines : 5;
      const resolved = file.startsWith('/') ? file : `${cwd}/${file}`;
      return readFileContext(resolved, line, ctx);
    }
    case 'venom_exec_safe': {
      const cmd = String(input.command ?? '');
      return execSafe(cwd, cmd);
    }
    default:
      return `Nieznane narzędzie: ${name}`;
  }
}

// ---------------------------------------------------------------------------
// System prompt
// ---------------------------------------------------------------------------

function buildSystemPrompt(cwd: string): string {
  const allowExec = getConfig<boolean>('allowExec', false);
  const execNote = allowExec
    ? 'Możesz uruchamiać komendy przez venom_exec_safe (pytest, make test-*, ruff, mypy).'
    : 'Wykonanie komend shell jest wyłączone (venom.execution.allowExec=false).';
  return [
    `Jesteś asystentem programisty Venom dla projektu w workspace: ${cwd}.`,
    'Zawsze wywołuj narzędzia zamiast zgadywać o kodzie lub stanie repo.',
    'Dla pytań o kod: wywołaj venom_search_code.',
    'Dla pytań o status/diff/log git: wywołaj venom_git_status.',
    'Dla pytań o zawartość pliku: wywołaj venom_read_file.',
    execNote,
    'Odpowiadaj po polsku, chyba że użytkownik pisze po angielsku.',
    'Nie generuj listy komend jako finalnej odpowiedzi – wywołaj narzędzie i pokaż evidence.',
  ].join('\n');
}

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
  const messages: vscode.LanguageModelChatMessage[] = [
    vscode.LanguageModelChatMessage.User(buildSystemPrompt(cwd)),
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
    let hasToolCall = false;

    for await (const chunk of response.stream) {
      if (token.isCancellationRequested) break;
      if (chunk instanceof vscode.LanguageModelTextPart) {
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
          toolOutput = await dispatchTool(chunk.name, chunk.input as Record<string, unknown>, cwd);
        }
        toolCalls.push({ part: chunk, result: toolOutput });
      }
    }

    if (!hasToolCall) {
      // Brak tool callów = finalna odpowiedź, koniec pętli
      break;
    }

    // Dodaj odpowiedź asystenta (z tool callami) + wyniki do historii
    messages.push(
      vscode.LanguageModelChatMessage.Assistant(
        toolCalls.map(tc => new vscode.LanguageModelToolCallPart(tc.part.callId, tc.part.name, tc.part.input))
      )
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
        const file = options.input.file_path.startsWith('/')
          ? options.input.file_path
          : `${root}/${options.input.file_path}`;
        const result = await readFileContext(file, options.input.line, options.input.context_lines ?? 5);
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
