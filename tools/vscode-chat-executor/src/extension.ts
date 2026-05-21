import * as vscode from 'vscode';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const TOOL_NAME = 'run_git_status';
const ALLOWED_COMMANDS = new Set([
  'git status --short --branch',
  'git status',
  'git diff --shortstat',
  'git branch --show-current',
  'git rev-parse --short HEAD'
]);

interface RunCommandInput {
  command: string;
}

function configuredRepoRoot(): string | undefined {
  const cfg = vscode.workspace.getConfiguration('venom.execution');
  const value = cfg.get<string>('repoRoot');
  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }
  return undefined;
}

async function resolveRepoRoot(): Promise<string | undefined> {
  const configured = configuredRepoRoot();
  if (configured) {
    return configured;
  }
  const candidate = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!candidate) {
    return undefined;
  }
  try {
    const { stdout } = await execFileAsync('git', ['rev-parse', '--show-toplevel'], { cwd: candidate });
    const root = stdout.trim();
    return root || candidate;
  } catch {
    return candidate;
  }
}

async function runGitStatus(cwd: string): Promise<string> {
  const { stdout, stderr } = await execFileAsync('git', ['status', '--short', '--branch'], { cwd });
  if (stderr?.trim()) {
    return `${stdout}\n${stderr}`.trim();
  }
  return stdout.trim();
}

async function runAllowlistedCommand(cwd: string, command: string): Promise<string> {
  const normalized = command.trim().replace(/\s+/g, ' ');
  if (!ALLOWED_COMMANDS.has(normalized)) {
    throw new Error(`Komenda poza allowlista: ${normalized}`);
  }
  const [bin, ...args] = normalized.split(' ');
  const { stdout, stderr } = await execFileAsync(bin, args, { cwd });
  if (stderr?.trim()) {
    return `${stdout}\n${stderr}`.trim();
  }
  return stdout.trim();
}

function isGitStatusIntent(prompt: string): boolean {
  const p = prompt.toLowerCase();
  return (
    p.includes('git status') ||
    p.includes('status git') ||
    p.includes('stan gita') ||
    p.includes('sprawdz stan git')
  );
}

function toolResultToText(result: vscode.LanguageModelToolResult): string {
  return result.content
    .map((part) => {
      if (part instanceof vscode.LanguageModelTextPart) {
        return part.value;
      }
      if (typeof part === 'string') {
        return part;
      }
      return '';
    })
    .filter(Boolean)
    .join('\n')
    .trim();
}

export function activate(context: vscode.ExtensionContext) {
  const toolDisposable = vscode.lm.registerTool<RunCommandInput>(TOOL_NAME, {
    async invoke(options) {
      const root = await resolveRepoRoot();
      if (!root) {
        return new vscode.LanguageModelToolResult([
          new vscode.LanguageModelTextPart('Brak otwartego workspace.')
        ]);
      }
      const command = options.input.command ?? '';
      try {
        const output = await runAllowlistedCommand(root, command);
        return new vscode.LanguageModelToolResult([
          new vscode.LanguageModelTextPart(`REPO_ROOT=${root}\n${output}`)
        ]);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return new vscode.LanguageModelToolResult([
          new vscode.LanguageModelTextPart(`Blad wykonania: ${message}`)
        ]);
      }
    },
    prepareInvocation(options) {
      const cmd = String(options.input.command ?? '').trim();
      return {
        invocationMessage: `Venom wykonuje lokalnie: ${cmd}`,
        confirmationMessages: {
          title: 'Venom execution tool',
          message: `Czy uruchomic komendę: ${cmd}?`
        }
      };
    }
  });
  context.subscriptions.push(toolDisposable);

  const participant = vscode.chat.createChatParticipant('venom.execution', async (request, chatContext, stream) => {
    void chatContext;

    const workspaceRoot = await resolveRepoRoot();
    if (!workspaceRoot) {
      stream.markdown('Brak otwartego workspace. Otworz folder repo i sprobuj ponownie.');
      return;
    }

    const prompt = request.prompt.trim();

    if (!isGitStatusIntent(prompt)) {
      stream.markdown(
        [
          'Ten participant obsluguje tylko execution-first dla statusu Git.',
          '',
          'Uzyj: `@venom-exec sprawdz status git`.'
        ].join('\n')
      );
      return;
    }

    stream.progress('Wykonuje lokalnie przez tool API: run_git_status');

    try {
      const toolResult = await vscode.lm.invokeTool(
        TOOL_NAME,
        {
          input: { command: 'git status --short --branch' },
          toolInvocationToken: request.toolInvocationToken
        },
        undefined
      );
      const status = toolResultToText(toolResult);
      stream.markdown(['```bash', status || '(brak outputu)', '```'].join('\n'));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      stream.markdown(`Blad wykonania komendy: ${message}`);
    }
  });

  context.subscriptions.push(participant);

  const orchestrator = vscode.chat.createChatParticipant('venom.orchestrator', async (request, chatContext, stream) => {
    void chatContext;
    const workspaceRoot = await resolveRepoRoot();
    if (!workspaceRoot) {
      stream.markdown('Brak otwartego workspace. Otworz folder repo i sprobuj ponownie.');
      return;
    }

    const prompt = request.prompt.trim();
    if (!isGitStatusIntent(prompt)) {
      stream.markdown(
        [
          'Ten participant jest execution-first dla statusu Git.',
          '',
          'Uzyj: `@venom-agent sprawdz status git`.'
        ].join('\n')
      );
      return;
    }

    stream.progress('Venom Agent wywoluje tool run_git_status');
    try {
      const toolResult = await vscode.lm.invokeTool(
        TOOL_NAME,
        {
          input: { command: 'git status --short --branch' },
          toolInvocationToken: request.toolInvocationToken
        },
        undefined
      );
      const status = toolResultToText(toolResult);
      stream.markdown(['```bash', status || '(brak outputu)', '```'].join('\n'));
      stream.markdown('Nastepny krok: jesli output jest poprawny, przejdz do `git diff --shortstat`.');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      stream.markdown(`Blad wykonania komendy: ${message}`);
    }
  });
  context.subscriptions.push(orchestrator);


  const cmd = vscode.commands.registerCommand('venom.execution.runGitStatus', async () => {
    const workspaceRoot = await resolveRepoRoot();
    if (!workspaceRoot) {
      vscode.window.showErrorMessage('Brak otwartego workspace.');
      return;
    }
    try {
      const out = await runGitStatus(workspaceRoot);
      await vscode.env.clipboard.writeText(out);
      vscode.window.showInformationMessage('Git status skopiowany do schowka.');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      vscode.window.showErrorMessage(`Blad: ${message}`);
    }
  });

  context.subscriptions.push(cmd);
}

export function deactivate() {
  // no-op
}
