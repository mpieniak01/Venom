# 114 - Security + test hardening (zakres do review)

## Cel
Zebrać w jednym PR/branchu poprawki bezpieczeństwa i stabilności testów, tak aby:
- zamknąć zgłoszenia typu security hotspot / secret exposure,
- ograniczyć flaky w testach E2E/integracyjnych,
- utrzymać spójny kontrakt uruchamiania `make pytest` i `make e2e`.

## Zakres zmian (dla recenzentów)

### 1) Security hardening (kod produkcyjny)
- `venom_core/services/benchmark.py`
  - walidacja `benchmark_id` przez `uuid.UUID(...)` zamiast regex.
  - losowanie pytań przez `secrets.SystemRandom()`.
- `venom_core/memory/vector_store.py`
  - walidacje wejścia bez `re.match` (whitelist znaków).
  - fallback leksykalny dla recall przy pustym wyniku semantycznym.
  - limity ochronne fallbacku (`MAX_FALLBACK_QUERY_CHARS`, `MAX_FALLBACK_QUERY_TOKENS`, `MAX_FALLBACK_SCAN_ROWS`) dla ograniczenia kosztownego skanowania.
- `venom_core/execution/skills/web_skill.py`
  - bezpieczny dynamiczny fallback importu DDGS (bez twardego importu brakujących modułów).
- `venom_core/execution/skills/browser_skill.py`
  - dynamiczny import Playwright (brak twardej zależności import-time).

### 2) Stabilność i odporność testów
- `tests/conftest.py`
  - wykrywanie Dockera sprawdza dostępność daemona (`docker info`), nie tylko binarki.
  - `requires_docker_compose` sprawdza działające `docker compose`.
- `tests/perf/test_learning_logs_integrity_e2e.py`
  - retry + backoff dla błędów transportowych HTTP/SSE (`ReadError`, `ReadTimeout`, itp.),
  - graceful `skip` zamiast fail po wyczerpaniu prób.
- `venom_core/execution/skills/test_skill.py`
  - parser wyników pytest poprawnie czyta formaty podsumowań typu `2 passed, 1 failed ...`.
- `tests/test_desktop_sensor_roi.py`
- `tests/test_memory_consolidator.py`
- `tests/test_hardware_bridge.py`
  - usunięcie literalnych danych testowych wyglądających na sekrety/IP (utrzymanie semantyki testów).

### 3) Spójność uruchamiania i dokumentacja
- `scripts/run-e2e-optimal.sh`
  - auto-instalacja Chromium Playwright przy pustym cache.
- `Makefile`
  - `make pytest` respektuje istniejące `VENOM_API_BASE` (nie nadpisuje bezwarunkowo).
- `tests/perf/chat_pipeline.py`
  - fallback endpointu API z `VENOM_API_PORT`/`APP_PORT`.
- `README_PL.md`
  - doprecyzowanie: `make pytest` testuje backend API (domyślnie `:8000`), UI działa na `:3000`.

## Checklist review
- Czy zmiany nie rozszerzają uprawnień runtime i nie wprowadzają nowych wektorów injection.
- Czy fallback leksykalny w VectorStore ma akceptowalne limity i nie degraduje dużych kolekcji.
- Czy skip/logika detekcji Dockera nie ukrywa testów, które powinny przechodzić w CI z Docker daemon.
- Czy `make pytest` i `make e2e` działają poprawnie dla środowisk lokalnych i CI.

## Ryzyka / uwagi
- Auto-download Playwright w `run-e2e-optimal.sh` wymaga dostępu do sieci.
- Fallback leksykalny to mechanizm ratunkowy; semantyczne wyszukiwanie pozostaje ścieżką główną.
