# Porównanie lekkich modeli do utrzymania Venoma

Status: implementacja i pomiary w toku. Ten dokument nie stanowi raportu wyników.

## Kontrakt eksperymentu

Baza repozytorium: `1ef42d5a` (pełny SHA zapisywany w każdym przebiegu).
Sprzęt: RTX 3060 12 GB, jeden model naraz. Osobno czas ładowania i wykonania.
Katalog: `config/maintenance_comparison/models.json`. Każdy checkpoint ma pełny
SHA Hugging Face; rewizja szablonu jest przypięta do tego samego SHA.
Niepotwierdzone parsery, backendy, licencje i szkolenie pozostają jawnie
niezakwalifikowane. Brak pomiaru nigdy nie oznacza zera.

## Integracja

- Katalog operatora: `venom_core/core/model_registry_catalog.py` i registry hosta.
- Istniejący benchmark: `venom_core/services/benchmark_coding.py`, schematy i API.
- Wykonanie: `SkillManager.register_mcp_adapter` / `invoke_mcp_tool`; polityka
  uprawnień pozostaje włączona, argumenty podlegają walidacji.
- Zasoby: hostowy runtime admission i istniejący guard wyłączności benchmarków.
- UI: istniejący wybór modelu i ekran benchmarków; nowe komunikaty PL/EN/DE.
- Adapter normalizuje tylko poprawne wywołania. Bez drugiego modelu naprawiającego
  format. SERA operator wymaga osobnego potwierdzenia protokołu; CodeScout ma
  wyłącznie kontrakt lokalizacji. FunctionGemma może kończyć przez funkcję.

## Środowisko i ocena

Każda próba otrzymuje świeżą kopię ustalonego commita, osobne artefakty i
niezmienny manifest środowiska. Testy rozstrzygające i rozwiązania kontrolne
pozostają poza plikami edytowalnymi przez model. Osiem napraw musi mieć
potwierdzone kontrolne fail → pass oraz test regresji; dwa pozostałe przypadki
oceniają diagnozę i eskalację. Lokalizacja dopuszcza wiele poprawnych symboli,
ale wymaga istniejących plików, symboli i dowodów. Brak funkcjonalności musi
być odróżniany od nieznalezienia jej przez model.

Do 8 wywołań operatora, 12 lokalizacji i 20 napraw; do 3 cykli patch → test.
Powtórzone działanie ocenia się razem ze skrótem kodu i środowiska. Osobne
statusy: model zakończył, limit kroków/czasu/kontekstu, brak postępu, błąd
modelu, parsera, narzędzia lub infrastruktury, blokada konfiguracji, nie dotyczy.
Tryb badania flaky testu musi mieć osobny identyfikator konfiguracji.

## Macierz pomiarów

Operator: 70, diagnoza/naprawa: 50, lokalizacja: 60; razem 180 pozycji baseline.
SERA operator pozostaje w mianowniku planu nawet w razie blokady protokołu.
Maksymalnie dwóch finalistów na rolę, po dwa dodatkowe wykonania każdego
scenariusza: do 120 prób, łącznie do 300. N/A nie jest porażką. Blokady są
widoczne oddzielnie od jakości; skuteczność napraw liczy się względem ośmiu
naprawialnych przypadków, eskalacje oddzielnie. Finaliści wymagają wspólnego
spełnionego zestawu zadań i porównywalnych konfiguracji, nie tylko małej latencji.

## Artefakty i raport

Każdy przebieg: identyfikator, checkpoint/revizja, wersje backendu i parsera,
kwantyzacja, kontekst, budżety, seed, commit wejściowy, wiadomości, rzeczywiste
wyniki narzędzi (stdout/stderr/exit code), patch, weryfikacja, powtórzenia,
czas ładowania i zadania, RAM/VRAM peak oraz dostępne tokeny. Prywatne logi i
checkpointy nie trafiają do Git. Raport publikuje agregaty i zanonimizowane
przykłady; liczniki bezwzględne obok procentów, wersje konfiguracji oddzielnie.
Rekomendacje per rola: pilotaż, dostrajanie, węższa rola, odrzucenie badanej
konfiguracji. Negatywny wynik jest poprawnym rezultatem eksperymentu.

## Szkolenie

Pochodzenie i weryfikacja każdego przykładu są obowiązkowe. Podział train/val/test
według problemów i commitów; finalny zbiór oceny nie trafia do treningu.
Dostępność LoRA/QLoRA i pełnego treningu jest potwierdzana osobno dla checkpointu,
backendu, wersji i sprzętu. Techniczna możliwość nie oznacza kwalifikacji na
12 GB. Adapter jednego kandydata jest kolejnym eksperymentem po baseline,
z identycznym zestawem testowym, narzędziami i budżetem bazy.

## Kolejność realizacji i warunek wydania

1. Przypięty katalog ośmiu checkpointów i kwalifikacja protokołów/runtime.
2. 30 scenariuszy oraz niezależne sprawdziany i kontrolne fail → pass.
3. Wykonawca współdzielonych narzędzi, limity, replay i izolacja prób.
4. Integracja wyboru modeli operatora i testy jednostkowe/kontraktowe.
5. Rzeczywisty baseline 180 pozycji, jawne wyniki lub dowody blokad.
6. Finaliści/powtórzenia, raport, eksport do szkolenia, kwalifikacja CI.

PR pozostaje Draft do rzeczywistego wykonania porównania i rozliczenia całej
macierzy. Same testy jednostkowe lub dostępny checkpoint nie są wynikiem modelu.
