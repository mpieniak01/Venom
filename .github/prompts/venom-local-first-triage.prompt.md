---
agent: Venom Local-First Orchestrator
description: Lokalny triage repo przed implementacja.
---

# Local-first triage

Wykonaj lokalny triage przed zmianami.

## Cel

Ustal:
1. branch i source of truth,
2. aktywne pliki i ryzyko kolizji,
3. czy potrzebny jest plan, implementacja czy tylko review,
4. czy workspace search pokazuje odpowiednie pliki dla zadania.

## Minimalna sekwencja

1. `git status --short`
2. `git diff --stat`
3. `#codebase` dla zakresu zadania
4. wskaz najbardziej prawdopodobny nastepny krok

## Reguly

1. Nie zgaduj bez sprawdzenia repo.
2. Jesli context jest niepelny, nazwij to wprost.
3. Jesli narzedzie nie odpowiada, podaj fallback.
4. Nie rozszerzaj scope ponad zadany problem.
