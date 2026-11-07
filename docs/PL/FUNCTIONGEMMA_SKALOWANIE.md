# PR — porównanie FunctionGemma 268M i 299M

W ostatnim porównaniu wąski kontrakt osiągnął 111/128, w tym 48/64 po polsku i 63/64 po angielsku. Wszystkie dziewięć nieoczekiwanych wywołań dotyczyło polskich intencji zapisu. Eksperyment sprawdza osobno wpływ nowych przykładów i wpływ poszerzenia modelu. Punktem startu jest zachowany checkpoint 128 wąskiego kontraktu.

## Ramiona i warunki

| Ramię | Parametry | Dane |
|---|---:|---|
| A | 268 098 176 | Dotychczasowe 2048 decyzji |
| B | 268 098 176 | 2048 decyzji z 512 zmienionymi polskimi przykładami |
| C | 299 063 936 | Identyczne rekordy i tokeny jak w B |

A–B mierzy wpływ korpusu. B–C mierzy wpływ poszerzenia wszystkich 18 MLP z 2048 do 2944. Wagi A i B są identyczne. C kopiuje ich wartości, dodaje kanały z zerowym wkładem na wyjściu i zachowuje tokenizer oraz kontrakt sześciu akcji. Oba seedy treningowe zaczynają od tych samych wag w obrębie ramienia i świeżego stanu AdamW.

Receptura zachowuje pełny SFT, parametry i momenty AdamW FP32, obliczenia BF16, batch 4 z akumulacją 4, kontekst 2048 i 128 aktualizacji na epokę. Wstępnie ustalony LR to 2e-6. Checkpointy są zapisywane po 32, 64, 96 i 128 krokach. Ocena kandydatów obejmuje 32, 64 i 128. Oba przebiegi porównawcze używają tego samego sprzętu i odpowiednio seedów 42 i 43.

## Materiał i ocena

- Zachować język, pozycje rekordów oraz etykiety akcji przy wymianie polskich przykładów. Przy jednej ścieżce rozdzielić odczyt, podgląd, zapis z treścią, pustą treść, brak treści i cofnięcie polecenia.
- Przygotować rozłączne rodziny parafraz i przestrzenie robocze dla treningu, rozwoju i zamrożonej oceny. Odtworzyć referencje w sandboxie. Raportować osobno surową akcję modelu, zweryfikowane argumenty i wynik wykonania. Zapisy testować w warstwie zgody operatora.
- Zweryfikować pełne generacje pilota przed treningiem z wag 268M i 299M. Kwalifikacja GPU na hoście obejmuje zmianę wag, zapis, odczyt i wznowienie każdej receptury. Przed oceną masową przejrzeć 16 surowych odpowiedzi każdego ocenianego checkpointu.
- Porównywać wynik PL i EN, akcje, argumenty, nieoczekiwane wywołania, błędy formatu, utracone poprawne odczyty oraz medianę i P95 na wspólnych poprawnych przypadkach. Grupować wnioski według rodzin parafraz. Mierzyć oddzielnie zużycie VRAM i opóźnienie w docelowej ścieżce Venoma.
- Do odbioru kierować jednego finalistę po obu powtórzeniach i przejściu retencji. Obowiązują 98% poprawnych zadań narzędziowych, 95% odpowiedzi bez wywołania oraz zero wywołań nieoczekiwanych lub niedozwolonych, deklaracji zapisu bez wykonania i utraconych poprawnych odczytów.

## Wykonanie

Lokalnie powstają narzędzie do poszerzenia, korpusy, pakiety z odciskami kodu i danych, testy, dowód równoważności inicjalizacji oraz procedura sesji zdalnej. Artefakty modelu, dane i surowe wyniki są prywatne. Używamy standardowej sesji FunctionGemma na Ubuntu VM z SSH direct, dyskiem według zapisanego profilu i kartą z co najmniej 24 GB VRAM. Przed treningiem host przechodzi kwalifikację. Uruchomienia treningowe są osobnym etapem operacyjnym.

### Pakiet operatora

Polecenia wykonuje się z katalogu Venoma i aktywnego środowiska. `HISTORY` wskazuje prywatne archiwum wcześniejszego A/B, `SNAPSHOT` katalog przypiętej rewizji tokenizera, `START_WEIGHTS` katalog checkpointu startowego z `export-receipt.json`, `HISTORICAL_ACCEPTANCE` zamrożone archiwum ZIP wskazane przez wcześniejszy plan oceny, a `KIT` nowy katalog eksperymentu.

```bash
python -m scripts.functiongemma_scale.prepare \
  --history "$HISTORY" --snapshot "$SNAPSHOT" \
  --start-weights "$START_WEIGHTS" --historical-acceptance "$HISTORICAL_ACCEPTANCE" \
  --output "$KIT"

python -m scripts.functiongemma_scale.baseline \
  --package "$KIT" --phase pilot --output "$KIT/baseline-pilot"
# Po przejrzeniu pełnych generacji obu modeli z pilota:
python -m scripts.functiongemma_scale.baseline \
  --package "$KIT" --phase development --output "$KIT/baseline-development" \
  --pilot-receipt "$KIT/baseline-pilot/result.json"
```

Pakiet zawiera sześć planów z osobnym `run_id`, dwa współdzielone zestawy wag oraz rozłączne archiwa oceny rozwojowej i odbiorczej. Walidacja development obejmuje 128 nowych przykładów, 24 warianty zmieniające pojedynczo kolejność kluczy, kolejność narzędzi lub prompt oraz 192 starsze przypadki retencji. Ten ostatni zestaw odtwarza istniejące przypadki po przystosowaniu do wąskiego kontraktu. Dopasowanie referencji sprawdza eksperymentalny wykonawca w sandboxie. Odbiór 256 nowych przypadków pozostaje oddzielnie. Starszy zestaw odbiorczy 256 + 64 zachowuje dotychczasowe sumy i format. Automatyczna aktywacja modelu pozostaje wyłączona.

### Sesja na zdalnej VM

1. Wyświetlić aktualne oferty przez `scripts/cloud/vast/offers_table.py --training-suite "$KIT/host-suite.json"`. Użyć obecnego profilu, Ubuntu VM, SSH direct, rozmiaru dysku z `host-suite.json` i min. 24 GB VRAM. Po wybraniu hosta przeprowadzić [kwalifikację VM, SSH i sandboxa](VAST_START_I_ODZYSKIWANIE.md).
2. Przenieść czysty checkout zgodny z `code_commit` z `readiness.json`. W trakcie przygotowania środowiska wysłać niezależnie plan, skrypty oceny i dwa katalogi wag z zachowaniem sum. Każdy katalog wag przesłać raz. `register` używa twardych dowiązań wewnątrz tego samego systemu plików. Przyjąć pakiet danego ramienia przez `python -m scripts.functiongemma_scale.register --root "$REMOTE_ROOT" --bundle "$ARM_DIR/input.zip" --plan "$ARM_DIR/launch-plan.json" --weights "$REMOTE_WEIGHTS"` uruchomione z checkoutu zdalnym interpreterem RPC. Oczekiwany wynik to `prepared`, próba 0.
3. Na tym samym hoście powtórzyć przedtreningowy pilot z obu wag w docelowej precyzji oceny. Przy rozbieżności surowych generacji sprawdzić precyzję i inicjalizację przed porównaniem jakości. Następnie dla każdego z sześciu `run_id` wykonać `start --stage smoke`, monitorować stan, zweryfikować `save/reload/resume` i momenty FP32, dopiero potem wykonać `start --stage train` przez istniejący `venom_core.services.remote_training.cli`. Jeden trening albo jedna ocena GPU naraz. Równolegle pobierać potwierdzenia i raporty z zakończonych etapów.
4. Przed każdym nowym ramieniem sprawdzić rzeczywiście wolne miejsce. Jeden pełny checkpoint 299M z parametrami i momentami FP32 zajmuje około 3,6 GB przed narzutem, a worker zapisuje kilka checkpointów i kopie wyników. Przy ograniczonej przestrzeni rozliczać ramiona sekwencyjnie, zachować sumy i wyniki wszystkich przebiegów oraz przenieść wybrane wagi poza host przed sprzątaniem dużych kopii. Pełny stan optymalizatora zachować dla finalistów i tam, gdzie wymagane jest wznowienie.
5. Ocenę checkpointów wykonywać na tej samej VM, z ośmioma workerami i natywną serializacją. Rozpakowany `run_evaluation.py` z `evaluation.zip` wymaga osobnego pilota 16 i potwierdzenia przeglądu przed pełną oceną. `python -m scripts.functiongemma_scale.score` ocenia zapisane odpowiedzi na tym samym pliku przypadków i planie. `python -m scripts.functiongemma_scale.compare` porównuje werdykty parami, z podziałem na PL, EN, grupy i rodziny. Raportować oddzielnie A–B i B–C dla obu seedów oraz zgodność z wagami startowymi na retencji. Zapisać p50/p95, szczytowy VRAM i przerwy w działaniu procesu.
6. Do zamrożonej oceny przechodzi jeden checkpoint z tego samego kroku w obu powtórzeniach. Dla 299M wymagać dodatniego bilansu na nowych rodzinach PL w obu powtórzeniach wobec 268M przy tym samym kroku oraz zachowania wcześniejszych poprawnych odczytów. Pomiary końcowe obejmują eksport i cały czas żądania w docelowym Venomie. Weryfikować reguły zgody na zapis w runtime osobno od surowej decyzji. Pobrać i zweryfikować sumy wybranych wag, raportów i uzgodnionych stanów wznowienia przed zwolnieniem instancji.

Dane są syntetyczne. Niezależny przegląd etykiet i powtórzenie wyników na prawdziwych poleceniach operatora należą do odbioru. Zachowanie punktu startu na CPU jest dowodem technicznym, a wpływ dodatkowej pojemności na jakość rozstrzyga pomiar po treningu.
