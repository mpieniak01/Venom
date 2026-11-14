# Trening lokalny i na hoscie SSH

Ten sam proces sesji obsluguje dwa miejsca wykonania:
`--execution local` oraz `--execution remote` (domyslne).
Zadania, pakiety, status, historia prob, logi, stop, resume i collect korzystaja
ze wspolnego RemoteClient/JobStore. Wykonanie lokalne nie otwiera portu ani tunelu.
Wybor miejsca nie uruchamia treningu, nie rezerwuje Vast i nie pobiera modelu.

## Konfiguracja hosta

Lokalnie wskaz jawnie:
`--local-root /sciezka/do/katalogu/hosta` i
`--local-python /sciezka/do/venv-kontrolera/bin/python`.

`host-init --root ... --worker-python ... --snapshot ... --admission-db ...
--code-root ...` zapisuje zaufana konfiguracje hosta.
Worker-python jest osobnym interpreterem zgodnym z lockiem modelu.
Dla `--execution local` rejestr admission-db musi odpowiadac MEMORY_ROOT
wybranemu w lokalnym .env.dev; alternatywna pusta baza jest odrzucana.
`host-check` pokazuje gotowosc bez ladowania wag i zajmowania GPU.

Dzialajacy Venom trzyma blokade przestrzeni hosta. Trening lokalny wymaga
jawnego okna wylacznosci GPU: operator konczy korzystanie ze stosu, zatrzymuje
go standardowym launcherem, a nastepnie wykonuje host-check. Samo zwolnienie
modelu Ollamy moze nie zwolnic blokady API. Kod nie zatrzymuje uslug automatycznie.
Po treningu operator przywraca stos standardowym launcherem.
Kontrola jest powtarzana w koordynatorze, wiec nie mozna ominac jej bezposrednim RPC.

Zdalnie wskaz istniejacy alias SSH: `--execution remote --host ALIAS
--remote-root /workspace/data/remote-training --remote-python python3`.
Host przygotuj dotychczasowymi skryptami. Konfiguracja snapshotu i interpretera
nalezy do host-init na tym hoscie. Klucze i known_hosts pozostaja w konfiguracji SSH.
Nie zamawiamy ani nie usuwamy hosta przy wyborze miejsca treningu.

## Przyklad lokalnej sesji

Ponizsze polecenia projektu wykonuje sie w Ubuntu-Venom jako ubuntu.
`control` oznacza jawny interpreter kontrolera; nie jest komenda do przegladarki.

```bash
control=/sciezka/do/venv-kontrolera/bin/python
host_root=/sciezka/do/przygotowanego/hosta
"$control" scripts/remote_training.py --execution local --local-root "$host_root" host-check
"$control" scripts/remote_training.py --execution local --local-root "$host_root" --local-python "$control" upload --bundle /sciezka/input.zip
"$control" scripts/remote_training.py --execution local --local-root "$host_root" --local-python "$control" start --run-id fg-full --stage smoke
"$control" scripts/remote_training.py --execution local --local-root "$host_root" --local-python "$control" watch --run-id fg-full
```

Po udanym smoke mozna jawnie wywolac start z `--stage train`.
Resume przyjmuje checkpoint wzgledny wewnatrz tej samej sesji, zapisany w attempts.
Stop zatrzymuje tylko procesy tej proby. Collect z `--include-checkpoint`
zbiera rowniez stan optimizer/scheduler/RNG; bez tego resume na podstawie
samego zebranego modelu nie jest uprawnione. Zmiana hosta wymaga nowego smoke.

## FunctionGemma 270M

Korzystamy z gotowego natywnego encoded.json oraz full-recipe.json/lora-recipe.json.
Pakowanie wspolne dla obu miejsc:

```bash
"$control" scripts/remote_training.py pack --source /sciezka/przygotowanych/danych --manifest /sciezka/encoded.json --profile /sciezka/full-recipe.json --snapshot /sciezka/przypietej/rewizji --output /sciezka/input.zip --run-id fg-full --updates 264 --max-seconds 7200
```

Budzet jest liczony z epok w recepcie i liczby decyzji w wybranym eksporcie.
Nie stosujemy limitu 256 historycznego trenera Granite. W tym pilocie FG nie obsluguje
`--until-update`: wybieramy pelna recepte epok albo wznawiamy jej checkpoint.

Pelny SFT oraz LoRA maja niezalezne sesje i dowody smoke.
Dziecko workera dziedziczy sprawdzona rezerwacje koordynatora; nie zajmuje
ponownie tego samego rejestru. Brak rezerwacji rodzica oznacza odmowe.
Tryb offline jest wymuszony dla koordynatora i workera obu miejsc wykonania.

Zbieranie pelnego SFT obejmuje model.safetensors/config.json, a LoRA pliki
adaptera. Oba wyniki maja metryki, dowody, logi i opcjonalny checkpoint.
Zebranie nie aktywuje modelu. Import FunctionGemma do Academy/aktywnego czatu
wymaga osobnej oceny i implementacji promocji; dotychczasowy importer adapterow
nie interpretuje pelnego modelu jako adaptera.

Lokalne sciezki, liczebnosci i gotowe pakiety przechowujemy poza Git.
Nie publikowac modeli, danych ani prywatnych konfiguracji hosta.
