# 096c — Plan bezpiecznego zrównoleglenia pytest w WSL

## Cel
Bezpiecznie przywrócić równoległe uruchamianie testów pytest w WSL, ograniczając ryzyko OOM i restartów systemu. Ustalić stabilną liczbę workerów, podział na testy lekkie/ciężkie i jasny schemat uruchomień.

> Uwaga: testy frontendowe `npm --prefix web-next run test:e2e` są już zoptymalizowane i działają poprawnie — nie wymagają zmian w tym planie.

## Kontekst i ograniczenia
- WSL potrafi zabić procesy (SIGKILL) przy presji pamięci.
- Historycznie próba `-n 8` kończyła się niestabilnością.
- `pytest.ini` ma domyślne `-n 4`, ale docelowo musimy zacząć ostrożniej.

## Zakres
- Tylko testy pytest (backend + unit/integration).
- Bez zmian w Playwright (testy `web-next` zostają osobno).

## Kryteria sukcesu
- Stabilny run pytest bez restartu WSL przez 3 kolejne uruchomienia.
- Udokumentowany bezpieczny poziom równoległości (np. `-n 2` lub `-n 3`).
- Jasny podział na testy lekkie i ciężkie, z osobnymi komendami uruchomienia.

## Plan działania
### 1) Inwentaryzacja i podział testów
- **Ciężkie (uruchamiać osobno lub z `-n 1`/`-n 2`)**:
  - `tests/perf/*` (marker `performance`)
  - `tests/test_browser_skill.py`
  - `tests/test_skills_enhancements.py`
  - `tests/test_forge_integration.py`
- **Lekkie**:
  - Pozostałe testy jednostkowe i te z pełnymi mockami.

### 1b) Zasada porządku (3 grupy, alfabetycznie)
- Testy są podzielone na 3 grupy: **heavy → long → light**.
- Każda grupa jest **posortowana alfabetycznie** (po ścieżce pliku), aby utrzymać stały porządek.
- Pliki konfiguracyjne z listami testów:
  - `config/pytest-groups/heavy.txt`
  - `config/pytest-groups/long.txt`
  - `config/pytest-groups/light.txt`
- Kryteria grup:
  - **heavy**: `tests/perf/*` + `test_browser_skill.py` + `test_skills_enhancements.py` + `test_forge_integration.py`
  - **long**: nazwa pliku zawiera `integration`, `e2e`, `stream`, `load`, `latency` (z wyłączeniem heavy) + ręczne wyjątki
  - **light**: pozostałe testy
- Uwaga: po dodaniu nowych testów listy należy odświeżyć (alfabetycznie).

### 2) Startowy tryb bezpieczny
- Uruchomienia bazowe (bezpieczny start):
  - Lekkie testy: `pytest -n 2 -m "not performance" -k "not browser_skill and not skills_enhancements and not forge_integration"`
  - Ciężkie testy osobno: `pytest -n 1 tests/perf` itd.

### 3) Ramp-up liczby workerów
- Jeśli `-n 2` przechodzi stabilnie, kolejno testować:
  - `-n 3` → `-n 4`
- Każdy poziom: min. 3 kolejne runy bez SIGKILL/OOM.
- Po nieudanym runie wracamy do poprzedniego stabilnego poziomu.

### 4) Weryfikacja stabilności (monitoring)
- Sprawdzać w `/var/log/syslog` i `/var/log/dmesg`:
  - OOM killer
  - SIGKILL dla `pytest`
- Zbierać metryki: czas całkowity, peak RAM, liczba workerów.

### 5) Utrwalenie wyniku
- Ustalić docelową wartość `-n` (jeśli stabilne, zaktualizować `pytest.ini`).
- Zapisać docelowy zestaw komend w README (sekcja testów backendu).

## Ryzyka i mitigacje
- **OOM / restart WSL** → ograniczenie `-n`, rozdzielenie ciężkich testów.
- **Kolizje z procesami tła (ollama, dev serwery)** → wyłączać przed testami.
- **Skoki pamięci podczas I/O** → unikać równoległego uruchamiania E2E.

## Ustawienia końcowe (optymalne)
**Optymalna konfiguracja uruchomień:**
- **heavy:** `-n 1`
- **long:** `-n 2`
- **light:** `-n 6`

Uzasadnienie skrótowe: to najszybsze stabilne konfiguracje przy akceptowalnym zużyciu pamięci; `-n 4` dla long jest niestabilne, a `-n 8` dla light podbija swap bez realnego zysku czasu.

## Zestawienie wyników (czas + RAM po teście)
Legenda: RAM po teście = `free -m` (used/free/buff-cache/avail), swap = `free -m` (swap used).

### Heavy (pojedyncze testy, -n 1)
| Workerzy | Podgrupa | Wynik | Czas | RAM po teście (MB) | Swap used (MB) |
|---:|---|---|---:|---|---:|
| 1 | tests/perf | 2 passed, 4 skipped | ~6.6s | `used=3793 free=3738 buff=8696 avail=12110` | 544 |
| 1 | tests/test_browser_skill.py | 4 passed, 3 skipped | ~24.0s | `used=3793 free=3457 buff=8976 avail=12110` | 544 |
| 1 | tests/test_skills_enhancements.py | 14 passed | ~2.9s | `used=3798 free=3449 buff=8979 avail=12106` | 544 |
| 1 | tests/test_forge_integration.py | 3 skipped | ~0.4s | `used=3800 free=3447 buff=8979 avail=12103` | 544 |

### Long (po przeniesieniu test_state_and_orchestrator.py)
| Workerzy | Wynik | Czas | RAM po teście (MB) | Swap used (MB) |
|---:|---|---:|---|---:|
| 1 | 84 passed, 8 skipped | ~58.1s | `used=3805 free=3362 buff=9059 avail=12098` | 544 |
| 2 | 84 passed, 8 skipped | ~38.7s | `used=3796 free=3371 buff=9060 avail=12108` | 544 |
| 4 | **FAILED** (test_state_manager_persistence) | ~41.5s | `used=3795 free=3371 buff=9061 avail=12109` | 544 |

### Light (po przeniesieniu test_state_and_orchestrator.py)
| Workerzy | Wynik | Czas | RAM po teście (MB) | Swap used (MB) |
|---:|---|---:|---|---:|
| 1 | 1704 passed, 94 skipped | ~141.8s | `used=3258 free=6650 buff=6241 avail=12646` | 2 |
| 2 | 1704 passed, 94 skipped | ~81.9s | `used=4002 free=2689 buff=9535 avail=11901` | 2 |
| 4 | 1704 passed, 94 skipped | ~53.5s | `used=4116 free=4405 buff=7706 avail=11787` | 32 |
| 6 | 1704 passed, 94 skipped | ~43.4s | `used=3208 free=5669 buff=7272 avail=12695` | 51 |
| 8 | 1704 passed, 94 skipped | ~44.5s | `used=3517 free=7365 buff=5345 avail=12387` | 566 |

## Uwagi końcowe
- Testy `npm --prefix web-next run test:e2e` są stabilne i pozostają poza tym planem.
- Po ustaleniu stabilnego `-n` warto rozważyć ograniczenie równoległości tylko dla ciężkich markerów (np. przez osobny job CI).

## Konfiguracja `npm --prefix web-next run test:e2e` (stan obecny)
Wynika z `web-next/package.json`, `web-next/playwright.config.ts`, `web-next/scripts/check-e2e-env.mjs`.

**Łańcuch uruchomień:**
1) `test:e2e:preflight` — `node scripts/check-e2e-env.mjs`
2) `test:e2e:latency` — `PLAYWRIGHT_REUSE_SERVER=true PLAYWRIGHT_MODE=dev playwright test tests/perf/chat-latency.spec.ts --workers=1`
3) `test:e2e:functional` — `PLAYWRIGHT_REUSE_SERVER=true PLAYWRIGHT_MODE=dev playwright test tests/smoke.spec.ts tests/chat-mode-routing.spec.ts tests/streaming.spec.ts`

**Ustawienia Playwright (dev):**
- `PLAYWRIGHT_MODE=dev` ⇒ `webServer.command = npm run dev -- --hostname ${PLAYWRIGHT_HOST||127.0.0.1} --port ${PLAYWRIGHT_PORT||3000}`
- `PLAYWRIGHT_REUSE_SERVER=true` ⇒ Playwright **nie startuje** webServer (zakłada już działający Next)
- `baseURL = http://${PLAYWRIGHT_HOST||127.0.0.1}:${PLAYWRIGHT_PORT||3000}` (lub `BASE_URL`)
- `headless: true`, `fullyParallel: true`, `timeout: 30s`, `expect.timeout: 5s`
- Artefakty: screenshot/video tylko przy błędach

### `test:e2e:functional` — pomiar czasu i RAM po teście (workers)
| Workerzy | Wynik | Czas | RAM po teście (MB) | Swap used (MB) |
|---:|---|---:|---|---:|
| 1 | 28 passed | ~67s | `used=8236 free=2156 buff=5855 avail=7668` | 513 |
| 2 | 28 passed | ~42s | `used=8148 free=2223 buff=5876 avail=7756` | 513 |
| 4 | 28 passed | ~34s | `used=8174 free=2295 buff=5757 avail=7729` | 528 |
| 8 | 28 passed | ~34s | `used=8195 free=3337 buff=4694 avail=7708` | 534 |

**Wniosek (optymalne):** `test:e2e:functional` uruchamiamy z `--workers=4` (najkrótszy czas bez wzrostu swap vs 8; `--workers=8` nie poprawia wyniku).
