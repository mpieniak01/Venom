# Porównanie lekkich modeli do utrzymania Venoma

Status: implementacja i porównanie wykonane lokalnie. [Raport wyników 350 prób](reports/LIGHT_MODEL_MAINTENANCE_RESULTS_2026-11-01.md) rozdziela konfiguracje, blokady i ograniczenia pomiaru. Kolejne zmiany pozostają lokalne zgodnie z dyspozycją operatora.

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

## Historyczna macierz pierwszego eksperymentu

Operator: 70, diagnoza/naprawa: 50, lokalizacja: 60; razem 180 pozycji baseline.
SERA operator pozostaje w mianowniku planu nawet w razie blokady protokołu.
Maksymalnie dwóch finalistów na rolę, po dwa dodatkowe wykonania każdego
scenariusza: do 120 prób, łącznie do 300. N/A nie jest porażką. Blokady są
widoczne oddzielnie od jakości; skuteczność napraw liczy się względem ośmiu
naprawialnych przypadków, eskalacje oddzielnie. Finaliści wymagają wspólnego
spełnionego zestawu zadań i porównywalnych konfiguracji, nie tylko małej latencji.

## Artefakty i raport

Każdy przebieg: identyfikator, checkpoint/rewizja, wersje backendu i parsera,
kwantyzacja, kontekst, budżety, seed, commit wejściowy, wiadomości, rzeczywiste
wyniki narzędzi (stdout/stderr/exit code), patch, weryfikacja, powtórzenia,
czas ładowania i zadania, RAM/VRAM peak oraz dostępne tokeny. Prywatne logi i
checkpointy nie trafiają do Git. Raport zawiera agregaty i zanonimizowane
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

Macierz została rozliczona w raporcie A/B/C. Istniejący Draft PR nie został
zaktualizowany po dyspozycji pracy wyłącznie lokalnej. Publikacja jest osobnym
krokiem operatora. Same testy jednostkowe lub dostępny checkpoint nie są wynikiem modelu.

## Uruchomienie profilu i próby

Eksperyment jest ręczny i domyślnie wyłączony. Operator zatwierdził odrębny
profil z sandboxem; nie zmieniamy `.env.dev`. Włącz flagi z
`config/maintenance_comparison/profile.env.example` tylko w procesie eksperymentu.
Zatrzymaj poprzedni stos przez jego istniejący launcher i uruchom tę kopię kodu
przez `make start-dev ENV_FILE=/bezwzgledna/sciezka/.env.dev BACKEND_RELOAD=0`.
Zachowaj te same bezwzględne ścieżki danych operatora i jeden hostowy ledger
runtime admission. Nie uruchamiaj drugiego API ani serwera LLM.
Proces potrzebuje dostępu do lokalnego Dockera; nie montujemy socketu w kontenerze.

Obraz narzędzi buduje się z `config/maintenance_comparison/sandbox/Dockerfile`.
Wykonawca wymaga dokładnego lokalnego image ID zapisanego w `worker.py`; zmiana
obrazu tworzy nową konfigurację. Kontener ma wyłączoną sieć i GPU, niemodyfikowalny
root, ograniczenia CPU/RAM/PID oraz tylko kopię repozytorium jako zapisowalny mount.
Oracle trafia do innego kontenera dopiero po zamrożeniu pracy modelu.

Opcjonalne biblioteki inferencji: istniejące Torch/Transformers z venv Venoma;
`requirements-maintenance-comparison.txt` deklaruje dodatkowy bitsandbytes.
Można zainstalować dodatek przez `python -m pip install --no-deps --target
$HOME/.local/share/venom/maintenance-comparison/python -r requirements-maintenance-comparison.txt`.
Checkpointy trafiają do osobnego cache eksperymentu. Gated repo wymaga już
zaakceptowanej licencji i dostępu HF operatora; brak dostępu to blokada w raporcie.
Nie akceptujemy licencji automatycznie i nie zapisujemy sekretów w artefaktach.

Na `/benchmark` wybierz benchmark kodowania i zaznacz „Porównanie modeli
utrzymania”. Aktywny katalog czterech modeli pochodzi z
`GET /api/v1/benchmark/coding/maintenance/models`. Zaznacz modele i trzy role.
Przycisk Start używa istniejącego `POST /api/v1/benchmark/coding/start`.
W nowym trybie nie uruchamia się Ollama; host sprawdza brak lokalnego LLM,
przejmuje wyłączną dzierżawę GPU i uruchamia jeden proces pomiarowy.

Przykładowe body dla pełnego pomiaru (nazwy modeli zgodne z katalogiem):

```json
{
  "models": ["mini-coder-1.7b", "granite-4.2-3b", "gemma-4-e2b-it", "qwen3.5-9b"],
  "tasks": ["maintenance_operator", "maintenance_repair", "maintenance_localization"],
  "loop_task": "",
  "timeout": 180,
  "max_rounds": 3,
  "stop_on_failure": false
}
```

`options: {"maintenance_phase":"qualification"}` uruchamia wyłącznie techniczny
obieg narzędzie → rzeczywisty wynik → kolejna odpowiedź. Na pierwszej turze tej
kwalifikacji dostępny jest tylko Terminal. Kwalifikacja nie wchodzi do baseline.
`options: {"maintenance_phase":"flaky_diagnostic"}` z samą rolą operatora to
odrębny, jawny test trzech powtórzeń kontrolowanego `test_visible.py` bez edycji.
Znosi wyłącznie zatrzymanie po trzech identycznych operacjach; limity kroków i
czasu pozostają. Nie wchodzi do rankingu i nie dowodzi stabilności innych testów.

LFM2 może zakończyć natywną odpowiedzią tekstową po narzędziu. Zapisujemy ją jako
`native_text`, bez wymyślania statusu i argumentów funkcji Finish; kryteria
operatorskie sprawdzają rzeczywiste operacje oraz jawne treści odpowiedzi.
Pozostałe modele zachowują swoje koperty funkcji lub sentinel Bash.
Precyzja BF16 odpowiada przypiętym konfiguracjom; większe modele używają NF4.
Niepoprawne wartości logitów są błędem inferencji, nie porażką jakości modelu.

Artefakty są w `data/benchmarks/coding/<run_id>/`: plan, stan oczekujących prób,
środowisko, konfiguracja ze skrótami źródeł, surowe przebiegi, patch, testy,
`REPORT.md`, `finalists.json` i `training-records.json`. Odtworzenie wymaga tego
samego commita wejściowego, checkpointów, image ID, kodu wykonawcy i środowiska.
Kolejne uruchomienie zawsze tworzy świeże kopie i nowy identyfikator przebiegu.
Zmiana budżetu, źródeł, wyboru ról/modeli lub backendu zmienia identyfikator
konfiguracji. Seed 17 pozostaje taki sam także w powtórzeniach.

Limit trzech cykli naprawa → test dotyczy obserwowanych wywołań narzędzi;
licznik kroków liczy rzeczywiste wywołania, także Finish. Bash może zawierać
złożone polecenie; nie deklarujemy pełnego śledzenia każdego syscalla.
VRAM to peak alokatora Torch, RAM to RSS procesu modelu co 50 ms, bez innych
procesów i kontenera. Brak danych jest jawny. Te same ograniczenia obowiązują
wszystkich finalistów. Surowe logi i dane szkoleniowe nie trafiają do Git.

Dodanie modelu wymaga wpisu z dokładnym HF SHA, licencją, rolami, natywnym
parserem, szablonem i parametrami, oraz aktualizacji walidacji liczby kandydatów.
Dodanie scenariusza wymaga niezależnego oracle/oczekiwanych lokalizacji i dowodu,
że sprawdzian odrzuca usterkę. Nie wolno przenosić przypadków oceny do train/val.

Profil kontenera uruchamia syntetyczne testy z
`PYTEST_ADDOPTS="-o addopts= -o filterwarnings= --noconftest"`, aby nie dziedziczyć
pluginów i bootstrapu pełnego stosu Venoma. Źródłowy `pytest.ini` pozostaje
niezmieniony. To środowisko przypadków porównawczych, nie pełna regresja Venoma;
wszystkie obowiązkowe bramki PR uruchamiamy osobno w venv projektu.

Adapter Bash akceptuje natywne zakończenie mini-swe-agent przez sam sentinel
`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`, bez dopisywania wywołania Finish
ani zgadywania statusu. Zachowuje oba jawne znaczniki bloku Bash; dodatkowy raport
JSON jest wymagany dla uporządkowanych lokalizacji. Obserwacje mają natywną
postać returncode/output. Zasady scaffolda: [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/config/default.yaml).
Widok odpowiedzi narzędzia dla każdego modelu jest jawnie skracany przy
przekroczeniu 10 000 znaków; rzeczywiste stdout/stderr pozostają w artefakcie.
Nie zmienia to wyników narzędzia ani nie naprawia odpowiedzi modelu.

CodeScout zachowuje natywne nazwy `terminal`/`localization_finish` i argument
`locations` z `file`, opcjonalnym `class_name` i `function_name` zgodnie z
[przypiętym kontraktem OpenHands](https://github.com/OpenHands/codescout/blob/f25decf9f7edde4fd7f4427e71a05c18aaf27eba/src/tools/localization_finish.py).
Nie dopisujemy do jego wywołania statusu, podsumowania ani dowodów. Ocena
lokalizacji sprawdza wskazane symbole i dowody w rzeczywistym stdout narzędzi.
Puste lokalizacje w zadaniu braku funkcji wymagają również negatywnego wyszukania.

Weryfikator montuje proponowany kod i kopię testów tylko do odczytu. Zaufany
etap przygotowania zapisuje oracle jako root z uprawnieniami 0444 w katalogu
z bitem sticky; oceniany kod nadal wykonuje się jako UID 1000 i nie może go
zmienić ani usunąć. Katalog artefaktów ma 0700, surowe pliki JSON mają 0600.

Grupa problemu (`venom-maintenance-v1:<case_id>`) jest stała również między
commitami: zmiana samego commita nie pozwala przenieść wariantu zadania z test
do treningu. Commit i identyfikator konfiguracji zapisujemy osobno.
Błędy backendu/generacji lub transportu narzędzia są blokadami infrastruktury,
a wcześniejsze rzeczywiste wywołania pozostają w śladzie. Przy niepotwierdzonym
wykonaniu nie dopisujemy kodu zakończenia; częściowe artefakty pozostają jawnie
niezweryfikowane. Zmieniona obserwacja narzędzia nie jest identycznym powtórzeniem.


## Lokalne rozszerzenie: Gemma 4 i Qwen3.5

Na polecenie operatora kolejne zmiany i wyniki pozostają lokalne; nie aktualizujemy
istniejącego Draft PR. Dodatkowe profile w `additional_models.json` zachowują
oryginalny katalog ośmiu modeli. Gemma 4 E2B i Qwen3.5-9B wykonują po tych samych
30 przypadkach, na tym samym commicie wejściowym i z budżetami 8/20/12 wywołań,
8192 tokenów kontekstu, 1024 generacji, 45 s na generację i 180 s na zadanie.

W API dodaj `options: {"maintenance_phase": "baseline"}` i wybierz
`gemma-4-e2b-it,qwen3.5-9b` oraz trzy role. Tryb baseline wykonuje 60 pozycji;
nie uruchamia automatycznych powtórzeń finalistów. Te wyniki są wstępne.
Gemma 4 korzysta z natywnych znaczników i odpowiedzi narzędzi nazwanych według
przypiętego szablonu Google. Qwen3.5 używa natywnego XML i nieaktywnego myślenia.
Parametry próbkowania są zapisane w profilach; presence penalty dotyczy tokenów
wygenerowanych w bieżącej odpowiedzi, bez prefiksu wejściowego.

Pierwszy przebieg CodeScout ujawnił błąd infrastruktury: po odczycie całego kodu
limit wyjścia zbiegał się z timeoutem API Dockera i wyścigiem pause/stop.
Zablokowana próba zachowuje niezweryfikowany ślad. Po poprawce strumień jest
zamykany przed zabiciem kontenera, stan spoczynku jest ponownie potwierdzany,
a niedostępny kod wyjścia pozostaje brakiem danych. Osobny pełny przebieg roli
CodeScout zakończył 30 ocenionych prób bez blokad infrastruktury. Wyniki A/B
pozostają oddzielne; historyczna blokada nie jest usuwana.

Kwalifikacja Qwen3.5 ujawniła brak zatrzymania na `<|im_end|>`: checkpoint
ma w konfiguracji tekstowej wyłącznie `<|endoftext|>`, a nie ma osobnego
`generation_config.json`. Profil jawnie ustawia oba natywne tokeny EOS
(248044 i 248046). Zapobiega to generowaniu kolejnych fikcyjnych tur użytkownika
i narzędzi; nie dopisuje ani nie poprawia argumentów modelu. Nieudaną próbę
techniczną zachowujemy oddzielnie od właściwego baseline.

Przykład odtworzenia nowego baseline przez istniejące API:

```json
{
  "models": ["gemma-4-e2b-it", "qwen3.5-9b"],
  "tasks": ["maintenance_operator", "maintenance_repair", "maintenance_localization"],
  "loop_task": "",
  "first_sieve_task": "",
  "timeout": 180,
  "max_rounds": 3,
  "stop_on_failure": false,
  "options": {"maintenance_phase": "baseline"}
}
```

Historyczny wybór wszystkich dziesięciu modeli w trybie comparison planował 240 pozycji
baseline i do 120 powtórzeń; limit wynosi wtedy 360. Pierwotny katalog ośmiu
zachowuje plan 180/do 300. W przeprowadzonym rozszerzeniu obu nowych modeli
użyto wyłącznie baseline, bez automatycznych powtórzeń.

Pole `peak_vram_bytes` zachowuje licznik `torch.cuda.max_memory_reserved`:
rezerwację alokatora, nie szczyt fizycznego dedicated/shared VRAM. W raporcie
nazywamy go rezerwacją CUDA; niewykonany pomiar sterownika oznacza brak danych.
Qwen osiągnął 13,18 GiB rezerwacji na karcie 12 GiB, więc profil GPU-only nie
jest potwierdzony. Backend Qwena używał referencyjnych operacji PyTorch bez
opcjonalnych szybkich kerneli; kwalifikacja szybszego profilu jest osobnym pomiarem.

Przy przygotowywaniu danych treningowych z kodu repo wyklucz definicje/gold
tego eksperymentu, odpowiadające im testy i wszystkie surowe rekordy held-out.
Zmiana commita nie zmienia grupy problemu i nie uprawnia do przeniesienia testu
do train/validation. W tym porównaniu nie wykonywano dostrajania.


## Aktywne modele po decyzji operatora 2026-11-01


`active_models.json` ogranicza nowe uruchomienia do mini-coder-1.7b,
Granite 4.2 3B, Gemma 4 E2B IT i Qwen3.5-9B. Panel i walidacja uruchomienia
korzystają z tej samej listy. Pozostałych sześciu kandydatów nie można wybrać;
ich wagi usunięto z prywatnego cache eksperymentu. Historyczne katalogi ośmiu
modeli i rozszerzenia oraz raporty i przebiegi pozostają zachowane.
Aktywne cztery modele mają po trzy role: 120 prób baseline, do 240 z powtórzeniami.
Odtworzenie wycofanego profilu wymaga świadomego przywrócenia konfiguracji i wag.

Profil `retained-models-rtx3060-v2` jawnie wybiera SDPA i cache generacji.
Mini-coder zachowuje BF16, trzy większe modele NF4 z obliczeniami BF16.
Qwen dodatkowo korzysta z `kernels==0.16.2`, `einops==0.8.2` oraz przypiętych
pełnymi SHA kerneli społeczności Hugging Face: mamba-ssm dla causal-conv1d,
fla dla obu operacji DeltaNet. Mapowanie nie dziedziczy nieprzypiętych domyślnych
kerneli. Dopasowujemy nazwy klas warstw API kerneli, nie modyfikujemy odpowiedzi
modelu. Oba natywne EOS Qwena i parametry generacji pozostają zachowane.

Dodatki Python i cache kerneli są prywatne dla eksperymentu; główny venv i
profil `.env.dev` pozostają bez zmian. Opcjonalne wymagania są w
`requirements-maintenance-comparison.txt`; nie należy aktualizować istniejącego
PyTorcha przy instalowaniu dodatku. Wymagana jest zgodność binarna kerneli z
Torch/CUDA/architekturą GPU. Brak zgodnej wersji jest blokadą infrastruktury.
Kwalifikację uruchamia operator w trybie `qualification`, przed nowym pomiarem.
Nie jest ona automatycznym Test Zero ani częścią zwykłych bramek testowych.

Artefakt zapisuje rzeczywiste implementacje attention i forward kerneli,
rewizje źródeł i wersję pakietu. Nowe pomiary zapisują oddzielnie szczyt
alokowanych i rezerwowanych bajtów CUDA; `peak_vram_bytes` pozostaje kompatybilnym
aliasem rezerwacji. Żadne z tych pól nie mierzy fizycznego dedicated/shared VRAM.
Nowy profil ma odrębny identyfikator; wyniki starych 350 prób nie są nadpisywane.
