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

Wspólny zestaw obejmuje krótkie prośby i rozmowy z doprecyzowaniem. Dla
każdego wariantu zapisujemy identyczną wersję danych, model bazowy, adapter,
budżet tokenów i wyniki. Raport oddziela przypadki modelowe od tych, które
wymagają narzędzia. Trening może wejść do użycia dopiero po poprawie jakości
polskiego dialogu względem bazy bez pogorszenia chronionych zadań.

Warstwa narzędzi wymaga prób z udanym i nieudanym pobraniem, poprawnym czasem,
źródłami oraz izolacją prywatnego kontekstu. Testy automatyczne stosują
podstawione odpowiedzi sieciowe i nie wysyłają płatnych zapytań.
