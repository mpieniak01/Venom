# Venom Chat Executor (VS Code extension)

Execution-first participant dla chatu VS Code.

## Cel

Zapewnia deterministyczne wykonanie `git status --short --branch` zamiast tekstowego JSON payloadu.

## Uzycie

1. Otworz ten katalog jako extension project i zbuduj:
   - `npm install`
   - `npm run build`
2. Uruchom Extension Development Host (F5).
3. W czacie wpisz:
   - `@venom-exec sprawdz status git`

Participant wykona lokalnie `git status --short --branch` w katalogu workspace i zwroci output jako blok `bash`.

W aktualnej implementacji participant wywoluje lokalny tool `run_git_status` przez VS Code Language Model Tool API (`lm.invokeTool`), co wymusza przejscie przez execution layer zamiast samego tekstu modelu.

Domyslnie extension probuje wykryc katalog repo z aktywnego workspace. Jesli ustawisz `venom.execution.repoRoot`, to wymusi wykonanie komendy w podanej sciezce i zwroci `REPO_ROOT=...` w output.

## Dlaczego to dziala

To participant z kodem wykonawczym (`execFile`) po stronie hosta VS Code, wiec komenda trafia do execution layer, a nie do samego LLM jako tekst do interpretacji.


## Debug Start (bez bledu "brak debuggera")

1. Otworz folder `tools/vscode-chat-executor` jako osobny workspace.
2. Uruchom konfiguracje `Run Extension` z panelu **Run and Debug** (nie uruchamiaj aktywnego pliku).
3. Jesli nadal pojawia sie komunikat o debugerze pliku, uzyj terminala:
   - `code --extensionDevelopmentPath=/home/ubuntu/venom/tools/vscode-chat-executor`
