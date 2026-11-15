# Zdalna kampania tekstowa w Academy

Kampania na przygotowanej VM Vast wykonuje kolejne próby LoRA i ocenę tekstu w istniejącej kolejce Academy. Po każdej zakończonej ocenie kontroler próbuje zsynchronizować archiwum dowodów. Academy pokazuje wykonaną pracę, wynik względem M0, koszt i stan VM.

Wybierz tę opcję, gdy chcesz użyć GPU Vast. Na własnym GPU możesz uruchomić kampanię z automatyczną oceną przez domyślny **Trening lokalny**. [Instrukcja lokalnych kampanii](ACADEMY_EKSPERYMENTY.md)

## Kontroler i przygotowanie

Uruchom API Academy i kontroler na stale działającym hoście Linux poza wynajętą VM. Oba procesy potrzebują tej samej konfiguracji i trwałych katalogów Academy oraz Vast. Kontroler wymaga dostępu SSH i klucza dostawcy przechowywanego w lokalnej konfiguracji. Przykład usługi użytkownika znajdziesz w [katalogu systemd](../../scripts/systemd/venom-remote-text.service.example). Ustaw WorkingDirectory, ENV_FILE i ExecStart dla tego wdrożenia. Pojedynczy kontroler można też uruchomić w konsoli w przygotowanym środowisku.

```bash
source .venv/bin/activate
python -m venom_core.services.training_experiments.remote_text_supervisor
```

Przygotuj dedykowaną VM według [procedury Vast](VAST_START_I_ODZYSKIWANIE.md). Złóż plan w trybie inspect z polityką `destroy` dla jednorazowego przebiegu lub `stop` dla kolejnych kampanii na tej samej instancji. Przygotuj na VM przypięty checkout Venoma, interpreter RPC, snapshot, środowisko treningowe, izolację i katalog eksperymentów. Na kontrolerze i VM zainstaluj ten sam plik profilu z automatyczną kalibracją dev oraz zidentyfikowanymi danymi. Ścieżki względne w profilu mogą wskazywać analogiczne wejścia pod różnymi katalogami bazowymi. Dla strategii optuna zainstaluj przypięte requirements/optuna.txt w .venv-optuna wewnątrz checkoutu VM. Ustaw VENOM_OPTUNA_PYTHON na odpowiedni przypięty interpreter kontrolera według [instrukcji Academy](ACADEMY_EKSPERYMENTY.md). Zdalne RPC włącza dopuszczenie GPU, a kontroler sprawdza zgodność całego planu.

Po przygotowaniu potwierdź klucz hosta w pliku known_hosts powiązanym z planem. Poniższe polecenie stosuje istniejącą kontrolę sandboxu i przypisuje VM do identyfikatora kampanii. Wybierz flagę odpowiadającą polityce w planie Vast.

```bash
python -m venom_core.services.training_experiments.remote_text_vast PLAN_ID \
  --campaign-id CAMPAIGN_ID --repo /workspace/venom \
  --python /workspace/data/remote-training/rpc-python \
  --root /workspace/academy/experiments --commit COMMIT_SHA \
  --sandbox-manifest /workspace/benchmarks/dialogue/manifest.json --authorize-destroy
```

Przy polityce `stop` użyj `--authorize-stop`. Po potwierdzonym zwolnieniu GPU dysk VM pozostaje dostępny i nadal generuje opłatę. Aby użyć tej samej VM, uruchom ją z tego samego planu Vast, zweryfikuj SSH, dołącz kolejną wersję danych i zarejestruj nowy identyfikator kampanii. Kontroler sprawdza łączny pozostały czas najmu od pierwszego startu. Wznowienie zależy od dostępności GPU. [Zarządzanie instancjami Vast](https://docs.vast.ai/guides/instances/manage-instances)

## Zlecenie i wynik

1. W Academy otwórz Kampanie i wybierz **Zdalny trening tekstowy · Vast**. Podaj ID przygotowanego planu Vast, limit kwoty, profil, czas i konfiguracje. Przy strategii Optuna kontroler wykorzystuje dopuszczone zakresy.
2. Zweryfikuj oszacowanie kosztu i uruchom zapisany plan. Termin utrwala się przy starcie. Rezerwa przeznaczona na synchronizację i zwolnienie VM skraca okno na próby. Po starcie możesz zamknąć Academy.
3. Po zakończeniu odczytaj wynik i pobierz archiwum. Wynik rozwojowy porównuje kandydatów na zamrożonym dev. Najlepszy oceniony adapter i kompletność dowodów są dostępne również wtedy, gdy próby wyczerpały czas przed końcem.

### Warunkowa dogrywka

Dla stałej listy prób możesz ustawić liczbę prób przed decyzją. Pozostałe warianty tworzą dogrywkę. Host uruchamia ją, jeśli najlepszy checkpoint z pierwszej części przeszedł wszystkie bramki selekcji i osiągnął wskazany przyrost na dev względem M0. W przeciwnym razie pomija dogrywkę, zachowuje wyniki i kończy kampanię. Raport zapisuje decyzję i dowód, na którym się opiera.

W limicie czasu, kwoty, aktualizacji, tokenów i miejsca uwzględnij od razu obie części. Na przykład osiem prób może składać się z pierwszych czterech i kolejnych czterech po przekroczeniu progu. Ustal budżet całego najmu wraz z przygotowaniem i synchronizacją. Host podejmuje decyzję po pierwszym bloku prób. Ten moment może wypaść przed orientacyjną godziną lub później. Twardy termin utrwala się przy starcie i pozostaje górną granicą. Ocena końcowa przyrostu względem wspólnego rodzica nadal jest osobnym krokiem.

### GPU dla obecnej receptury czatu

Do wyszukiwania ofert LFM3-Omni-2B BF16 LoRA dla tekstu zacznij od jednej karty NVIDIA i `min_gpu_ram_mb: 12000` w profilu Vast `inspect` z `vm_required: true`. Dwie udane próby na RTX 3060 12 GB przy mikrobatchu 1, limicie 1280 tokenów i rank 4 osiągnęły szczyt rezerwacji PyTorch 5486 MiB. To pomiar trainera. Przy wydłużeniu rzeczywistych sekwencji, zmianie modelu lub równoległości ponownie zmierz pełne zużycie GPU łącznie z oceną. Porównuj przewidywany koszt ukończonej kampanii wraz z dyskiem i transferem. [Pola wyszukiwania ofert Vast](https://docs.vast.ai/api-reference/search/search-offers)

Przycisk zatrzymania zapisuje żądanie przez API. Kontroler obserwuje stan procesu i pobiera ostatnie kompletne dowody. Gdy łączność nie wróci przed terminem, zachowuje wcześniej potwierdzone archiwa, a finalizacja zgłasza brakujące dowody. Stan oczekiwania na zwolnienie VM wymaga dalszego uzgodnienia z dostawcą. Opóźnione rachunki i awarie dostawcy mogą przedłużyć ekspozycję kosztową. Kontroler odróżnia koszt oszacowany od rozliczonego.

## Niezależna kwalifikacja adaptera

Kampania ze stałą listą może kontynuować jeden wspólny adapter. Zainstaluj ten sam wpis katalogu wraz z wagami, konfiguracją i potwierdzeniem hashy na obu hostach i wybierz go we wszystkich wariantach. Zgodność sprawdza plan. Obecna kwalifikacja automatyczna mierzy poprawę względem M0. Zdalna kampania kontynuacji dopuszcza ranking na dev. Do wydania przyrostowego potrzebne jest osobne porównanie ze wspólnym rodzicem.

Dla kampanii startującej od M0 podaj w formularzu SHA-256 odłożonego testu i jego kalibracji. Na dedykowanym GPU do oceny udostępnij artefakty kontrolera i przypięty snapshot modelu. Po finalizacji kampanii istnieje możliwość oceny jednego zamrożonego finalisty wybranego na zbiorze dev.

```bash
python -m venom_core.services.training_experiments.remote_text_qualification \
  /srv/venom-data/training/experiments CAMPAIGN_ID /srv/venom-data/final-inputs.json
```

Plik wejściowy zawiera ścieżki train, dev, final_test, calibration, snapshot, training_venv oraz max_seconds. Dane train i dev służą do sprawdzenia hashy i rozłączności z holdoutem. Plik final_test używa podziału pilot. Pole dev_sha256 w kalibracji zawiera hash oryginalnego pliku pilot. Holdout i kalibracja pozostają na hoście oceny. Exact-v1 wymaga pokrycia wszystkich odpowiedzi końcowego pomiaru. Brak pokrycia skutkuje niekompletną oceną. Na dedykowanym hoście oceny włącz RUNTIME_ADMISSION_ENABLED i wykonuj zadanie bez działającego API Venoma oraz konkurencyjnych procesów GPU.

Do wykonania automatycznego umieść manifest kwalifikacji pod nazwą CAMPAIGN_ID.json w katalogu remote-text-final-inputs wewnątrz katalogu eksperymentów. Katalog kolejki powinien mieć uprawnienia 0700. Na dedykowanym hoście oceny wywołuj okresowo polecenie poniżej, korzystając z tego samego trwałego magazynu co kontroler. Jedno wywołanie obsługuje co najwyżej jedną przygotowaną kampanię. Proces oceny jest niezależny od czasu życia VM treningowej.

```bash
python -m venom_core.services.training_experiments.remote_text_qualification \
  /srv/venom-data/training/experiments --pending
```

Pozytywny wynik potwierdza świeże załadowanie konkretnego adaptera przez natywny tryb tekstowy Omni z PEFT. Katalog Academy pokazuje zakwalifikowany adapter i pozwala użyć go jako rodzica kolejnego zlecenia zgodnego z jego recepturą.

Odbiór ścieżki Vast wymaga przygotowanej VM i zamrożonego profilu czatu tekstowego z danymi oraz oceną. Testy kodu używają imitacji dostawcy. Płatny pilot wykonuje się jako osobne zlecenie operatora.
