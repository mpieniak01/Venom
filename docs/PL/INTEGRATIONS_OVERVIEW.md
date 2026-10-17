# Przegląd integracji

Konfiguracja > Integracje i węzły korzysta z GET /api/v1/system/api-map w wersji
schematu 2. Zachowano internal_connections i external_connections. Nowa lista
integrations obejmuje API core, moduły opcjonalne, dostawców i zasoby. Gotowość
połączenia nie jest zgodą na ruch robota.

W moim środowisku pokazuje bieżącą instalację. Wszystkie obsługiwane uwzględnia
możliwości znane z deklaracji core i skonfigurowanych manifestów, także bez
konfiguracji. Nie skanuje marketplace ani nie wykrywa nieznanych modułów.
Pozostałe zakładki konfiguracji zachowują dotychczasowe funkcje.

Konfiguracja, aktywacja modułu, łączność API i stan zasobów są oddzielne. Sama
obecność trasy lub klucza nie oznacza poprawnej łączności. Nieznana liczba zasobów
to null; potwierdzony brak to 0. Lokalne manifesty modułów są widoczne także
bez rejestracji ich API. Integracje bez węzłów pokazują nie dotyczy.
Dane wskazują źródło i czas. Lokalne rekordy Vast są historyczne.

Odczyt mapy korzysta tylko z lokalnych obserwacji i nie uruchamia kamer, modeli,
robota ani wynajmu. Jawne sprawdzenie POST /api/v1/system/integrations/vast/probe
wywołuje istniejącego klienta Vast: wyłącznie GET konta i instancji. Nie tworzy,
nie uruchamia, nie zatrzymuje ani nie usuwa zasobów. Sprawdzenia mają ograniczony
czas oczekiwania, współdzielone żądanie i krótki okres ponawiania. Klucz pozostaje
na serwerze; wynik nie zwraca salda ani prywatnej odpowiedzi dostawcy. Obserwacja
starsza niż 60 s nie potwierdza bieżącej liczby zasobów. Zmiana klucza unieważnia
powiązanie z poprzednią obserwacją. Pozostałe testy dostawców pozostają oddzielne.

Widoczny ekran odświeża dane co 10 s, bez nakładania żądań. Zachowuje wybór
oraz ostatni wynik przy błędzie odświeżenia. Błędny moduł jest izolowany; walidator
autorski nadal zgłasza problemy. Moduł bez poprawnej polityki danych nie jest ładowany.

## Opcjonalne obserwacje modułu

Dotychczasowe moduły nie wymagają zmian. Załadowany moduł może zadeklarować
backend.integration_provider_import w module.json w formacie pakiet.modul:funkcja.
Funkcja async otrzymuje aplikację i zwraca IntegrationObservation lub zgodny JSON.
Pola: observed_at z czasem i strefą, connectivity, resources_complete i resources.
Zasoby mają id, label, kind, state i opcjonalny observed_at. Szczegółowy kontrakt
jest w venom_core/api/schemas/integrations.py oraz dokumentacji EN.

Host izoluje wyjątki, waliduje wynik, nadaje prefiks ID i czeka maksymalnie 0,5 s.
Wynik jest współdzielony przez 10 s. Obserwacje starsze niż 60 s są przestarzałe;
pełna liczba zasobów wymaga czasu obserwacji. Dostawca ma korzystać z istniejących
obserwacji i obsługiwać anulowanie. Nie zmienia wyboru urządzenia, ARM, sesji ani
kamery. Etykiety i identyfikatory nie mogą zawierać sekretów.

Brak dostawcy oznacza dostępne metadane modułu oraz nieznany stan urządzenia.
Pełne obserwacje Rider należą do odrębnego przyrostu w jego repozytorium.

Host ogranicza oczekiwanie na start i zamykanie routera modułu do dwóch sekund.
Błąd oznacza niedostępność danego modułu i kontrolowane 503 na jego trasach;
pozostałe trasy core działają. Osłona nie ukrywa błędów samego core i nie zmienia
trwale współdzielonego kontekstu cyklu życia routera dla innej aplikacji.

## Nawigacja konfiguracji

/config?tab=integrations otwiera przegląd. Starsze tab=apiMap i section=parameters
pozostają obsługiwane. integration, scope, visibility i q zapisują wybór, filtry
i wyszukiwanie w URL. Nieznana zakładka wraca do Usług; brak wybranej integracji
jest opisany wprost. Wstecz przeglądarki przywraca wybór.

Klucz integracji prowadzi do istniejącego edytora przez parameter=NAZWA_KLUCZA.
Wyszukiwanie obejmuje nazwy i opisy, bez wartości i sekretów. Nieudostępniony klucz
ma jawny komunikat; nie rozszerzamy listy kluczy zapisywalnych w backendzie.
Niezapisany formularz pozostaje podczas przełączania zakładek; pełne odświeżenie
strony nadal usuwa niezapisane zmiany. Zapis, Reset, profile usług, Audyt
i Uprawnienia zachowują istniejące endpointy i znaczenie. Wyszukane sekcje otwierają
się automatycznie.

Starszy ENABLE_IOT_BRIDGE / RIDER_PI_* pozostaje niezależny od modułu Rider
i nadal jest używany w bootstrapie core. Nie usuwamy ani nie migrujemy tych kluczy.
Kokpit korzysta z identyfikatorów i obserwacji wspólnego przeglądu; nie wyznacza
integracji z nazw usług. Modele prowadzą do wpisu runtime; nawigacja opcjonalnego
modułu pochodzi wyłącznie z manifestu. Ukryte zakładki nie odpytują przeglądu.

Kontekst zasobu obejmuje configuration, selected, mode (demo/device), source,
reason_code oraz supported/reported/available_capabilities. Brak dowodu możliwości
oznacza null. Online nie nadaje zgody na ruch. Pełna lista skonfigurowanych
urządzeń potwierdza łączną liczbę, lecz aktywne pozostają nieznane, jeśli nie
zaobserwowano stanu każdego urządzenia. Opcjonalne pola configuration i reason_code
obserwacji odróżniają brak urządzeń od błędnej konfiguracji. Starsze hooki działają.

Kolejność wydania: core 263, nawigacja i kontekst 264, adapter modułu 263R. Starszy
core ignoruje opcjonalny hook manifestu i zachowuje sterowanie Rider; nie importuje
adaptera na tej ścieżce.

Przegląd zachowuje opisy połączeń, protokoły, uwierzytelnianie, kierunek,
krytyczność i widoczne listy metod dotychczasowej mapy API. Filtry źródła,
łączności i protokołu uzupełniają widoczność/typ/wyszukiwanie i są zapisywane
w URL. Rejestracja tras i konfiguracja kluczy pozostają odrębne od pomiaru
zdrowia. Zmiana zakładki konfiguracji czyści wyszukiwanie poprzedniej zakładki.
