# Contributing to Venom 🧬

Dziękujemy, że chcesz pomóc w rozwoju projektu! Poniżej znajdziesz zasady, wskazówki i instrukcje, jak możesz się zaangażować.

## Spis treści

- [Jak zgłosić błąd / feature request](#how-to-report-bugs-or-request-features)
- [Jak zaproponować zmianę / kod](#how-to-contribute-code)
- [Standard commitów i formatowania](#code-style-and-commit-messages)
- [Testy i CI](#tests-and-ci)
- [Kod zachowania i etyka](#code-of-conduct)
- [Kontakt / pytania](#contact)

---

## How to report bugs or request features

- Sprawdź, czy podobny issue już istnieje.
- Jeśli nie — otwórz nowy issue, podając:
  - opis kroku do reprodukcji (jeśli to bug),
  - wersję Pythona i system,
  - opcjonalnie stack trace / logi,
  - oczekiwany rezultat vs. aktualny.

---

## How to contribute code

1. Sforkuj repo → utwórz branch `feat/`, `fix/` albo `chore/`.
2. Zrób zmiany, uruchom `make lint && make test` (lub lokalnie `pre-commit run --all-files && pytest`).
3. Dodaj tests / dokumentację, jeśli zmieniasz API / logikę.
4. Użyj standardowych commit-message (zobacz niżej).
5. Zrób PR — jeśli wszystko przejdzie, zmergujemy do `main`.

---

## Code style and commit messages

- Kod w Pythonie: **PEP-8 / Black + Ruff + isort**.
- Przed commitem uruchom `pre-commit install`.
- Commit message:
  - format: `type(scope): krótki opis` (np. `feat(core): add orchestrator`)
  - typy: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`.
  - pierwszy wiersz ≤ 50 znaków, potem pusta linia, potem szczegóły.

---

## Tests and CI

- Wszystkie nowo dodawane funkcjonalności muszą mieć testy (pytest).
- Testy wrzucamy do katalogu `/tests`.
- CI Lite na PR najpierw sprawdza szybkie bramki jakości (lint + wybrane testy unit).
- SonarCloud jest wymaganą bramką PR (bugi, podatności, code smell, utrzymywalność, duplikacje).
- Snyk jest uruchamiany okresowo, aby wychwytywać nowe CVE w zależnościach i kontenerach.

### Checklist jakości przed PR

- Uruchom `pre-commit run --all-files`.
- Uruchom `mypy venom_core`.
- Utrzymuj prostą logikę funkcji (unikaj wysokiej złożoności kognitywnej i rozbudowanych bloków warunkowych).
- Usuwaj martwy kod, nieużywane importy i placeholdery.
- Traktuj uwagi `ruff`, `mypy` i Sonara jako blokery dla nowych zmian.

---

## Code of Conduct

Wszyscy współpracownicy zobowiązują się do **szacunku, uprzejmości i konstruktywnej współpracy**.
Nie tolerujemy: hejtu, obelg, nękania, spamowania.
Jeśli coś Cię niepokoi — otwórz issue lub skontaktuj się bezpośrednio.

---

## Contact

Autor / Maintainer: **Mac_** (mpieniak01)
Email / kontakt w GitHub – przez Issues / Discussions.

Dzięki za wkład — każdy PR i pomysł pomaga rozwijać Venom!
