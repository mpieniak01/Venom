# Coding Agent Access Management

Ten runbook mapuje ustawienia z GitHub Copilot Coding Agent do polityki repo Venom.

## Cel

Zapewnić minimalne uprawnienia i kontrolę ryzyka dla agentów kodowania:

1. agent ma wystarczający dostęp do tworzenia branchy/PR,
2. agent nie może obchodzić bramek jakości,
3. merge do `main` pozostaje pod branch protection.

## Zakres konfiguracji (GitHub UI)

Ustawienia znajdują się na poziomie:

1. Enterprise/Organization (globalne włączenie coding agent i polityki),
2. Repository (dostęp dla repo i constraints),
3. Branch protection (egzekucja required checks).

## Rekomendowana polityka dla Venom

1. Włącz coding agent tylko dla zaufanych członków zespołu.
2. Ogranicz bypass branch protection dla adminów (preferowane: brak bypassu).
3. Wymagaj PR review i stale-review dismissal.
4. Wymagaj status checks z `.github/BRANCH_PROTECTION.md`.
5. Zablokuj direct push do `main`.

## Hard Gate alignment checklist

- [ ] Branch protection na `main` aktywny.
- [ ] Required checks ustawione zgodnie z runbook.
- [ ] PR template aktywny (`.github/pull_request_template.md`).
- [ ] Instrukcje agenta aktywne (`AGENTS.md`, `.github/copilot-instructions.md`).
- [ ] Hook config obecny (`.github/hooks/hard-gate.json`).

## Wdrożenie techniczne

Skrypt pomocniczy:

```bash
bash scripts/apply_branch_protection_hard_gate.sh owner/repo
```

## Audyt okresowy (co sprint)

1. Sprawdź, czy nie było merge z czerwonymi required checks.
2. Sprawdź, czy PR-y agenta mają wypełniony raport jakości.
3. Sprawdź, czy nie przyznano nadmiarowych uprawnień bypass.
