# Dokumentacja Decyzji Architektonicznych (ADR)

Ten katalog zawiera Architecture Decision Records (ADRy) dla systemu Venom. ADRy dokumentują ważne decyzje architektoniczne podjęte podczas ewolucji projektu.

## Czym jest ADR?

Architecture Decision Record (ADR) dokumentuje pojedynczą decyzję architektoniczną, taką jak wybór technologii, wzorców projektowych lub konwencji systemowych. Każdy ADR zawiera:
- **Kontekst**: Sytuacja wymagająca podjęcia decyzji
- **Decyzja**: Wybrane rozwiązanie
- **Status**: Zaproponowany, Zaakceptowany, Wycofany lub Zastąpiony
- **Konsekwencje**: Pozytywne i negatywne skutki decyzji

## Indeks ADR

| ID | Tytuł | Status | Data |
|----|-------|--------|------|
| [ADR-001](./ADR-001-runtime-strategy-llm-first.md) | Strategia Runtime: LLM-First z ONNX Fallback | Zaakceptowany | 2026-02-18 |
| [ADR-003](./ADR-003-chat-2-shell.md) | Chat 2.0 jako osobna powłoka | Wdrożenie częściowo zastąpione przez ADR-004 | 2026-10-30 |
| [ADR-004](./ADR-004-studio-runtime-composition.md) | Osobne kompozycje aplikacji Venom i Studio | Decyzja implementacyjna | 2026-10-31 |

## Konwencja nazewnictwa ADR

ADRy przestrzegają wzorca nazewnictwa: `ADR-XXX-krotki-tytul.md`
- **XXX**: Trzycyfrowy numer sekwencyjny (001, 002, itd.)
- **krotki-tytul**: Krótki opis w formacie kebab-case

## Odniesienia

- [Architecture Decision Records (ADR) by Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR GitHub Organization](https://adr.github.io/)
