# Polski czat: jakość języka i aktualne źródła

## Cel i stan wyjściowy

Jakość czatu oceniamy na naturalnych polskich zadaniach, z osobnymi wynikami dla
języka, wykonania prośby, historii rozmowy, faktów i zakończenia wypowiedzi.
Archiwum Venoma zawiera głównie rozmowy testowe i nie służy do szacowania potrzeb
polskich użytkowników. Badanie źródeł i liczb pozostaje prywatne.

Następnego adaptera nie wolno wybierać na podstawie samego ubytku ucięć;
potrzebna jest ocena jakości naturalnych dialogów i zachowania historii.

## Strumień A: dane i trening LoRA

1. Zamrozić zestaw przypadków oceny przed doborem przykładów treningowych.
   Oznaczyć pytania wymagające danych bieżących, aby nie liczyć braku dostępu
   do sieci jako błędu polszczyzny modelu.
2. Pozyskiwać naturalne polskie pytania i doprecyzowania z licencjonowanych
   źródeł, w szczególności WildChat. Przed użyciem przeprowadzić przegląd
   prywatności, języka całego dialogu i jakości odpowiedzi. Odpowiedzi modelu
   w publicznym korpusie nie są automatycznie wzorcami treningowymi.
3. Dla wzorców odpowiedzi stosować jawny przegląd jakości i pochodzenie.
   PLLuMIC wymaga dostępu do danych; OASST2 i Aya mogą uzupełniać materiał.
   Każdy rekord treningowy musi spełniać schemat Academy (`quality_status`,
   `review_note`, źródło, wersja, licencja i grupa). Grupy rozmów, parafrazy
   i dokumenty źródłowe nie mogą przechodzić między train, dev i holdout.
4. Uczyć odpowiadania po polsku, korzystania z historii i zwięzłego kończenia
   odpowiedzi. Wiedza faktograficzna wymaga osobnego sprawdzenia źródła.
   Pełny zrzut Wikipedii nie jest wejściem pilota LoRA.
5. Uruchomić próbę dopiero z zatwierdzonymi danymi i bazową oceną. Na RTX 3060
   roboczy limit całego rekordu to 1280 tokenów; 2048 wymaga osobnej próby
   stabilności. Nie zmieniać limitu nadzorowanych tokenów bez audytu receptury.

### Wizja na później: wiedza z polskiej Wikipedii

Osobnym kierunkiem badawczym jest wzbogacenie trwałej wiedzy i polskiego
słownictwa modelu na oczyszczonym korpusie polskiej Wikipedii. Nie jest to
część obecnego pilota LoRA ani źródło wzorcowych dialogów. Przed ewentualną
próbą trzeba przygotować odrębną recepturę dalszego treningu językowego,
przypięty zrzut z pochodzeniem i licencją oraz porównanie wiedzy, jakości
dialogu i odpowiedzi z artykułem podanym w kontekście. Na razie nie pobieramy
zrzutu i nie uruchamiamy treningu Wiki.

## Strumień B: źródła bieżące w zwykłym czacie

Zasady wyboru źródeł w interfejsie opisuje
[instrukcja operatora czatu](CHAT_OPERATOR.md#źródła-publiczne-w-studio-normal).

- Pytania o pogodę korzystają z narzędzia pogodowego. Odpowiedź podaje
  lokalizację, czas odczytu oraz dostawcę danych.
- Pytania o bieżące wydarzenia, ceny, obecne osoby na stanowiskach i inne
  zmienne fakty kierują do wyszukiwania. Wersja bezpłatna korzysta z obecnej
  ścieżki DuckDuckGo. Odpowiedź wymaga daty i linków do przeczytanych źródeł.
  Dla ogólnego pytania o wiadomości ze świata, gdy nie da się potwierdzić
  artykułów, można podać wyłącznie świeże nagłówki z kanału RSS BBC z datą
  i linkiem, jawnie zaznaczając, że pełnych artykułów nie przeczytano.
- Pytania o wiedzę ogólną mogą pobrać odpowiednią stronę polskiej Wikipedii.
  Trzeba zachować URL, tytuł i atrybucję. Jeśli nie znaleziono źródła,
  czat może odpowiedzieć z wiedzy modelu, jasno oznaczając niepewność.
- Do publicznego wyszukiwania przekazywać tylko bieżące pytanie potrzebne do
  zapytania. Historia sesji, notatki użytkownika i wyniki prywatnych narzędzi
  pozostają poza treścią zapytania. Pobrana strona jest danymi, nie instrukcją
  dla asystenta.
- Awaria narzędzia nie może przejść w udawanie świeżej informacji. Odpowiedź
  ma ujawnić brak aktualnego źródła.

Zalogowana karta Google nie jest interfejsem API wyszukiwania. Publiczny
`Custom Search JSON API` jest zamknięty dla nowych klientów. Automatyzacja
wyników zwykłej wyszukiwarki nie jest planem wydania.

## Bramka jakości

Protokół `semantic-local-v6` wykonuje dwa osobne zapytania do tego samego
przypiętego modelu: ocenę faktów v5 oraz kontrolę polaryzacji i wykonania
instrukcji z materiału. Kontroler otrzymuje oryginalny materiał bez werdyktu
pierwszej oceny. To rozdziela zadania, ale nie dowodzi niezależności błędów
tego samego modelu.

Kontroler cytuje aktualne źródła oraz pełne, mechanicznie wydzielone zdania
kandydata. Wycięcie samej nazwy z zanegowanego zdania jest odrzucane.
Sprzeczny fakt lub wykonanie instrukcji z materiału ma prawo weta; inne
rozbieżności między ocenami dają nierozstrzygnięcie i blokują kwalifikację.
Segmentacja zdań nie stanowi samodzielnej analizy językowej. Skuteczność
całości musi potwierdzić osobny audyt.

Audyt v6 wymaga 60 kontroli legacy, 48 rozwojowych i 32 dodatkowych przed
otwarciem 24 odłożonych odpowiedzi ocenianych trzykrotnie. Łącznie są to
212 decyzji i 424 odrębne wywołania. Zachowuje pełne requesty, odpowiedzi,
tożsamość modelu, hashe kodu i kolejność obu etapów. Częściowy ślad jest
zapisywany przed każdym wywołaniem i po nim; awaria drugiego nie usuwa
dowodu pierwszego i nie powoduje automatycznego retry.

Kod v6 nie oznacza uzyskanej kwalifikacji. Wymagany jest prawdziwy receipt
całego mechanizmu, wskazany w środowisku procesu przez
`VENOM_ACADEMY_JUDGE_V6_AUDIT_ROOT`. Receipt starszej wersji go nie zastępuje.
Przygotowanie audytu dopuszcza limit do 3600 s z rezerwą cleanup 120 s;
wersje v4/v5 zachowują dotychczasowy limit 1500 s. Testy na atrapach nie
stanowią audytu rzeczywistego modelu.

Wspólny zestaw obejmuje krótkie prośby i rozmowy z doprecyzowaniem. Dla
każdego wariantu zapisujemy identyczną wersję danych, model bazowy, adapter,
budżet tokenów i wyniki. Raport oddziela przypadki modelowe od tych, które
wymagają narzędzia. Trening może wejść do użycia dopiero po poprawie jakości
polskiego dialogu względem bazy bez pogorszenia chronionych zadań.

Warstwa narzędzi wymaga prób z udanym i nieudanym pobraniem, poprawnym czasem,
źródłami oraz izolacją prywatnego kontekstu. Testy automatyczne stosują
podstawione odpowiedzi sieciowe i nie wysyłają płatnych zapytań.

## Jawna precyzja wyniku i brakujące wejścia
Kalkulator zachowuje dokładną wartość dowodu. Pilot może powiązać zaokrąglone roszczenie tylko z jawnym poleceniem bieżącego użytkownika `do N miejsc po przecinku` (0–6) i jednoznaczną jednostką wyniku. Stosuje dziesiętne ROUND_HALF_UP; widoczna odpowiedź musi mieć żądaną precyzję. Przecinek dziesiętny i powtórzona zgodna jednostka są normalizowane, błędna wartość/jednostka pozostaje blokowana. Protokół precyzji trafia także do recenzji semantycznej. Konwersja liczebności na procent nie jest domniemywana.

Żądany całkowity koszt lub nazwany wynik procentowy nie może być wymaganym wejściem do własnego obliczenia. Ten filtr nie usuwa brakującej ceny dojazdu, liczebności ani stawki procentowej potrzebnej w rachunku. Rozpoznanie języka jest ograniczone; niezależna recenzja planu i odpowiedzi pozostaje obowiązkowa. Testy kontrolowane nie upoważniają do pomijania recenzji przy rzeczywistym modelu.

Pozostałe zgłoszone braki nazwane jako procent lub udział, przy jawnym żądaniu wyniku procentowego, przechodzą fazę `input_roles`. Inne operandy (np. nieznany koszt dojazdu) nie mogą zostać usunięte przez tę fazę. Adapter modelu obsługuje schemat `InputRoles` i instrukcję `INPUT_ROLES_GUIDANCE`. Model musi sklasyfikować każdą etykietę dokładnie raz; odrzucenie jej jako szukanego wyniku wymaga literalnego cytatu bieżącej prośby. Role `input` i `uncertain` zachowują dopytanie. Pełny ślad trafia do niezależnej recenzji; klasyfikacja roli nie potwierdza sama poprawności wyrażenia ani odpowiedzi.
