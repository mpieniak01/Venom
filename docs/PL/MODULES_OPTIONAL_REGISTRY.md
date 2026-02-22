# Moduły Opcjonalne: Przewodnik Tworzenia i Utrzymania (PL)

Ten dokument opisuje uniwersalny, publiczny sposób tworzenia i operacji modułów opcjonalnych w Venom bez dopisywania importów na sztywno w `venom_core/main.py`.

## 1. Cele projektu

- Utrzymać stabilność OSS core, gdy moduły są wyłączone.
- Umożliwić niezależny rozwój i wydawanie modułów.
- Egzekwować kompatybilność (`module_api_version`, `min_core_version`) podczas startu.
- Rozdzielić flagi backend i frontend.

## 2. Model rejestru

Obsługiwane jest jedno źródło modułów produktowych:
- zewnętrzny manifest z `API_OPTIONAL_MODULES`.
- core nie utrzymuje listy modułów "na sztywno".

Preferowany format wpisu (bez duplikowania danych z manifestu):

`API_OPTIONAL_MODULES=manifest:/home/ubuntu/venom/modules/<repo-modulu>/module.json`

Format legacy (kompatybilność wsteczna):

`module_id|module.path:router|FEATURE_FLAG|MODULE_API_VERSION|MIN_CORE_VERSION`

Pola:
- `module_id` (wymagane): unikalny identyfikator modułu.
- `module.path:router` (wymagane): ścieżka importu routera FastAPI.
- `FEATURE_FLAG` (opcjonalne): flaga backend, np. `FEATURE_ACME`.
- `MODULE_API_VERSION` (opcjonalne): wersja kontraktu modułu.
- `MIN_CORE_VERSION` (opcjonalne): minimalna zgodna wersja core.

Przykłady:
- `API_OPTIONAL_MODULES=manifest:/home/ubuntu/venom/modules/venom-module-example/module.json`
- `API_OPTIONAL_MODULES=manifest:/home/ubuntu/venom/modules/mod-a/module.json,manifest:/home/ubuntu/venom/modules/mod-b/module.json`
- (legacy) `API_OPTIONAL_MODULES=my_mod|acme_mod.api:router|FEATURE_ACME|1.0.0|1.6.0`

## 3. Kontrakt kompatybilności

Core porównuje manifest modułu z:
- `CORE_MODULE_API_VERSION` (domyślnie `1.0.0`)
- `CORE_RUNTIME_VERSION` (domyślnie `1.6.0`)

Jeśli moduł jest niekompatybilny:
- moduł jest pomijany,
- start aplikacji trwa dalej,
- do logów trafia ostrzeżenie.

Niepoprawne wpisy manifestu:
- nie wywracają startu,
- są ignorowane,
- generują ostrzeżenia.

## 4. Struktura modułu (jedyny wariant docelowy)

### 4.1. Moduł w osobnym repo (docelowy dla produktów)

Ustalona konwencja lokalizacji:
- katalog kolekcji modułów: `/home/ubuntu/venom/modules`
- każdy moduł jako osobne repo wewnątrz tej kolekcji

Przykład:
- `/home/ubuntu/venom/modules/venom-module-example`

```text
/home/ubuntu/venom/
├─ venom_core/                         # repo core
├─ web-next/                           # frontend core
│  ├─ app/
│  │  └─ [moduleSlug]/page.tsx         # dynamiczny host route modułów
│  ├─ lib/generated/
│  │  └─ optional-modules.generated.ts # auto-generated z module.json
│  ├─ scripts/
│  │  └─ generate-optional-modules.mjs # generator manifestów FE
│  └─ components/layout/
│     └─ sidebar-helpers.ts            # menu pobierane z manifestów modułów
└─ modules/                            # kolekcja repo modułów
   └─ venom-module-example/            # osobne repo modułu (najlepiej private)
      ├─ pyproject.toml
      ├─ README.md
      ├─ module.json                   # metadane modułu (id, wersje, entrypointy)
      ├─ venom_module_<slug>/
      │  ├─ __init__.py
      │  ├─ manifest.py               # metadane modułu (id, wersje, kompatybilność)
      │  ├─ api/
      │  │  ├─ __init__.py
      │  │  ├─ routes.py              # FastAPI router eksportowany do core
      │  │  └─ schemas.py             # Pydantic modele API modułu
      │  ├─ services/
      │  │  └─ service.py             # logika domenowa modułu
      │  └─ connectors/
      │     └─ github.py              # opcjonalne integracje (sekrety tylko z env)
      ├─ web_next/      # frontend modułu (separowany od core)
      │  ├─ page.tsx                   # główny ekran modułu (np. /module-example)
      │  ├─ components/
      │  │  └─ ModuleExamplePanel.tsx
      │  └─ api/
      │     └─ client.ts               # klient do /api/v1/module-example/*
      └─ tests/
         ├─ test_routes.py
         └─ test_service.py
```

W Venom core moduł jest tylko "podpinany":
- instalacja pakietu modułu (pip),
- rejestracja przez `API_OPTIONAL_MODULES`,
- włączenie flag.
- uruchomienie generatora FE (`node web-next/scripts/generate-optional-modules.mjs`).

Jak dodać nowy ekran modułu (w praktyce):
1. W repo modułu tworzysz ekran, np. `web_next_<module_id>/page.tsx`.
2. W `module.json` ustawiasz frontend:
   - `nav_path` (np. `/module-example`)
   - `feature_flag` (np. `NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE`)
   - `component_import` (import względny liczony od `web-next/lib/generated/optional-modules.generated.ts`, np. `../../../modules/venom-module-example/web-next/page`)
3. Generator odświeża `optional-modules.generated.ts`.
4. `web-next/app/[moduleSlug]/page.tsx` i menu pobierają konfigurację z generatora (bez ręcznych zmian route/menu w core).
5. Po wyłączeniu flagi ekran znika z nawigacji i nie jest dostępny przez URL.

I18n modułu (ważne):
- tłumaczenia modułu trzymamy w repo modułu (np. `web_next/i18n/pl.ts`, `en.ts`, `de.ts`),
- nie dopisujemy kluczy modułu do globalnych locale core (`web-next/lib/i18n/locales/*`),
- manifest modułu dostarcza etykiety nawigacji (`frontend.nav_labels`), więc menu działa bez zmian w core.

Wspólna operacja z jednej stacji developerskiej:
- `make modules-status` (status core + wszystkich repo modułów),
- `make modules-branches` (aktywne branche core + moduły),
- `make modules-pull` (pull --ff-only dla core + modułów),
- `make modules-exec CMD='git status -s'` (to samo polecenie w całym workspace).

### 4.2. Minimalny zestaw plików modułu (wymagany)

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
4. Rejestruj moduł przez `API_OPTIONAL_MODULES` wskazując `manifest:/.../module.json`.
5. Włącz flagę backendową.
6. Włącz flagę frontendową (jeśli moduł ma UI).
7. Zweryfikuj health i logi.
8. Rollback: wyłącz flagę lub usuń wpis z manifestu.

## 6. Module Example: status i przełączanie
`module_example` traktujemy jako moduł referencyjny platformy i kierujemy do pełnej separacji repo (`/home/ubuntu/venom/modules/venom-module-example`).
W praktyce operacyjnej obowiązuje model modułu zewnętrznego (4.1).

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
- `API_OPTIONAL_MODULES` wskazuje istniejące `module.json`.
- preferuj `manifest:/.../module.json` zamiast formatu legacy `module_id|...`.
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
