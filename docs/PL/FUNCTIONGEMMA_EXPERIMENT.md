# FunctionGemma 270M: lokalny eksperyment narzedziowy

Status: pelny SFT i lokalny import Ollama zakonczone 2026-11-03.
Model jest dostepny do recznych prob; automatyczny dispatcher pozostaje warunkowy.
Porownawcza ocena jakosci jest oddzielna od sukcesu treningu i GPU smoke.
Galaz wydania: `codex/functiongemma-tool-training`.

Model `google/functiongemma-270m-it` jest przypiety do rewizji
`39eccb091651513a5dfb56892d3714c1b5b8276c`. Nie korzysta z encodera Gemma4.
Natywna serializacja korzysta z chat_template tokenizera, roli developer i promptu
aktywacyjnego Google. Parser zwraca propozycje; nie wykonuje narzedzi.

## Przygotowanie

W aktywnym venv Venoma:

```bash
python scripts/functiongemma.py plan --samples 1408
python scripts/functiongemma.py export --train data/training/gemma-g05-v2-20261103-ready/train.jsonl --validation data/training/gemma-g05-v2-20261103-ready/validation.jsonl --output data/training/functiongemma-decisions-20261103/release.json
```

Eksport zachowuje zrodla i lineage oraz grupy PL/EN w jednym podziale. Wybiera
decyzje FileSkill, zachowuje rzeczywiste poprzednie wyniki i odrzuca decyzje
z prefiksem spoza tego zakresu. Diagnostyczny holdout G05 nie jest niezaleznym
testem koncowym. Nie dodawac go do treningu.

Polecenie `prepare` przyjmuje te same pliki `--train`, `--validation`, a takze
`--snapshot`, nowy katalog `--output` i `--context {1024,2048}` (domyslnie 1024).
Dla obecnego zestawu G05 uzyj `prepare --context 2048` z pozostalymi argumentami.
Snapshot musi byc lokalnie dostepnym
katalogiem przypietej rewizji HF; polecenie niczego nie pobiera. Powstaja
release.json, encoded.json, full-recipe.json, lora-recipe.json i preparation.json.
Maska obejmuje tylko ostatnia wybrana odpowiedz asystenta i natywny koniec tury.
Przekroczenie kontekstu jest bledem, bez obcinania i bez packingu.

## Trening i smoke

F1: pelny SFT BF16. L1: LoRA BF16 r8/alpha16/dropout0.05 na q/k/v/o.
Wspolne: kontekst 1024, batch 4, akumulacja 4. Dla kontekstu 2048 wykonaj
`prepare --context 2048` z nowym katalogiem `--output`; eksport pozostaje aktualny.
LR5e-5, AdamW wd0.01, linear, warmup5%, seed42, maksymalnie3 epoki.
Dla1408 decyzji:88 aktualizacji/epoke,264 ogolem. Ostatnia niepelna akumulacja
jest zachowana przez Trainer. Rozproszony WORLD_SIZE>1 jest odrzucany.
Walidacja loss co okolo pół epoki, zapis po kazdej epoce. Kod nie wybiera
najlepszego checkpointu na podstawie loss; wybor wymaga osobnej oceny wywolan.

Worker wymaga osobnego srodowiska Python3.14.8 zgodnego z istniejacym lockiem
`requirements/locks/granite-operator-training-linux-py314.txt`
(torch2.13.0/transformers5.17.0/peft0.21.2). Ten lock jest baza zaleznosci;
zgodnosc FunctionGemma z GPU nadal wymaga rzeczywistego smoke.
Nie instalowac tych zaleznosci do venv aplikacji.

`python scripts/functiongemma.py run REQUEST.json` przyjmuje:

- recipe: pelny obiekt z full-recipe.json albo lora-recipe.json;
- stage: smoke, train albo resume;
- snapshot, encoded_release, output: jawne sciezki; output musi byc nowy;
- run_id: identyfikator proby; gpu_authorized: true;
- qualification: metrics.json udanego smoke przy train/resume;
- checkpoint: zapieczetowany checkpoint przy resume.

Proces musi miec HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1 oraz
VENOM_GRANITE_ADMISSION_DB wskazujace istniejacy wspolny rejestr hosta.
Nie tworzyc prywatnego rejestru, aby obejsc aktywny model.
Worker korzysta ze wspolnej RuntimeAdmission, nie uruchamia ani nie usuwa hosta,
nie zwalnia innych modeli i odrzuca brak CUDA/BF16 oraz offload CPU/dysk.

Smoke wykonuje jedna aktualizacje, zapis, reload i wznowienie do drugiej.
Sprawdza zmiane wag, identyczne logity po reload oraz stan optimizer/scheduler/RNG.
Smoke ma warmup0, aby pierwszy krok faktycznie zmienial wagi.
Dowod jest zwiazany z recepta, hostem, kodowaniem, snapshotem i zaleznosciami;
kazda zmiana wymaga nowej kwalifikacji. Artefakty i metryki pozostaja prywatne.
Raport obejmuje czas, peakVRAM/RSS i wielkosc checkpointu. Nie jest dowodem
jakosci narzedziowej ani zgoda na aktywacje.

## Porownanie i kolejne warunki
### Standard zdalnej oceny i wynik pierwszego pelnego SFT

Zdalna ocena korzysta z **8 rownoleglych workerow**, po 2 watki CPU na worker.
Przed kazdym dlugim przebiegiem obowiazuje **pilot -> przeglad surowych
wynikow -> pelny zestaw**. Dla oceny narzedziowej pilot obejmuje co najmniej
16 reprezentatywnych przypadkow na wariant: PL/EN, kazde narzedzie, brak
wywolania, escapowanie i dlugi kontekst. Sprawdz rzeczywiste zakonczenie
generacji oraz zgodnosc oceny z odpowiedzia; sam kod wyjscia 0 nie wystarcza.
Przy nowym loaderze/treningu analogiczna bramka obejmuje smoke wag i reload.

Proces oceny wprowadza domyslny tryb pilot. Tryb full wymaga review.json
z PASS, potwierdzeniem przegladu odpowiedzi i granic zatrzymania oraz hashami
podsumowania pilota, danych, wag obu wariantow i skryptu. Zmiana parametrow
generacji lub rownoleglosci uniewaznia dowod. Brak review ma blokowac start
przed utworzeniem wynikow i rezerwacja GPU; sprawdzono rzeczywiste odrzucenie
takiego wywolania. Runner i dowody sa prywatnymi artefaktami eksperymentu.

Historyczny pomiar bez stopu na <end_of_turn> jest niepoprawnym pomiarem;
nie uzywac go jako wyniku jakosci modelu. Zachowac jako dowod bledu ewaluatora.
Pilot po poprawce: B0 8/16, F1 16/16; przejrzano wszystkie 32 odpowiedzi.

Przed uruchomieniem odczytaj GPU/VRAM/RAM/CPU; nie zmniejszaj rownoleglosci
bez pomiaru wskazujacego ograniczenie. Baza i wynik treningu musza miec
identyczna liczbe workerow, te same przypadki, prompt i limity generacji.
Jeden koordynator rezerwuje wspolny rejestr GPU na czas zycia workerow.
Po zmianie rownoleglosci zachowaj poprzednia probe osobno; nie mieszaj
pomiarow opoznienia z roznych konfiguracji. Ocena nie wykonuje narzedzi.

Pierwszy pelny wynik: `functiongemma-full-remote-20261103-v1`, proba 2,
264 aktualizacje / 3 epoki, 1408 decyzji treningowych i 352 walidacyjne,
kontekst 2048, batch4/akumulacja4. GPU smoke: zapis/reload/resume/zmiana wag PASS.
Pelny trening: succeeded; ostatni loss treningowy 0.000024993,
loss walidacyjny 0.000135300. Peak VRAM 21.84 GB. Prywatny lokalny pakiet
`data/training/functiongemma-remote-results-20261103/full-result.zip`
ma 2209970581 bajtow; inspect-result potwierdzil complete=true, brak bledow.
Te metryki nie zastepuja oceny poprawnosci wywolan ani niezaleznego testu koncowego.

### Ponowna ocena zdalna v4 (2026-11-03)

Po ponownym pilocie i przegladzie 32 odpowiedzi zakonczono pelne sparowane
porownanie: 352 decyzje na wariant, 24 grupy, 8 workerow po 2 watki CPU.
Trening nie byl powtarzany. B0 oznacza baze, F1 pelny SFT, nie adapter LoRA.

| Wariant | Dokladna decyzja i argumenty | Wywolania narzedzi | Brak wywolania | Mediana | P95 |
|---|---:|---:|---:|---:|---:|
| B0 | 63/352 (17.90%) | 0/288 | 63/64 | 3.759 s | 9.471 s |
| F1 | 350/352 (99.43%) | 286/288 | 64/64 | 1.449 s | 3.247 s |

Dwa bledy F1 to przedwczesne "Gotowe" zamiast zapisu raportu w polskich
przypadkach log_diagnosis-00 i log_diagnosis-03 (decision:9). Ocena braku
wywolania nie ocenia prawdziwosci tekstu. Jest to syntetyczna walidacja,
nie niezalezny test koncowy ani kwalifikacja do aktywacji.

Wszystkie 704 odpowiedzi przeliczono lokalnie; 42 pliki eksportu i archiwum
maja zgodne sumy kontrolne. Prywatne dowody: katalog
`data/training/functiongemma-remote-results-20261103/evaluation-repeat-v4/`.
W v4 nie odtworzono SIGSEGV; przyczyna wczesniejszych awarii pozostaje nieustalona.

`compare TRIALS.json` porownuje sparowane B0/F1/L1 po case_id, problem_group
i tych samych hashach benchmark_sha256/tools_sha256/generation_sha256.
Wiersze zawieraja seconds, exact, schema_valid, unexpected_call. Wynik:
trafnosc pelnych argumentow, schemat, niepozadane wywolania, p50/p95 i liczba grup.
`evaluation.score` waliduje odpowiedz natywna i dokladny zbior wywolan.
`evaluation.propose` daje tylko propozycje albo eskalacje; zatrzymuje generacje
na poczatku function_response, bez fabrykowania wykonania.

Do zamkniecia eksperymentu potrzeba rzeczywistego tokenizera, GPU smoke obu metod,
niezaleznego testu koncowego, oceny retencji, porownania z Gemma4 i dispatcherem,
oraz pomiaru calego czasu routingu+eskalacji. CPU/kwantyzacja to osobna kwalifikacja.
FG5 pozostaje warunkowe: nie dolaczamy niezakwalifikowanego modelu do kazdego czatu.
Nie ma nowego serwisu, portu ani autostartu.

### Lokalne udostepnienie pelnego SFT w Ollama (2026-11-03)

Wynik jest dostepny jako `venom-functiongemma-270m-g05-sft264-20261103:bf16`.
Operator wybiera silnik Ollama i ten model; domyslnego modelu stosu nie zmieniono.
To pelny SFT po 264 aktualizacjach, nie adapter LoRA. GGUF BF16 ma 542847232
bajty, kontekst operacyjny 2048. Uzywa natywnego renderera i parsera functiongemma.

Lokalny pilot GPU: 16/16 poprawnych decyzji na zamrozonych promptach oraz 4/4
wywolania narzedzi przez API chat Ollama. Model miesci sie w calosci w VRAM.
Sprawdzono listowanie, istnienie, odczyt i zapis pliku z JSON-em i nowa linia;
narzedzia nie byly wykonywane. To proba zgodnosci lokalnego formatu i API,
nie pelna lokalna ocena 352 przypadkow ani kwalifikacja ogolnego czatu.

Ollama 0.40.11 ucinala argumenty na nowej linii. Celowy test odtworzyl blad;
poprawka DOTALL i test obu trybow (calosc/strumien) sa w
`scripts/llm/patches/ollama-0.40.11-functiongemma-multiline.patch`.
Na czystych zrodlach tagu v0.40.11 zastosuj ja przez `git apply --unidiff-zero`.
Sprawdzono testy FunctionGemma oraz rzeczywisty zapis JSON-a przez API.
Usluga uzytkownika venom-ollama.service korzysta z lokalnej wersji w katalogu
`~/.local/share/venom266/ollama-0.40.11-functiongemma-multiline/` i oryginalnych
bibliotek 0.40.11. Prywatne dowody importu, hashy i prob sa w
`data/training/functiongemma-remote-results-20261103/local-models/`.

### Lokalna szybkosc na probkach treningowych (2026-11-03)

RTX 3060 12 GB, GGUF BF16, kontekst 2048, pojedyncze zadania przez API Ollama.
Po pilocie 3 probek i przegladzie 6 odpowiedzi zmierzono 20 probek PL/EN
(cztery narzedzia i brak wywolania), po dwa wywolania kazdej.
Zimny start: 1755 ms, w tym ladowanie 1468 ms. Dla zaladowanego modelu:
mediana 161 ms, P95 347 ms; powtorzenie tego samego promptu: mediana 137 ms.
Mediana generowania: 284 tokeny/s. Wspoldzielone prefiksy KV moga byc uzywane.
Poprawnosc: 18/20 probek; dwa warianty recover_missing_file-14 (PL/EN)
zwrocily error_count=2 zamiast 3. To pomiar na danych treningowych,
bez wykonywania narzedzi i bez pomiaru calego cyklu agenta. Surowe wyniki
i raport sa prywatne w `data/training/functiongemma-remote-results-20261103/local-speed-20261103/`.

Oficjalne podstawy: [format Google](https://ai.google.dev/gemma/docs/functiongemma/formatting-and-best-practices)
i [pelny SFT](https://ai.google.dev/gemma/docs/functiongemma/finetuning-with-functiongemma).

## Zapis plików po pilocie G07

W MAF i pętli Ollama identyfikatory FunctionGemma (w tym wydane nazwy
`venom-functiongemma-…`) dostają wyłącznie trzy narzędzia FileSkill:
sprawdzenie istnienia, listowanie i odczyt. Nazwa modelu powinna zachować
oznaczenie rodziny podczas rejestracji aliasu. Sfałszowane wywołanie
zapisu nie ma wykonawcy. Zgody na zapis nie można przekazać w komunikacie
modelu ani w treści odczytanego pliku.

Operator może zatwierdzić konkretną operację z lokalnego terminala Linux/WSL:

```bash
source .venv/bin/activate
python -m scripts.operator_file_write --session moja-sesja \
  --path output/raport.txt --content-file /tmp/sprawdzona-tresc.txt
```

Katalog docelowy musi już istnieć w workspace Venoma. `--empty` pozwala
jawnie utworzyć pusty plik, a `--overwrite` jawnie zatwierdzić nadpisanie.
Jeśli operator podaje plik propozycji przez `--proposal`, jego JSON musi
zawierać dokładnie `file_path` oraz `content`. Obie wartości muszą być
identyczne z niezależnie podaną ścieżką i treścią operatora. Komenda
pokazuje podgląd przed zatwierdzeniem w terminalu. Zgoda wygasa po dwóch
minutach, jest związana z sesją i workspace oraz działa jeden raz.
O obowiązującym trybie autonomii decyduje zapisany stan Venoma.
Udany zapis trafia do pliku `venom.log` w katalogu logów Venoma. Wpis zawiera
identyfikator, czas, sesję, ścieżkę, skrót SHA-256 i informację o nadpisaniu.
Treść pliku pozostaje poza logiem. Dla wpisu obowiązuje rotacja logów Venoma,
a strumień audytu w panelu jest odrębny od procesu CLI.
