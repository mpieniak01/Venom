## Copilot Coding Agent — Minimal Operating Contract

Pełne zasady są w `docs/AGENTS.md` (source of truth). Ten plik jest skrótem.

1. Przed zakończeniem zadania uruchom `make pr-fast`.
2. Jeśli gate failuje, napraw i uruchom ponownie do zielonego wyniku (lub użyj ścieżki blokera środowiskowego z `docs/AGENTS.md`).
3. Dla zmian doc-only (`docs/**`, `docs_dev/**`, `README*.md`, root `*.md`) hard gate można pominąć.
4. W raporcie końcowym podaj: komendy, pass/fail, changed-lines coverage, ryzyka/skipy z uzasadnieniem.
5. Nie maskuj statusu walidacji pipeline bez `set -o pipefail`.
