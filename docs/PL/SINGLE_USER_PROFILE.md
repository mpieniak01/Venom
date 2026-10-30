# Domyślny profil Venoma dla jednej osoby

Codzienny profil zachowuje obecne funkcje aplikacji, jeden worker API i wybrany
silnik/model. Domyślny frontend developerski korzysta z Turbopack. Webpack jest
jawną opcją awaryjną; błąd watchera nie zmienia bundlera automatycznie.

## Uruchamianie

- `make start` lub `make start-dev`: domyślny stos z Turbopack.
- `make start-dev-webpack`: jawny powrót do Webpack do diagnostyki.
- `make start-dev-turbo`: jawny odpowiednik wyboru domyślnego.
- `make status`: stan procesów; gotowość funkcji należy sprawdzić przez API i UI.

Hostowy launcher `venom-full start`, jeśli został zainstalowany dla konkretnej
instancji, deleguje do tego samego domyślnego celu Make. Zachowuje własne porty,
wybrany plik środowiska i istniejący venv. Nie kopiować całego pliku .env z innej
instancji. Standardowe porty repo i porty hostowego launchera mogą się różnić.

Przed restartem ustalić właściciela listenera, PID/cwd oraz aktywne zadania.
Nie zatrzymywać cudzej instancji ani sprawnego modelu dla samego wyniku testu.
Odbiór modułów opcjonalnych obejmuje ich rzeczywisty DOM i API; HTTP 200 strony
głównej nie potwierdza kompletności aplikacji.

## Gotowość i priorytety

Zapisany wybór OpenRouter/Vast jest rozstrzygany przez tę samą funkcję runtime,
której używa API. Protokół Ollama na zdalnym Vast nie oznacza lokalnego daemona.
Jawne wyłączenie lokalnego runtime oraz llm_off pozostają respektowane.
Rozstrzygnięcie przy starcie jest offline i nie wykonuje generacji ani Test Zero.

Często używane audio zachowuje dotychczasową jakość i asynchroniczne przygotowanie.
Nie wybieramy słabszego modelu ani nie zmieniamy silnika dla oszczędności idle RAM.
Admission i kontrola kosztów nadal obowiązują przy rzeczywistym wykonaniu.

Opcjonalne skanowanie workspace i automatyczna dokumentacja czekają na bezczynność
pracy interaktywnej i współdzielonego runtime. To wskazówka dla planowania I/O,
nie rezerwacja modelu: właściwe admission nadal sprawdza dostęp atomowo.
Health checks i retencja nie są globalnie wyłączane. Początkowy skan Gardenera
nie opóźnia gotowości HTTP. Zatrzymanie usług musi odczekać rzeczywiste wątki I/O,
ponieważ anulowanie await nie zabija operacji plikowej w Pythonie.

## Interfejs

Sesja jest inicjalizowana po zgodnej hydratacji SSR/klienta. Czat nie czeka na
pełen zestaw statystyk. Zamknięte panele nie utrzymują swoich wyłącznych subskrypcji;
polling współdzieli aktualnych odbiorców i zatrzymuje zbędne timery ukrytej karty.
Powrót odświeża dane; aktywny stream i Stop pozostają osobnymi mechanizmami.

PL jest pojedynczym podstawowym słownikiem; EN/DE są ładowane oddzielnie.
Wybrany język jest uzgadniany z SSR i zapisywany w cookie. Prefetch najczęstszych
tras pozostaje włączony, a pozostałe trasy czekają na intencję nawigacji.
KaTeX jest potrzebny dopiero dla matematyki, wykres ładuje wymagane typy po
widoczności. Rendering treści nadal wymaga sanitizacji.

## Pomiar i odbiór

Porównywać identyczne ekrany, historię, bundler, cache, wybrany runtime i rozgrzanie.
Oddzielić start procesu, stan gotowy i pierwsze użycie. Zapisać SHA core/modułów
oraz wersje środowiska. Raportować osobno PSS UI/API/workerów/LLM, VRAM,
transfer skompresowany i po dekompresji, stertę JS oraz opóźnienia. Sterta JS
nie jest całym RAM karty. Przeniesienie zasobu do workera nie oznacza redukcji sumy.

Odbiór obejmuje reload, historię, pierwszy fragment i Stop, reconnect,
nawigację, rzeczywiście ukrytą kartę, równoległe statystyki, głos i cykle tła.
Bez utraty jakości, danych lub gotowości używanych funkcji. Regresje automatyczne
korzystają z atrap; rzeczywisty provider test zero wymaga osobnego zlecenia
dla każdego uruchomienia zgodnie z [polityką](../PL/PROVIDER_TEST_ZERO_POLICY.md).

Warstwa telemetrii i własność zasobów API:
[opis techniczny](../SINGLE_USER_API_RESOURCES.md).

## Granice bieżącej zmiany

Produkcja oraz pozostałe historyczne warianty nie są teraz domyślnym profilem.
Znana osobna usterka komponentowego celu web przy względnym WEB_DIR/.ONESHELL
i pełna kwalifikacja produkcyjnego UI pozostają odłożone. Nie utożsamiać ich
statusu z odbiorem codziennego Turbo.

Chat 2.0 jest oddzielnym zakresem projektu powłoki. Obecna optymalizacja nie
migruje ekranów, nie dodaje theme i nie uruchamia drugiej instancji frontendu.
