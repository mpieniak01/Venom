# Natywny adapter tekstowy Omni w czacie

Jest to jawnie włączana lokalna ścieżka dla tekstowej LoRA Omni 2B. Wybór obejmuje zwykły endpoint `POST /api/v1/llm/simple/stream`. Integralność katalogu nie oznacza kwalifikacji jakości adaptera.

Przed uruchomieniem jednego procesu API operator ustawia:

- `OMNI_NATIVE_TEXT_CATALOG_ROOT`: bezwzględny katalog Academy experiments z podkatalogiem adapters;
- `OMNI_NATIVE_SNAPSHOT`: materializowany snapshot zgodny ze śledzonym omni_native_snapshot.json;
- `OMNI_NATIVE_TEXT_ENV`: venv z przypiętymi zależnościami treningowymi/PEFT, używający tej samej bazy Pythona co API.

API wyboru jest pod `/api/v1/llm/native-text`. `GET /catalog` odczytuje poprawne wpisy katalogu, `GET /state` pokazuje bieżący i poprzedni wybór. `PUT /selection` przyjmuje `adapter_id` i `expected_runtime_id` bieżącego wyboru (null przy pierwszym wyborze). Przed publikacją wyboru wykonuje rzeczywiste ładowanie i krótką generację kontrolną. Błąd lub anulowanie zachowuje poprzedni wybór. ID nie jest ścieżką; symlinki, niezgodne konfiguracje i zmienione wagi są odrzucane.

`POST /rollback` przyjmuje `expected_runtime_id`. Przywrócenie poprzedniego PEFT porównuje pełny zachowany wybór z aktualnym katalogiem, następnie ponownie ładuje i sprawdza jego wagi. Spójnie przepisany wpis katalogu o tym samym ID również jest odrzucany przed generacją kontrolną. Powrót do null wyłącza nakładkę i używa poprzedniej konfiguracji zwykłego runtime. Jeżeli ktoś zmienił ten runtime podczas aktywnej nakładki, odbiór i rollback zgłaszają drift zamiast potwierdzać pozorne przywrócenie. Wybór jest lokalny dla procesu; restart API wyłącza nakładkę i nie zmienia globalnej konfiguracji modelu.

Żądanie czatu przekazuje `model=null`, ID adaptera albo pełne runtime_id z odpowiedzi wyboru. Inny model lub nieaktualny expected_runtime_id/config_hash jest odrzucany. Historia user/assistant przechodzi w tej samej kolejności, także z wcześniejszym błędem asystenta. Worker odrzuca zbyt długi kontekst zamiast go ucinać. Temperatura jest deterministyczna, limit wynosi 1–1024 nowych tokenów. Funkcje narzędzi, materiały, niestandardowy format i Studio Normal wymagają osobnego odbioru i są jawnie odrzucane.

Generacja zachowuje host admission i blokadę wyboru do zakończenia procesu. Worker działa offline w prywatnym namespace, weryfikuje pliki przypiętego snapshotu, hashe adapter_config.json i adapter_model.safetensors, używa natywnego AutoModelForMultimodalLM z PEFT ograniczonym do części językowej. Nie eksportuje wag przez AutoModelForCausalLM. Każda tura ma świeży proces; obecna implementacja nie utrzymuje GPU modelu między turami.

Zdarzenia SSE start/done zawierają model_identity: ID i SHA wag/konfiguracji, przypięcie snapshotu, hash faktycznych wiadomości wejściowych oraz pomiary. Hash wejścia odpowiada profiles.stable_hash. Backend sprawdza te hashe przed publikacją odpowiedzi. Historia sesji utrwala tożsamość wag i request_id razem z faktycznym tekstem odpowiedzi. Dodatnie testy na atrapach potwierdzają kontrakt kodu; rzeczywisty odbiór P13 wymaga kontrolowanego dostępu do GPU i izolowanego API. Użytkownik musi odczytać pełną odpowiedź do końca, aby standardowy mechanizm historii utrwalił zakończoną turę.

## Własność hosta podczas rzeczywistego odbioru

Na jednym GPU obowiązuje jeden właściciel namespace `MEMORY_ROOT` i wspólny ledger host admission. Drugi proces API nie może otrzymać własnego ledgera na tym samym GPU. Przed odbiorem należy potwierdzić bezczynność, zatrzymać główne API zgodnie z launcherem, uruchomić API odbioru ze wspólnym `MEMORY_ROOT` oraz osobnym SessionStore, a po zakończeniu zatrzymać je i odtworzyć główny stos z jego wcześniejszą konfiguracją. Sprawdzenie zakończenia obejmuje puste dzierżawy, brak aktywnej pracy i rzeczywistą dostępność GPU.

Rezydentny model Ollamy może nadal zajmować VRAM mimo zatrzymania API. Dla odbioru ustaw `LLM_KEEP_ALIVE=0` w izolowanym procesie, aby jego zwykła generacja zwolniła własny model. Nie wykonuj potajemnego unloadu innych modeli. Jeśli pamięć nadal jest zajęta, zgłoś ten stan przed obciążeniem GPU; sama pustka kolejki nie dowodzi dostępności VRAM.

## Wybór z aplikacji

W `/chat2` wybierz adapter w sekcji „Adapter tekstowy Omni”, następnie „Wczytaj i sprawdź”. Aplikacja wykonuje prawdziwy probe przed przełączeniem i pokazuje hash aktywnych wag. Przypięty P13 ma etykietę referencji; inne wpisy są kandydatami bez kwalifikacji. Etykieta nie jest wynikiem nowego testu jakości. „Przywróć poprzedni model” używa chronionego rollbacku backendu. Wybór wygasa po restarcie API; odświeżenie stanu i ponowne wejście do okna pobierają stan serwera.

Wybrany adapter działa w Direct. Inne tryby i dołączone materiały blokują wysłanie; szkic pozostaje zachowany. Przy aktywnym adapterze wybór zwykłego silnika jest zablokowany do rollbacku. Tożsamość ze zdarzeń SSE jest sprawdzana przed uznaniem odpowiedzi za ukończoną, następnie zapisywana w lokalnej historii i wyświetlana przy odpowiedzi. Po ponownym wczytaniu sesji aplikacja pokazuje tożsamość utrwaloną przez serwer. Żądanie ze starym runtime nie jest automatycznie ponawiane. Historia native jest przekazywana bez przycinania przez frontend; backend nadal kontroluje rzeczywisty limit kontekstu.

## Powtarzalny odbiór i przywracanie

`scripts/academy/native_text_acceptance.py` udostępnia `run_acceptance(output, main_root, steps)`. Sterownik rzeczywistego odbioru dostarcza kanoniczne kroki `preflight`, `stop_main`, `start_test`, `accept`, `stop_test`, `restore_main`, `verify_restore`. Krok startu może uruchomić pełną aplikację na osobnym porcie po zatrzymaniu głównego właściciela. Testowy SessionStore musi być odrębny; MEMORY_ROOT i ledger pozostają wspólne. Helper nie uruchamia usług przy imporcie ani w testach automatycznych.

Każda próba wymaga nowego katalogu. Nawet błąd stopu procesu testowego nie pomija przywrócenia głównego stosu i świeżego sprawdzenia. `status=passed` wymaga wszystkich udanych kroków oraz odczytu `verify_restore` wykonanego po rozpoczęciu tej fazy: dziewięć HTTP200, aktualni właściciele API/UI/nadzorcy w kanonicznym katalogu, aktywny nadzorca, zamknięte porty testowe, brak lease i operations, pusty wykaz aktywnych eksperymentów i modeli Ollamy oraz dostępna blokada GPU. Nie wolno podawać wcześniejszego receiptu zamiast nowego pomiaru. `lifecycle.json` i osobne pliki faz zachowują również nieudane przywrócenie; samo zakończenie generacji nie nadaje PASS całemu odbiorowi.
