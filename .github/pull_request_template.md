## Summary

<!-- Krótki opis: co i dlaczego -->

## Scope

<!-- In scope / out of scope -->

## Quality Gates (Hard Gate)

- [ ] `make pr-fast` passed
- [ ] CI required checks passed (`Forbidden Paths Guard`, `Architecture drift guard`, `Backend lite (pytest)`, `Frontend lite (lint)`, `OpenAPI Contract (export + TS codegen)`, `SonarCloud Scan`, `Quick validator (syntax + CI-lite deps)`)
- [ ] For new/renamed tests: `make test-catalog-sync` + `make test-groups-sync` executed

## Validation Report

### Commands run

```bash
# wklej faktycznie uruchomione komendy
```

### Results (pass/fail)

<!-- np. make pr-fast: PASS -->

### Changed-lines coverage

<!-- np. 80.3% -->

## Risks / Limitations / Skips

<!-- Wymień ryzyka lub skipy i uzasadnij -->

## Evidence

<!-- Krótkie logi, link do artifactów CI, screeny jeśli dotyczy -->

---

**Policy:** PR bez wypełnionych sekcji jakości i raportu walidacji oznaczamy jako `Not ready for review`.
