# PR — dedykowana zakładka OpenRouter i wiele podłączonych modeli

## Summary

Operator wyszukuje modele w osobnej zakładce OpenRouter i podłącza wybrane pozycje. Podłączenie udostępnia model w selektorze czatu; nie zmienia aktywnego modelu i nie uruchamia generacji. Można podłączyć kilka modeli, a następnie każdy niezależnie odłączyć. Modele zdalne pozostają ogólnym panelem statusu i połączeń dostawców.

Gałąź: codex/openrouter-chat-mvp. Repo: Venom. Biblioteka współdzielona 0.2.0 i repo orkiestracji nie wymagają zmiany kontraktu w tym zakresie. Realizacja i walidacja lokalna; publikacja PR/GitHub nie jest częścią tego polecenia.

## Scope

1. Backend katalogu: metadata-only pobieranie API OpenRouter, wyszukiwanie po nazwie/ID, profile czat/zadania/programowanie, kategorie, paginacja i ograniczony cache. Kategorie pobierane osobno, bo zaobserwowano HTTP 400 przy łączeniu category z zestawem filtrów modalności/narzędzi. Capabilities dodatkowo sprawdzane lokalnie.
2. Trwały rejestr wielu modeli: atomowe podłączanie/odłączanie, jawny wybrany endpoint i ceny, ważność cen per model. Import dotychczasowej listy operatora tylko przy braku rejestru. Pusty rejestr po odłączeniu ostatniego modelu pozostaje pusty.
3. UI: oddzielna zakładka OpenRouter, wyszukiwarka, lista wyników i podłączonych modeli, niezależne akcje i stany błędów. Modele zdalne zachowują połączenia/statusy dostawców, bez drugiego katalogu OpenRouter.
4. Czat: wszystkie dostępne podłączone modele pojawiają się w istniejącym selektorze. Zmiana listy innych modeli nie unieważnia konfiguracji wybranego modelu. Odłączenie aktywnego modelu blokuje jego nowe wywołania bez cichego fallbacku. Trwające wywołanie może się zakończyć.
5. Walidacja: testy granic API i registry, testy UI/selektora, katalog i grupy testów, typowanie, locale parity, make pr-fast oraz realny smoke panelu po jednym restarcie obecnego stosu.

## Podział pracy

- Worker backend: serwis katalogu i rejestru, trasy OpenRouter, integracja openrouter_runtime, testy Python.
- Worker UI: zakładka, wyszukiwarka, połączenia modeli, i18n PL/EN/DE, testy DOM/hook.
- Worker review czatu: zgodność selektora i wielomodelowego użycia, niezależny przegląd.
- Agent główny: plan PR, katalog testów, integracja, bramki, odbiór lokalnego stosu i raport.

## Kryteria odbioru

- Dwa podłączone modele są jednocześnie dostępne w selektorze czatu; podłączenie nie wybiera żadnego automatycznie.
- Odłączenie jednego zachowuje pozostałe. Odłączenie ostatniego nie odtwarza starej listy.
- Ceny jednego modelu nie są sztucznie odświeżane przez podłączenie innego. Nieznane ceny blokują podłączenie.
- Niedostępność dostawcy nie blokuje startu Venoma. Globalne wyłączenie API i istniejące limity budżetu nadal blokują nowe wywołania.
- Brak automatycznych generacji, wynajmu VAST, przełączania modelu lub dodatkowej instancji Venoma.

## Quality Gates

- [x] make pr-fast
- [x] katalog/grupy nowych testów i changed-lines coverage
- [x] targetowane testy Python, TypeScript/DOM, lint, i18n
- [x] lokalny smoke rzeczywistego panelu
- [ ] CI i Sonar po publikacji (nie wykonano w lokalnym etapie)

## Validation Report

Kod: f29738ca (backend), 599632d5 (UI), 10106407 (limit taryfy endpointu dla wszystkich modeli, zero dla :free).

- `make pr-fast`: PASS, 171,89 s; 1353 testy backendu i 230 interfejsu. Changed-lines coverage 93,61% przy progu 80%; progi 14 plików zaliczone.
- `scripts/qualify_openrouter_local.py`: PASS, 2,35 s; niezmieniony wheel 0.2.0 i zgodny receipt konsumenta Windows. Pakiet i repo orkiestracji bez zmian.
- `pytest tests/test_openrouter_model_catalog.py tests/test_openrouter_runtime.py`: 68 PASS.
- Testy nowej zakładki i selektora czatu: 11 PASS; pełny TypeScript, targeted ESLint, mypy trzech modułów oraz PL/EN/DE parity PASS.
- `make test-groups-sync test-catalog-check test-groups-check`: PASS. Rejestracja obejmuje wyłącznie nowy plik; wcześniejszy podział testów zachowany.
- Live smoke: wyszukiwanie, dwa bezpłatne modele, odłączenie jednego bez utraty drugiego i ponowne podłączenie PASS. Aktywny model nie zmienił się; bez generacji. API runtime options i rzeczywisty DOM potwierdzają nowy panel i dostępność OpenRouter.

Pełna bramka wykonana w izolacji sieci, GPU i danych z czystym ENV_FILE=/dev/null, bez operatorskiego profilu i sekretów. Lokalny runner poprawiono dla kanonicznego checkoutu: zapisywalne puste katalogi sandboxa oraz właściciel wygenerowanych raportów. Nie zmieniano progów ani zakresu bramek. Pełne prywatne dowody: docs_dev/openrouter-local-20261029/validation-connections.json, live-connections-check.json i pr-fast-connections.log.

## Risks / Limitations / Skips

Wyszukiwanie katalogu nie potwierdza jakości modelu ani skuteczności agenta kodowania. Metadane tools służą filtrowaniu kandydatów. Każdy podłączany model wymaga zgodnego przypiętego endpointu oraz znanych cen. Rollback kodu przez powrót na poprzedni commit/main; trwałego rejestru i rozliczeń nie usuwa się jako cache.
