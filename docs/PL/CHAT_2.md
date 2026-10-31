# Venom Chat 2.0

Chat 2.0 to wspólna obsługa rozmowy tekstowej, materiałów i głosu. Jest dostępna
jako opcjonalna powłoka `/chat2` w Venomie oraz osobna aplikacja Studio.
Obie używają jednego kontrolera rozmowy, adapterów dostawców i historii wybranego
środowiska. Studio ma własną aplikację Next i mniejsze wejście FastAPI:
[instrukcja uruchamiania Venom/Studio](STUDIO.md).

## Włączenie i powrót

Osobną aplikację uruchamia `make start-studio`, a zatrzymuje `make stop-studio`.
Powrót: po zatrzymaniu Studio użyj `make start-venom`. Jawne warianty wybierają
własną kompozycję frontendu/API. Studio zawiera wyłącznie trasy rozmowy
i nie ma linku do klasycznego `/chat`.

Opcjonalna trasa w obecnym `web-next` nadal używa `NEXT_PUBLIC_FEATURE_CHAT2`,
domyślnie `false`. Ustaw dokładnie `true` dla tego UI. Flaga trafia do buildu
Next: wymaga restartu UI developerskiego lub przebudowania zatrzymanego gotowego
UI z tą samą flagą. Sama zmiana środowiska uruchomionego artefaktu nie włącza
linku po stronie klienta. Dla skonfigurowanego, zatrzymanego historycznego wejścia:

```bash
NEXT_PUBLIC_FEATURE_CHAT2=true make start PROFILE=full ENVIRONMENT=dev
```

Jawny wariant `start-venom` ustawia tę flagę na `false`; osobnego Studio używa
`start-studio`. Szablony pozostają w `.env.dev.example`, `.env.preprod.example`
i `web-next/.env.local.example`. Stosuj launcher właściciela instancji i zachowaj
ustawienia środowiska. Bez kopiowania prywatnej konfiguracji i przebudowywania
artefaktu aktywnego UI.

W profilu Full wyłączona trasa `/chat2` zwraca 404 i nie ma pozycji menu, a `/chat` pozostaje
dostępny; **Dotychczasowy Venom** prowadzi do niego. Wyłączenie tego wejścia albo
zatrzymanie Studio i powrót do Venoma nie kasują historii serwera, materiałów
ani wyboru dostawcy. Szkice używają wspólnych kluczy na tym samym originie.
Migracja historii nie jest potrzebna. Szczegóły: [profile stosu](STACK_PROFILES.md)
i [cykl budowania UI](WEB_LIFECYCLE.md).

## Rozmowa i runtime

Lista rozmów pozwala wrócić do wątku lub utworzyć nowy. Obie powłoki używają
tej samej tożsamości sesji i szkicu. Udane tury Direct są zapisywane w hostowym
SessionStore przed zgłoszeniem zakończenia: zachowywany jest oryginalny tekst
użytkownika i identyfikatory materiałów, a nie rozwinięte dokumenty czy obrazy
base64. Zatrzymana częściowa odpowiedź może zachować status `CANCELLED`.
Odzyskiwanie szkicu w przeglądarce jest udogodnieniem, nie kopią zapasową historii
serwera.

Wybierz silnik i model, potem **Zastosuj model**. Powłoka korzysta z istniejącego
katalogu, kontroli dostępu do runtime i budżetów. Zmiana modelu zachowuje szkic
i pliki; niezgodny wybór blokuje wysłanie z wyjaśnieniem.

| Tryb | Zakres |
| --- | --- |
| Direct | Rozmowa przez wybrany adapter; w tym trybie przekazywane są obsługiwane materiały. |
| Normal | Dotychczasowa orkiestracja, jeżeli dany runtime ją obsługuje. |
| MAF | Dotychczasowa ścieżka złożonych zadań, zależna od dostępności backendu i polityki. |

Obecne adaptery OpenRouter i Vast działają wyłącznie w Direct. Normal/MAF nie
przyjmują referencji materiałów; dołączenie plików nie przełącza po cichu trybu
ani dostawcy. Ten sam host nadal zarządza jednym aktywnym przebiegiem
runtime/generacji. **Stop odpowiedzi** dotyczy pracy tej rozmowy, a nie globalnego
awaryjnego zatrzymania kolejki.

Panel kosztów pokazuje znane ceny i rozliczenia z istniejącego kontraktu
dostawcy. **Nieznana cena nie oznacza usługi bezpłatnej.** Wyceny, rezerwacje
i usage pozostają kontrolowane przez serwer; zatrzymanie płatnego żądania o
nieznanym rozliczeniu nie zmienia kosztu oczekującego na zero. Otwarcie powłoki
lub wybór modelu nie uruchamia płatnego testu ani monitorowania konta.

## Materiały

Przeciągnij pliki do Materiałów lub użyj **Dodaj pliki**. Upload tworzy referencję
należącą do sesji; do jednej tury wybierz maksymalnie **cztery identyfikatory
materiałów**. Podgląd, odłączenie i usunięcie są osobnymi czynnościami. Brakująca
lub usunięta referencja blokuje wysłanie zamiast znikać po cichu. Nowa rozmowa ma
własne materiały.

| Wejście | Wdrożona ścieżka |
| --- | --- |
| TXT, MD, CSV, JSON | Tekst UTF-8 dołączany do kontekstu; bez automatycznego RAG i wykonywania aktywnej zawartości. |
| PNG, JPEG, WebP | Obrazy przez obsługiwany lokalny adapter Ollama, po sprawdzeniu w metadanych możliwości vision wybranego modelu. |
| PDF, Office, SVG/HTML, pliki audio/wideo | Niedostępne w tym adapterze materiałów. |
| Obrazy przez OpenRouter, Vast i inne zdalne adaptery | Niedostępne; obsługa tekstu lub deklarowana multimodalność modelu nie uruchamia transportu ani rozliczania obrazów. |

Każdy plik ma limit **8 MiB**; dokument musi też być poprawnym UTF-8 i mieścić
się w **64 000 znaków**. Wykonywana tura wraz z rozwiniętym tekstem referencyjnym
ma limit **50 000 znaków**, a uwzględniona historia tekstowa wraz z bieżącą turą
— **64 000 znaków**. Łączny payload referencji materiałów ma limit **16 MiB**.
Wybrany model/runtime może mieć mniejszy kontekst. Samo przyjęcie uploadu nie
gwarantuje więc, że każda kombinacja zmieści się w turze; skróć wiadomość lub
odłącz część plików po przekroczeniu kontekstu. Obrazy są walidowane/dekodowane
i mają limit 20 megapikseli. Sesja przechowuje maksymalnie 32 pliki i 64 MiB.
Nadal obowiązuje tryb preprod tylko do odczytu.

Zmiana modelu, powrót do `/chat` i wyłączenie Chat 2.0 nie kasują materiałów.
Usunięcie pliku rzeczywiście usuwa materiał, więc stare referencje historii mogą
stać się niedostępne. To osobna operacja od wycofania powłoki.

## Dyktowanie i głos

Głos korzysta z istniejącej ścieżki **STT → wspólny kontroler rozmowy → TTS**.
Nie jest natywnym audio modelu; model tekstowy może współpracować ze
skonfigurowanym rozpoznawaniem i syntezą mowy. Przeglądarka wymaga zgody na
mikrofon i bezpiecznego kontekstu. Gotowość usług i błędy są widoczne.

- **Dyktuj szkic**: świadomie nagraj fragment i zakończ go. Transkrypcja staje się
  edytowalnym tekstem; dyktowanie nie wysyła wiadomości automatycznie.
- **Rozmowa głosowa**: wybierz **Nagraj turę**, potem **Zakończ turę**. Transkrypcja
  jest wysyłana tym samym kontrolerem rozmowy, a kwalifikująca się zakończona
  odpowiedź jest odczytywana. Kolejną turę nagraj świadomie; mikrofon nie włącza
  się ponownie po odtwarzaniu.
- **Wycisz mikrofon**, **Stop odpowiedzi** i **Zakończ głos** mają różne skutki.
  Koniec trybu zwalnia nagrywanie i odtwarzanie oraz unieważnia oczekujące
  callbacki. Stop nie pozwala, by spóźniona transkrypcja, odpowiedź lub dźwięk
  wznowiły dawną turę.

Otwarcie strony ani panelu głosu nie pyta o mikrofon, nie nagrywa i nie włącza
ciągłego nasłuchu. Gotowość STT/TTS nie oznacza natywnego audio modelu ani obsługi
uploadowanych plików audio/wideo.

## Kwalifikacja

Testy unit, komponentowe i przeglądarkowe na atrapach API potwierdzają kontrakty.
Nie kwalifikują rzeczywistego mikrofonu, jakości dostawcy, trafności vision ani
płatnego wykonania. Rzeczywisty Test Zero wymaga osobnego zlecenia operatora na
każde uruchomienie: [polityka testów dostawców](PROVIDER_TEST_ZERO_POLICY.md).
Ta instrukcja nie deklaruje końcowego odbioru wydajności ani wydania B07.

[English guide](../CHAT_2.md)

[Odbiór lokalny i ograniczenia pomiarów](../CHAT_2_ACCEPTANCE.md).
