# Recenzent GPT‑6 Luna w Academy

Academy rozróżnia lokalnych recenzentów, zdalny protokół
`semantic-openrouter-luna-field-v7` i ocenę `exact-v1`. Nieznany identyfikator
jest błędem. Zdalna recenzja nie przechodzi na porównanie dosłownego tekstu ani
na lokalny model, gdy brakuje kwalifikacji lub połączenia z OpenRouter.

## Trzy osobne odbiory

1. Odbiór danych potwierdza źródła, kryteria i etykiety kontroli.
2. Testy kodu sprawdzają transport, budżet, odtwarzanie dowodów i integrację.
3. Rzeczywista kwalifikacja recenzenta wymaga kompletnego audytu modelu.

Kwalifikacja v7 przypina sprawdzenie cytatów observed względem odpowiedzi.
Wyniki v2–v6 pozostają dowodami historycznymi.

## Kontrole i znaczenie ocen

Kontrole przygotowuje `scripts/academy/prepare_judge_controls.py`. Nowy pakiet
zachowuje historyczne pliki źródłowe i zapisuje własny manifest oraz pochodzenie
napraw. Przygotowanie pierwszej fazy nie odczytuje treści testu odłożonego.

Pierwsza faza obejmuje 60 odpowiedzi legacy, 48 development, 32 dodatkowe
kontrole i 16 kontrastów. Historyczne progi pozostają zachowane. Dodatkowe
kontrasty muszą również przejść w całości. Dopiero pełny PASS pierwszej fazy
pozwala odczytać i ocenić 24 odłożone odpowiedzi po trzy razy.

Brak informacji w źródle jest inną informacją niż potwierdzona odpowiedź
negatywna. Jeśli kryterium wymaga stwierdzenia braku danych, a odpowiedź podaje
niepopartą konkretną wartość, atom ma status `omitted`, a `unsupported` wynosi
`yes`. Samo pominięcie informacji nie wystarcza do `unsupported=yes`.
Odpowiedź sprzeczna z jawnym faktem ma status `contradicted`. Niepoparta wartość
nadal daje negatywny werdykt i alarm krytyczny.

## Audyt operatora

Publiczna ścieżka przygotowania i ręcznego wykonania audytu znajduje się
w `scripts/academy/qualify_openrouter_judge.py`. Pomoc polecenia nie wykonuje
wywołań dostawcy. Przygotowanie przypina dane kontrolne, odbiór danych, prompt, schemat żądania,
implementację, limity i politykę tempa. Raportuje rezerwę fazy 1, holdoutu
i obsługi HTTP 429. Przed pierwszym POST runner sprawdza łączną rezerwę
z uwzględnieniem wcześniejszych kosztów i aktywnego limitu projektu. Uruchomienie audytu
jest osobną, jawną czynnością operatora.

Opis argumentów jest dostępny bez połączenia z dostawcą:

```bash
python -m scripts.academy.qualify_openrouter_judge prepare --help
python -m scripts.academy.qualify_openrouter_judge run --help
```

`prepare` wymaga katalogu kontroli, pliku odbioru danych oraz niezależnie
podanych hashy obu wejść. Przyjmuje nowy katalog wyjściowy, limit USD
i limit czasu. Wymaga także jawnego `--holdout-max-request-usd`, który jest
operacyjnym limitem rezerwacji jednego żądania odłożonego testu.
`run --audit-root ... --execute` jest jawnym wykonaniem
przygotowanej próby. Bez `--execute` nie wykonuje audytu.

Operator wybiera aktualny odebrany pakiet i aktualną recenzję danych.
Poprzednie rewizje i zastąpione recenzje zachowuje się jako historyczne
dowody; nie służą do przygotowania nowej kwalifikacji.

Przed odczytem holdoutu runner sprawdza rezerwę na wszystkie 72 żądania
oraz rezerwę czasu według zamrożonej polityki. Jeśli po odczycie rzeczywisty
pakiet przekroczy ustalony limit pojedynczego żądania, próba kończy się jako
technicznie niekompletna. Nie wysyła tego żądania i zapisuje, że holdout
został już otwarty. Wybrany limit nie jest pomiarem nieodczytanych danych.

Kwoty rozliczone i rezerwy przenoszone z poprzednich prób podaje się przez
`--initial-accounted-usd` i `--initial-unknown-reserved-usd`. Nowy katalog
nie stanowi dowodu wyzerowania kosztów poprzedniej próby.

Adres HTTP to `https://openrouter.ai/api/v1/chat/completions`. Model to
`openai/gpt-6-luna`; dostawca Azure jest wybierany wewnątrz OpenRouter.
Protokół nie wymaga ZDR. Używa istniejącej konfiguracji dostępu do chmury
i poświadczeń OpenRouter. Nie zapisuje klucza w kalibracji ani receiptach.

Audyt zapisuje surowe żądania i odpowiedzi, identyfikatory generacji, czasy,
decyzje, koszty oraz hashe. FAIL, przerwanie i niepełny audyt nie są
kwalifikacją. Weryfikator odtwarza pierwszą fazę przed odczytem holdoutu;
sam wpis `passed` w pliku wyniku nie otwiera tej bariery.

## Kalibracja i użycie w kampanii

Kalibracja przypina odrębny typ `QualificationRemote`. Zawiera identyfikator
v7, model, dostawcę, adres endpointu, katalog audytu oraz hashe protokołu,
wyniku, manifestu kontroli, promptu, kontraktu żądania i implementacji.
Nie wpisuje wersji Ollamy ani fikcyjnego hasha zdalnych wag.

Pole `remote_review` zawiera:

| Pole | Znaczenie |
| --- | --- |
| `ledger_root` | Katalog rozliczenia ocen, uwzględniający początkowy koszt audytu kwalifikacji |
| `budget_usd` | Łączny limit; ogranicza go także konfiguracja OpenRouter |
| `max_request_usd` | Maksymalna rezerwacja pojedynczego żądania |

Przed każdym żądaniem zapisywana jest rezerwacja. Potwierdzony koszt zastępuje
rezerwację po odpowiedzi, a koszt nieznany pozostaje rezerwacją. Odtworzenie
ledgera ma wykrywać zmianę kwot i receiptów. Błąd transportu nie daje częściowej
kwalifikacji ani automatycznej ponownej próby do uzyskania PASS.

Wspólny dispatch obejmuje walidację kalibracji, preflight, ocenę checkpointów,
ponowne użycie ocen M0 i ocenę finału. Tożsamość oceny uwzględnia zdalny
protokół oraz kwalifikację. Ocena z lokalnego sędziego lub poprzedniej wersji
protokołu nie staje się oceną Luny przez zmianę identyfikatora.

Reuse wymaga zgodności całego pakietu, odpowiedzi i własnej historii modelu.
Receipt jest odtwarzany przed użyciem zapisanej oceny. Sama identyczna treść
odpowiedzi nie wystarcza.

## Granice kwalifikacji

Kwalifikacja dotyczy oceniania odpowiedzi względem zamrożonych kryteriów.
Nie nadaje kwalifikacji ocenianemu adapterowi, całemu czatowi W/R, mowie ani
narzędziom. Kampania nadal wymaga danych, właściwej referencji jakości,
retencji i odrębnego odbioru finalisty. Wprowadzenie tego protokołu nie
uruchamia treningu ani automatycznego testu dostawcy.

Audyt operatora uruchamia się z głównego wątku procesu CLI w systemie Linux.
Limit 75 sekund dotyczy całej wymiany HTTP, w tym odczytania odpowiedzi.
Krótkie porcje danych nie odnawiają tego limitu. Przerwany POST zachowuje
rezerwację jako koszt nieznany i zamyka próbę bez ponowienia żądania.

Przy kwalifikacji Academy wykonuje jeden audyt Luny naraz na użytkownika
systemowego, również przy kilku katalogach roboczych. Zachowuje dwie sekundy
przerwy między zwykłymi żądaniami. Wyłącznie po HTTP 429 ponawia ten sam
pakiet najwyżej dwa razy i najwyżej osiem razy w całym audycie. Honoruje
Retry-After do 60 sekund. Przy braku poprawnego nagłówka stosuje 5 i 10 sekund.
Dłuższy Retry-After zatrzymuje audyt i jest zapisany dla kolejnego startu.
Połączenie o nieznanym wyniku, inny błąd HTTP i błąd oceny kończą próbę.
Odrzucone żądania zachowują koszty lub rezerwacje i nie liczą się jako decyzje.
Próby zamrożone przed zmianą zachowują dotychczasowy protokół.

Panel celowany przechodzi przez ten sam limit czasu, tempo i rejestr prób.
Polecenie przygotowania sprawdza hash wejściowego panelu oraz zgodność
wszystkich pakietów z aktualnym kontraktem recenzenta. Użyj podpolecenia
prepare-targeted w scripts.academy.qualify_openrouter_judge, a następnie
podpolecenia run z katalogiem audytu i flagą --execute.

Wynik targeted_review_required wymaga potwierdzenia ręcznego. Ten tryb
nie tworzy pinu kwalifikacji ani nie otwiera holdoutu. Odrzucona decyzja
lub różnica względem klucza nie przerywa zbierania kolejnych niezależnych
ocen. Ograniczenia transportu i budżetu nadal mogą zakończyć próbę wcześniej.
