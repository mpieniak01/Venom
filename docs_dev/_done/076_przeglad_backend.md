# 76: Przeglad techniczny backendu

## Cel
- Znalezc nieoptymalny, nadmiernie skomplikowany lub niewydajny kod.
- Wykryc zbyt duze, monolityczne pliki oraz martwy kod.
- Wskazac kandydatow do refaktoru i uproszczen.
- Zrealizowac refaktor w tym samym PR i udokumentowac zmiany.

## Zakres
- Backend/serwisy: `venom_core`, `venom_spore`.

## Wstepna analiza (szybki rekonesans)
### Duze/monolityczne pliki (kandydaci do podzialu)
- `venom_core/core/orchestrator.py` (~1846 linii).
- `venom_core/api/routes/models.py` (~1329 linii).
- `venom_core/core/model_registry.py` (~1114 linii).
- `venom_core/core/model_manager.py` (~945 linii).
- `venom_core/main.py` (~885 linii).
- `venom_core/services/runtime_controller.py` (~735 linii).

### Wstepne hipotezy ryzyk
- Rozmiar plikow sugeruje mieszanie wielu odpowiedzialnosci w jednym module.
- Mozliwa duplikacja logiki miedzy warstwami API, managerami i orkiestrowaniem.
- Potencjalny martwy kod w trasach i obsludze modeli (brak czyszczenia starych sciezek).

### Dodatkowe obserwacje po spojrzeniu w kod
- `venom_core/core/orchestrator.py` laczy orkiestracje zadan, kolejke, stream callbacks, tracer, meta-learning (lessons) i rozne flowy (council/forge/healing/issue). To "god object" z wysoka spolnoscia.
- `venom_core/core/model_registry.py` miesza odpowiedzialnosci: HTTP (httpx), IO plikow, subprocess, parsowanie metadanych i operacje na modelach w jednym module.
- `venom_core/core/model_manager.py` rozwija osobna logike wersjonowania i zasobow modeli, co czesciowo dubluje obszar `model_registry`.
- `venom_core/api/routes/models.py` zawiera duzo modeli Pydantic i walidacji (powtarzajace sie regexy i zasady), a takze rozne domeny (registry, instalacje, tlumaczenia, usage) w jednym pliku.
- `venom_core/services/runtime_controller.py` obsluguje procesy i logi w jednym miejscu; sporo kodu systemowego (PID, logi, psutil) w klasie aplikacyjnej.

## Wskazowki dla wykonawcy
- Rozdziel odpowiedzialnosci w `orchestrator.py` na mniejsze serwisy (kolejka, routing/flowy, streaming, tracer, meta-learning) z czytelnym API.
- Ujednolic zarzadzanie modelami: okresl, co jest zrodlem prawdy (registry vs manager), i wyciagnij wspolne utilsy do osobnych modulow.
- Podziel `routes/models.py` na mniejsze routery (np. registry, instalacje/aktywizacja, metryki/usage, tlumaczenia) i wyciagnij walidacje do wspolnych helperow.
- Rozwaz wydzielenie warstwy IO (subprocess, pliki) z `model_registry.py` do adapterow, by ulatwic testy i mockowanie.
- Dla `runtime_controller.py` rozdziel logike odczytu logow/PID-ow od operacji start/stop, a odczyty procesow ogranicz przez cache lub limity.

## Co nie jest celem
- Nie przebudowywac backendu w mikroserwisy ani nie wprowadzac nowych warstw bez wyraznej potrzeby.
- Nie przenosic logiki miedzy `venom_core` i `venom_spore` bez uzasadnienia w raporcie.
- Nie usuwac istniejacych endpointow lub zachowan bez potwierdzenia zgodnosci z legacy fallback.

## Odniesienia do dokumentacji i ograniczenia
- Architektura uruchomieniowa jest opisana w `docs/DEPLOYMENT_NEXT.md` (FastAPI jako API/SSE/WS + niezalezne `web-next`). Refaktory backendu nie powinny mieszac warstw ani przenosic logiki UI do API.
- Legacy UI (`web/`) pozostaje fallbackiem zgodnie z `docs/DASHBOARD_GUIDE.md`. Nie usuwac endpointow lub zachowan bez potwierdzenia zgodnosci z fallbackiem.
- W razie watpliwosci co do podzialu odpowiedzialnosci, odwolac sie do `docs/DEPLOYMENT_NEXT.md` i `docs/DASHBOARD_GUIDE.md` zamiast wprowadzac dowolne warianty architektury.
- Nie jest intencja tworzenie rozbudowanej siatki nowych plikow i nadmiernie skomplikowanej architektury; podzial ma zwiekszac czytelnosc i ulatwiac rozwoj, a nie mnozyc byty.

## Plan przegladu
1) Mapowanie odpowiedzialnosci w najwiekszych plikach.
2) Identyfikacja powtorzen i nadmiarowych abstrakcji.
3) Szukanie martwego kodu i rzadko uzywanych sciezek.
4) Lista rekomendacji: podzial plikow, uproszczenia przeplywow, usuniecie dead code.

## Kryteria wyjscia
- Lista plikow o wysokim priorytecie refaktoru.
- Konkretne przyklady zbednej zlozonosci lub duplikacji.
- Rekomendacje co uproscic i jak podzielic moduly.

## Kryteria akceptacji
- Raport refaktoryzacji z opisem zmian i uzasadnieniem decyzji.
- Brak regresow w testach po wprowadzeniu zmian.
- Ewentualne dostosowanie testow do nowej logiki plikow lub zoptymalizowanej funkcjonalnosci.
- Aktualizacja dokumentacji projektu (funkcjonalnej i architektury), jesli zmiany tego wymagaja.
- Zmiany w kodzie zostaly wprowadzone (nie tylko raport).

## Format raportu (backend)
Plik raportu: `docs/_done/077_przeglad_backend_report.md`
- `Cel i zakres` (zawiera obszary objete przegladem).
- `Najwazniejsze ryzyka` (lista z priorytetem i wskazaniem plikow).
- `Znaleziska` (problem -> lokalizacja -> uzasadnienie -> rekomendacja).
- `Propozycje refaktoru` (zakres, minimalny podzial, szacowany wplyw).
- `Wpływ na testy` (co uruchomic, co dostosowac).
- `Zmiany w dokumentacji` (jezeli wymagane, z wskazaniem plikow).
