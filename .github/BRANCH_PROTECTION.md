# Branch Protection Runbook (main)

Ten plik dokumentuje wymagane ustawienia repozytorium dla trybu Hard Gate.

## Wymagane ustawienia dla `main`

1. Require a pull request before merging.
2. Require approvals (min. 1; rekomendowane 2 dla zmian architektonicznych).
3. Dismiss stale pull request approvals when new commits are pushed.
4. Require status checks to pass before merging.
5. Do not allow bypassing the above settings for standard contributors.
6. Disable direct push to `main`.

## Required status checks (dokładne nazwy jobów)

1. `Backend lite (pytest)`
2. `Frontend lite (lint)`
3. `SonarCloud Scan`
4. `Quick validator (syntax + CI-lite deps)`

## Why

Te ustawienia wymuszają, że agent (i człowiek) nie domkną PR z czerwonymi bramkami jakości.

## Operational note

Ustawienia branch protection są konfigurowane w UI GitHub repo i nie są egzekwowane samym commitem.

## Automation helper

Możesz zastosować ustawienia skryptem (wymaga `gh` i uprawnień admin):

```bash
bash scripts/apply_branch_protection_hard_gate.sh owner/repo
```

## Related governance docs

- Agent access management: `.github/CODING_AGENT_ACCESS_MANAGEMENT.md`
- MCP usage policy for coding agent: `.github/CODING_AGENT_MCP_POLICY.md`
- Custom agents profiles: `.github/agents/`
