## Copilot Coding Agent — Minimal Operating Contract

Pełne zasady są w `docs/AGENTS.md` (source of truth). Ten plik jest skrótem.

1. Przed zakończeniem zadania uruchom `make pr-fast`.
2. Jeśli gate failuje, napraw i uruchom ponownie do zielonego wyniku (lub użyj ścieżki blokera środowiskowego z `docs/AGENTS.md`).
3. Dla zmian markdown-only (wszystkie zmienione pliki to `*.md`, niezależnie od katalogu) hard gate można pominąć.
4. W raporcie końcowym podaj: komendy, pass/fail, changed-lines coverage (lub `N/A` dla markdown-only), ryzyka/skipy z uzasadnieniem.
5. Nie maskuj statusu walidacji pipeline bez `set -o pipefail`.
6. Dla workspace Venom trzymaj local-first jako domyślny kontrakt:
   - start od `git status --short`, `git diff --stat` i `#codebase`,
   - traktuj local semantic index jako canonical knowledge base,
   - używaj `.github/agents/*` i `.github/prompts/*` jako jawnych kontraktów ról i promptow,
   - nie dokładaj drugiego, równoległego stosu wiedzy bez jawnej decyzji w planie.
7. Dla repo-truth intentow (`sprawdz status git`, `stan repo`, `git status`, `repo git`) aktywny agent ma najpierw wykonac handoff przez `agent` / `runSubagent` do `Venom Local-First Orchestrator` albo `Venom Full Agent`, a nie uruchamiac bezposrednio `terminal`; po powrocie zwraca evidence, nie plan ani liste komend.
8. Jeśli handoff lub tool nie jest dostępny, odpowiedz jawnie `tool_unavailable_or_unsupported_session` zamiast symulowac routing.
9. Domyslny jezyk odpowiedzi agenta w workspace Venom to polski; angielski uzywaj tylko gdy user poprosi albo dokument/format wymaga angielskiego.
