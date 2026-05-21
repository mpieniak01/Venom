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

W aktualnej implementacji participant wywoluje lokalny tool `venom.runCommand` przez VS Code Language Model Tool API (`lm.invokeTool`), co wymusza przejscie przez execution layer zamiast samego tekstu modelu.

Domyslnie extension wykonuje komendy w `venom.execution.repoRoot` (`/home/ubuntu/venom`) i zwraca `REPO_ROOT=...` w output, zeby uniknac falszywych wynikow z niewlasciwego katalogu.

## Dlaczego to dziala

To participant z kodem wykonawczym (`execFile`) po stronie hosta VS Code, wiec komenda trafia do execution layer, a nie do samego LLM jako tekst do interpretacji.


## Debug Start (bez bledu "brak debuggera")

1. Otworz folder `tools/vscode-chat-executor` jako osobny workspace.
2. Uruchom konfiguracje `Run Extension` z panelu **Run and Debug** (nie uruchamiaj aktywnego pliku).
3. Jesli nadal pojawia sie komunikat o debugerze pliku, uzyj terminala:
   - `code --extensionDevelopmentPath=/home/ubuntu/venom/tools/vscode-chat-executor`
