# 76c: Kontynuacja refaktoru backendu (po 76b)

## Cel
- Domknac refaktor backendu w zakresie najbardziej ryzykownych obszarow (routes/models, model_registry).
- Utrzymac stabilnosc testow i zachowac kompatybilnosc z legacy fallback.
- Udokumentowac zmiany w architekturze i funkcjonalnosci.

## Kontekst
- Poprzedni etap (76b) wykonal czesciowe wydzielenia, ale nie domknal kluczowych refaktorow:
  - `venom_core/api/routes/models.py` pozostaje monolitem.
  - `venom_core/core/model_registry.py` nadal miesza I/O i logike biznesowa.

## Zakres
- Backend/serwisy: `venom_core` (głownie API i model registry).
- Bez zmian w warstwie UI i bez migracji do mikroserwisow.

## Priorytety refaktoru (kolejnosc)
1) **Podzial `venom_core/api/routes/models.py`**
   - Wydzielic sub-routery (registry/install/config/usage/translation).
   - Wydzielic wspolne walidatory Pydantic do osobnego modulu.
   - Utrzymac kompatybilnosc endpointow (bez zmiany sciezek API).

2) **Wydzielenie adapterow I/O z `venom_core/core/model_registry.py`**
   - Adaptery: `OllamaClient`, `HuggingFaceClient` (subprocess + httpx).
   - Providery: osobne klasy per provider.
   - ModelRegistry ma zostac cienka warstwa orkiestracji.

3) **Doprecyzowanie granic ModelManager vs ModelRegistry**
   - Zdefiniowac source-of-truth i dokumentacje odpowiedzialnosci.
   - Wydzielic wspolne utilsy (np. `model_utils.py`).

## Plan prac
1) Inwentaryzacja w `routes/models.py` (lista tras + domeny).
2) Wydzielenie wspolnych walidatorow Pydantic.
3) Podzial `routes/models.py` na sub-routery bez zmiany kontraktow.
4) Wydzielenie adapterow I/O w `model_registry.py`.
5) Refaktor providerow i integracja z nowymi adapterami.
6) Dokumentacja granic ModelManager/ModelRegistry.
7) Aktualizacja dokumentacji projektu (architektura + funkcjonalnosc).

## Ograniczenia
- Nie przebudowywac backendu w mikroserwisy.
- Nie usuwac endpointow ani nie zmieniac kontraktow API.
- Nie tworzyc nadmiernej liczby nowych plikow bez uzasadnienia.

## Kryteria wyjscia
- `routes/models.py` podzielone na sub-routery z zachowaniem sciezek API.
- `model_registry.py` uproszczony i pozbawiony bezposredniego I/O.
- Zdefiniowane granice odpowiedzialnosci ModelManager/ModelRegistry.

## Kryteria akceptacji
- Refaktor zrealizowany w kodzie (nie tylko raport).
- Brak regresji w testach.
- Dostosowane testy, jesli zmiany tego wymagaja.
- Aktualizacja dokumentacji projektu (funkcjonalnej i architektury).

## Format raportu (kontynuacja 76c)
Plik raportu: `docs/_done/076c_kontynuacja_refaktoru_backend_report.md`
- `Cel i zakres`
- `Zrealizowane refaktory` (z listą plikow)
- `Zmiany w API/kontraktach` (jesli brak, to jawnie: "brak")
- `Wpływ na testy`
- `Zmiany w dokumentacji`
