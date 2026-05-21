# Inwentaryzacja artefaktow PR240

Ten dokument definiuje stabilny zakres porzadkowania PR240 i oddziela produkt od diagnostyki oraz artefaktow generowanych.

## W zakresie

### Produkt

- `.github/agents/venom-full-agent.agent.md`
- `.github/agents/venom-local-first-orchestrator.agent.md`
- `.github/copilot-instructions.md`
- `venom_core/agents/integrator.py`
- `venom_core/execution/skills/git_skill.py`
- `tools/vscode-chat-executor/package.json`
- `tools/vscode-chat-executor/package-lock.json`
- `tools/vscode-chat-executor/src/extension.ts`
- `tools/vscode-chat-executor/README.md`
- `tools/vscode-chat-executor/.vscode/launch.json`
- `tools/vscode-chat-executor/.vscode/extensions.json`
- `tools/vscode-chat-executor/.gitignore`

### Dokumentacja

- `docs/CHAT_OPERATOR.md`
- `docs/PL/CHAT_OPERATOR.md`
- ten dokument

### Sensowne testy i gate

- `tests/test_git_skill.py`
- `tests/test_integrator_agent.py`
- `make pr-fast`
- `make local-first-pr239-selftest`
- `make local-first-pr240-orchestrator-routing-probe`
- `make local-first-pr240-full-agent-handoff-probe`
- `make local-first-agent-config-validate`

## Poza zakresem

### Szum diagnostyczny

- probe tylko od sprawdzania obecnosci plikow lub tekstu
- logi eksperymentalne i eksporty debug
- tymczasowe outputy `test-results/*`

### Artefakty generowane

- `tools/vscode-chat-executor/node_modules/`
- `tools/vscode-chat-executor/out/`
- wygenerowane mapy JS i build output

### Wątki poboczne

- alternatywne eksperymenty routingu, ktore nie zmieniaja produktu
- duplikaty planow komend
- wyłącznie UI-narracyjne flow, ktore nie daja prawdziwego evidence

## Zasada robocza

Jesli plik nie:

1. dostarcza produktu,
2. broni produktu sensownym regression testem,
3. albo opisuje produkt operatorowi,

to nie nalezy do finalnego zakresu PR240.
