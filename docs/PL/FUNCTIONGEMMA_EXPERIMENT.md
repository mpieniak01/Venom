# FunctionGemma 270M: lokalny eksperyment narzedziowy

Status: pelny SFT zakonczony 2026-11-03; model pozostaje niedopuszczony do czatu.
Porownawcza ocena jakosci jest oddzielna od sukcesu treningu i GPU smoke.
Galaz: `codex/functiongemma-tool-training`. Zmiany pozostaja lokalne.

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
`--snapshot` i nowy katalog `--output`. Snapshot musi byc lokalnie dostepnym
katalogiem przypietej rewizji HF; polecenie niczego nie pobiera. Powstaja
release.json, encoded.json, full-recipe.json, lora-recipe.json i preparation.json.
Maska obejmuje tylko ostatnia wybrana odpowiedz asystenta i natywny koniec tury.
Przekroczenie kontekstu jest bledem, bez obcinania i bez packingu.

## Trening i smoke

F1: pelny SFT BF16. L1: LoRA BF16 r8/alpha16/dropout0.05 na q/k/v/o.
Wspolne: kontekst1024 (2048 wymaga nowego eksportu), batch4, akumulacja4,
LR5e-5, AdamW wd0.01, linear, warmup5%, seed42, maksymalnie3 epoki.
Dla1408 decyzji:88 aktualizacji/epoke,264 ogolem. Ostatnia niepelna akumulacja
jest zachowana przez Trainer. Rozproszony WORLD_SIZE>1 jest odrzucany.
Walidacja loss co okolo pol epoki, zapis po kazdej epoce. Kod nie wybiera
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

Oficjalne podstawy: [format Google](https://ai.google.dev/gemma/docs/functiongemma/formatting-and-best-practices)
i [pelny SFT](https://ai.google.dev/gemma/docs/functiongemma/finetuning-with-functiongemma).
