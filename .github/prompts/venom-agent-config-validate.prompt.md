---
agent: Venom Local-First Orchestrator
description: Waliduj konfiguracje agentow i promptow w workspace Venom.
---

# Agent config validation

Uruchom walidacje konfiguracji agentow, promptow i instrukcji workspace.

## Oczekiwany wynik

1. Lista sprawdzonych plikow.
2. Liczba bledow i ostrzezen.
3. Jasny PASS albo lista problemow do naprawy.

## Reguly

1. Sprawdz frontmatter custom agentow i prompt files.
2. Sprawdz kontrakt instrukcji workspace i jezyk domyslny.
3. Nie uznawaj konfiguracji za poprawna bez jawnego PASS.
