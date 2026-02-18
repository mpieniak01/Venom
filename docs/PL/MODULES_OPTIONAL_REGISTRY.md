# Moduły Opcjonalne: Przewodnik Tworzenia i Utrzymania (PL)

Ten dokument opisuje uniwersalny, publiczny sposób tworzenia i operacji modułów opcjonalnych w Venom bez dopisywania importów na sztywno w `venom_core/main.py`.

## 1. Cele projektu

- Utrzymać stabilność OSS core, gdy moduły są wyłączone.
- Umożliwić niezależny rozwój i wydawanie modułów.
- Egzekwować kompatybilność (`module_api_version`, `min_core_version`) podczas startu.
- Rozdzielić flagi backend i frontend.

## 2. Model rejestru

Obsługiwane są dwa źródła modułów:
- wbudowany manifest opcjonalny (w core),
- zewnętrzny manifest z `API_OPTIONAL_MODULES`.

Format wpisu:

`module_id|module.path:router|FEATURE_FLAG|MODULE_API_VERSION|MIN_CORE_VERSION`

Pola:
- `module_id` (wymagane): unikalny identyfikator modułu.
- `module.path:router` (wymagane): ścieżka importu routera FastAPI.
- `FEATURE_FLAG` (opcjonalne): flaga backend, np. `FEATURE_ACME`.
- `MODULE_API_VERSION` (opcjonalne): wersja kontraktu modułu.
- `MIN_CORE_VERSION` (opcjonalne): minimalna zgodna wersja core.

Przykłady:
- `API_OPTIONAL_MODULES=my_mod|acme_mod.api:router|FEATURE_ACME|1|1.5.0`
- `API_OPTIONAL_MODULES=mod_a|pkg.a:router|FEATURE_A|1|1.5.0,mod_b|pkg.b:router`

## 3. Kontrakt kompatybilności

Core porównuje manifest modułu z:
- `CORE_MODULE_API_VERSION` (domyślnie `1`)
- `CORE_RUNTIME_VERSION` (domyślnie `1.5.0`)

Jeśli moduł jest niekompatybilny:
- moduł jest pomijany,
- start aplikacji trwa dalej,
- do logów trafia ostrzeżenie.

Niepoprawne wpisy manifestu:
- nie wywracają startu,
- są ignorowane,
- generują ostrzeżenia.

## 4. Struktura modułu (pełne drzewo)

Poniżej są dwa warianty, które razem pokazują "gdzie tworzyć pliki modułu".

### 4.1. Wariant A: moduł wbudowany w repo Venom (jak `module_example`)

```text
venom/
├─ venom_core/
│  ├─ api/
│  │  ├─ routes/
│  │  │  └─ module_example.py
│  │  └─ schemas/
│  │     └─ module_example.py
│  └─ services/
│     └─ module_example_loader.py
├─ web-next/
│  ├─ app/
│  │  └─ module-example/
│  │     └─ page.tsx               # opcjonalnie, jeśli moduł ma własny ekran
│  └─ components/
│     └─ layout/
│        └─ sidebar-helpers.ts     # wpis nawigacyjny z feature flagą
└─ docs/
   └─ MODULES_OPTIONAL_REGISTRY.md
```

To jest wariant dobry dla modułów demonstracyjnych lub technicznych.

### 4.2. Wariant B: moduł w osobnym repo (docelowy dla produktów)

```text
venom-module-acme/                 # osobne repo (najlepiej private)
├─ pyproject.toml
├─ README.md
├─ venom_acme/
│  ├─ __init__.py
│  ├─ manifest.py                  # metadane modułu (id, wersje, kompatybilność)
│  ├─ api/
│  │  ├─ __init__.py
│  │  ├─ routes.py                 # FastAPI router eksportowany do core
│  │  └─ schemas.py                # Pydantic modele API modułu
│  ├─ services/
│  │  └─ service.py                # logika domenowa modułu
│  └─ connectors/
│     └─ github.py                 # opcjonalne integracje (sekrety tylko z env)
└─ tests/
   ├─ test_routes.py
   └─ test_service.py
```

W Venom core moduł jest tylko "podpinany":
- instalacja pakietu modułu (pip),
- rejestracja przez `API_OPTIONAL_MODULES`,
- włączenie flag.

### 4.3. Minimalny zestaw plików modułu (wymagany)

1. `api/routes.py` z obiektem `router`.
2. `api/schemas.py` z modelami request/response.
3. `services/service.py` z logiką modułu.
4. `pyproject.toml` (instalacja jako pakiet).
5. `README.md` z instrukcją env/flag.
6. Testy modułu (`tests/*`).

## 5. Cykl życia modułu (rekomendacja)

1. Rozwijaj moduł w osobnym repozytorium/pakiecie.
2. Publikuj artefakt instalowalny (wheel/source package).
3. Instaluj artefakt w środowisku runtime.
4. Rejestruj moduł przez `API_OPTIONAL_MODULES`.
5. Włącz flagę backendową.
6. Włącz flagę frontendową (jeśli moduł ma UI).
7. Zweryfikuj health i logi.
8. Rollback: wyłącz flagę lub usuń wpis z manifestu.

## 6. Moduł przykład: zarządzanie i przełączanie

Aktualny wbudowany moduł opcjonalny:
- `module_example` -> `venom_core.api.routes.module_example:router`

Włączenie backend:
- `FEATURE_MODULE_EXAMPLE=true`

Włączenie nawigacji frontend:
- `NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE=true`

Bazowa ścieżka API modułu:
- `/api/v1/module-example/*`

Bezpieczne wyłączenie:
- ustaw `FEATURE_MODULE_EXAMPLE=false` (backend off),
- ustaw `NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE=false` (ukrycie wpisu w UI),
- opcjonalnie usuń odpowiadający wpis z `API_OPTIONAL_MODULES`.

## 7. Runbook operacyjny (szybka lista)

1. Sprawdź flagi:
- backend: `FEATURE_*`
- frontend: `NEXT_PUBLIC_FEATURE_*`
2. Sprawdź manifest:
- `API_OPTIONAL_MODULES` ma poprawne separatory `|` i `,`.
3. Sprawdź import:
- `module.path:router` da się zaimportować w runtime.
4. Sprawdź kompatybilność:
- `MODULE_API_VERSION` i `MIN_CORE_VERSION` pasują do core.
5. Sprawdź logi:
- moduł załadowany/pominięty z jednoznacznym powodem.

## 8. Testy i quality gates

Minimalna walidacja platformy modułów:
- `tests/test_module_registry.py`
- `web-next/tests/sidebar-navigation-optional-modules.test.ts`

Wymagane hard gate dla zmian w kodzie:
- `make pr-fast`
- `make check-new-code-coverage`

## 9. Granica zakresu

Ten mechanizm dostarcza infrastrukturę modułową.
Nie przenosi prywatnej logiki biznesowej do OSS core.
