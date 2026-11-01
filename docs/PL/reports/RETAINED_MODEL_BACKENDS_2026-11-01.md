# Cztery pozostawione modele i kwalifikacja backendów — 2026-11-01

Zmiany wykonano lokalnie na `feat/light-model-maintenance-comparison`.
Publikacja na GitHub pozostaje wstrzymana zgodnie z decyzją operatora.
Historyczny raport 350 prób i surowe przebiegi nie zostały zmienione.

## Usunięcie wag

Z prywatnego cache eksperymentu usunięto mini-coder-4b, Granite 4.2 8B,
SERA-8B, FunctionGemma 270M, LFM2-1.2B-Tool i CodeScout-4B.
Usunięto ich katalogi i osierocone współdzielone bloby. Przed usunięciem
zweryfikowano katalog docelowy, brak procesu eksperymentu oraz referencje
pozostawionych modeli. Pliki używane przez te modele pozostały zachowane.

Odzyskane miejsce według `du -s -B1`: **53003808768 bajtów (53,00 GB)**.
Cache wag zmalał z 93,40 GB do 40,39 GB. To wartość usuniętych wag;
nowe biblioteki i cache kerneli są rozliczane oddzielnie. Pozostałe instalacje
Venoma i modele głosu, wizji oraz embeddingów były poza zakresem usunięcia.
Prywatny manifest kontroli: `test-results/model-retirement-2026-11-01.json`.

## Aktywne profile

| Model | Precyzja | Attention i cache | Protokół |
|---|---|---|---|
| mini-coder-1.7b | BF16 | SDPA, cache włączony | natywny Bash mini-swe-agent |
| Granite 4.2 3B | NF4 / obliczenia BF16 | SDPA, cache włączony | natywne XML narzędzi |
| Gemma 4 E2B IT | NF4 / obliczenia BF16 | SDPA, cache włączony | natywne znaczniki Gemma 4 i nazwane odpowiedzi narzędzi |
| Qwen3.5-9B | NF4 / obliczenia BF16 | SDPA, cache, szybkie kernele DeltaNet i causal-conv1d | natywne XML, oba tokeny EOS |

Panel i walidacja startu korzystają z `active_models.json`. Wycofane modele
są odrzucane przed utworzeniem procesu/pobraniem wag. Oryginalny katalog i
rozszerzenie zachowują metadane potrzebne do interpretacji historii.

Qwen korzysta z Torch 2.13.0+cu130, Transformers 5.17.0, bitsandbytes 0.50.2,
kernels 0.16.2, kernels-data 0.16.2 oraz einops 0.8.2 na RTX 3060 12 GB.
Biblioteki dodano wyłącznie w prywatnym komponencie eksperymentu; bazowego
venv, domyślnego `.env.dev` i systemowego CUDA nie aktualizowano.

Przypięte źródła kerneli:

- mamba-ssm: `da82c7927c6caac3d8024f98a350131ffec6be85` — klasy obu operacji causal-conv1d;
- fla: `4d57fd54fa5d5c15f7438de2c7e40f603b824dd8` — klasy chunk/recurrent gated delta rule.

Rewizje zawierają warianty zgodne z Torch 2.13/CUDA 13.0 i GPU.
Mapowanie nie dziedziczy innych, nieprzypiętych kerneli. Natywne nazwy klas
warstw różnią się od eksportów funkcji; konfigurację sprawdzono na rzeczywistym
modelu. Artefakt zawiera forward `_mamba_ssm_cuda_e632c06.layers.*` i
`_fla_cuda_fe2bb66.layers.*` dla wszystkich czterech operacji.
Dokumentacja upstream: [ładowanie kerneli Transformers](https://huggingface.co/docs/transformers/kernel_doc/loading_kernels),
[karta Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B),
[karta mini-coder](https://huggingface.co/ricdomolm/mini-coder-1.7b).

## Rzeczywista kwalifikacja

Przebieg `0245546a-d226-49d7-ac30-4638daf5a79d` wykonał po jednym technicznym
zadaniu przez istniejące API, hostową dzierżawę GPU i sandbox Dockera.
Celem był obieg: polecenie `printf MAINTENANCE_PROTOCOL_OK`, rzeczywisty wynik,
kolejna odpowiedź i zakończenie. Jedna instancja modelu naraz.

| Model | Załadowanie i wykonanie narzędzi | Pełne wykonanie zadania kwalifikacyjnego |
|---|---|---|
| mini-coder-1.7b | poprawne | nie: ignoruje zadanie, wykonuje 8 poleceń, zatrzymany limitem kroków |
| Granite 4.2 3B | poprawne | zaliczone |
| Gemma 4 E2B IT | poprawne | zaliczone |
| Qwen3.5-9B | poprawne; potwierdzone cztery szybkie kernele | zaliczone |

Mini-coder pozostaje zgodnie z decyzją operatora. Ten negatywny wynik dotyczy
wykonania instrukcji przez model i nie jest przedstawiany jako zaliczona
kwalifikacja. Samo poprawne załadowanie nie dowodzi skuteczności agenta.

## Powtórny pomiar Qwena: wszystkie 30 scenariuszy

Nowy przebieg: `0e084ca6-4987-48c5-81ec-037853e55fd1`, konfiguracja
`5b509b7abd40ebe70d4185302c62acbe2ae00dc6158862122d971e7cf2d43af4`.
Odniesienie: Qwen z przebiegu `24c7e4f4-55fd-422e-84d9-5a11c45eec6b`.
Ten sam commit wejściowy, 30 scenariuszy, rewizja checkpointu, natywne EOS,
parametry próbkowania i budżety. Po jednej próbie przypadku w każdym profilu.
Wszystkie 30 pozycji wykonano i oceniono; **0 blokad infrastruktury**.
Status całego przebiegu `completed_with_failures` zachowuje niezaliczone zadania.

| Rola | Poprzednio | Nowy profil | Średnia całej próby wcześniej [s] | Średnia teraz [s] |
|---|---:|---:|---:|---:|
| Operator | 8/10 | 8/10 | 27.50 | 17.23 |
| Naprawa | 3/8 | 5/8 | 125.51 | 72.59 |
| Lokalizacja | 1/10 | 1/10 | 84.49 | 62.89 |

Naprawy mają mianownik 8. Dwie diagnozy/eskalacje oceniamy osobno:
**0/2 wcześniej i 0/2 teraz**. Średnia czasu sekcji napraw obejmuje wszystkie
10 przypadków, także te dwie diagnozy. Czas próby obejmuje przygotowanie,
pracę modelu i narzędzi oraz niezależną weryfikację; nie zawiera ładowania modelu.
Historyczna tabela raportu 350 prób używa median, nie średnich.

Suma czasów 30 prób: **2375.02 s → 1527.10 s**, czyli **35.7% mniej** (1.56× względem czasu poprzedniego profilu).

Mediany całej próby, dla odróżnienia od powyższych średnich:

| Rola | Poprzednio [s] | Teraz [s] |
|---|---:|---:|
| operator | 14.82 | 15.57 |
| repair | 117.77 | 77.88 |
| localization | 89.37 | 59.31 |

Ładowanie Qwena: **40,26 s → 42,68 s**. Szybkie kernele poprawiają wykonanie;
nie skróciły ładowania/kwantyzacji checkpointu. Monotoniczny czas pracy nowego
wykonawcy, z ładowaniem i przygotowaniem: **1582.66 s (26.38 min)**.

To porównanie kompletnych profili wykonania, nie izolowany mikropomiar kernela.
Floating point zmienia trajektorie, liczbę operacji i tokenów mimo tego samego
seedu. Przed nowym pomiarem oficjalny endpoint zwolnił zasoby głosu, wizji i
embeddingów; nie zmieniono wag ani konfiguracji ich instalacji. Nie prowadzono
równolegle ciężkich testów. Nie przypisujemy całej różnicy samym kernelom ani
nie przedstawiamy pojedynczego przebiegu jako statystycznie potwierdzonej poprawy.

## Pamięć

Szczyt rezerwacji CUDA: **13.18 GiB → 9.39 GiB**.
Szczyt rzeczywistych alokacji Torch w nowym profilu: **8.62 GiB**; poprzednio tego pola nie utrwalano.

Odczyty sterownika całego GPU: **701 próbek**, maksimum **11393 MiB**
przy 12288 MiB pamięci karty. Próbkowanie co około 2 s rozpoczęto po pierwszym
przypadku; nie obejmuje ładowania i nie jest pomiarem per proces/model.
Rezerwacja i alokacja Torch nie są pomiarem fizycznej pamięci dedicated/shared.
Odczyty nie dowodzą braku migracji stron WDDM do RAM. Nie deklarujemy na ich
podstawie pełnego potwierdzenia profilu GPU-only.

## Wnioski

- Zachowane cztery modele są dostępne w aktywnym katalogu; sześć wycofanych nie pobiera się przez API.
- Qwen ma potwierdzony pełny obieg narzędzi i użycie szybkich kerneli, mniejszą rezerwację oraz krótszą sumę czasów prób.
- Naprawy poprawiły się z 3/8 do 5/8 w pojedynczym przebiegu; lokalizacja i eskalacja nadal wymagają poprawy.
- Granite i Gemma zaliczyły techniczną kwalifikację. Ich całego baseline nie powtarzano w tej zmianie.
- Mini-coder wymaga nadzoru: narzędzia działają, ale nie zaliczył instrukcji kwalifikacyjnej. Pozostaje na żądanie operatora.
- Wszystkie nowe rekordy pozostają held-out (`split=test`, `training_allowed=false`); nie wykonywano treningu.

## Weryfikacja kodu

Wszystkie wymagane kontrole zakończone:

- Testy komponentu: **149 PASS**; Ruff: PASS; mypy: PASS (16 plików źródłowych).
- `make test-ci-lite`: **898 PASS**, 83,69 s wraz z uruchomieniem celu make.
- `make test-catalog-check` i `make test-groups-check`: PASS.
- `make pr-fast`: **PASS, 206,69 s**; 1300 testów backendu, frontendowe lint/testy jednostkowe i 354 testy komponentowe oraz lint/typecheck i 12 testów Studio.
- Pokrycie zmienionych linii: **87,34%**, wymagane 80%; progi wszystkich 14 plików spełnione.
- `make check-new-code-coverage-diagnostics`: PASS.
- Łączny czas sekwencji katalog/grupy + ci-lite + pr-fast + diagnostyka: **290,62 s (4,84 min)**.
- Końcowy smoke API i panelu: HTTP 200, cztery aktywne modele, runtime available, brak aktywnego procesu eksperymentu.
- Rzeczywisty POST z wycofanym `mini-coder-4b`: **HTTP 400 `unknown_maintenance_model`** przed pobraniem/wczytaniem modelu.
- Odczyt cache: dokładnie cztery pozostawione repozytoria, zero ostrzeżeń skanera HF.

Prywatne dowody: `test-results/retained-model-gate-result.json`,
`retained-model-targeted.log`, `retained-pr-fast.log`,
`retained-backend-comparison-summary.json` i `qwen-accelerated-gpu-samples.json`.
Po zaliczeniu bramek uzupełniono wyłącznie ten raport; kod wykonawczy pozostał ten sam.
Stos działa jako jawny wariant Venom na 3300/8800, z prawidłową główną grupą
właściciela i dostępem sandboxa przez grupę dodatkową docker. Nie uruchamiano
drugiego stosu, zewnętrznej generacji, Test Zero ani operacji VAST.
Żadnego kodu ani raportów nie wysłano na GitHub.
