# Gemma 4 E4B w Venomie

Decyzja z **2026-11-07**. Do lokalnego pilotażu wybrano bazowy model
`gemma4:e4b` przez Ollamę, z kontekstem 4096 i jednym żądaniem naraz.
Rozgrzewamy model przed sesją. Kandydat jest aktywny w lokalnym profilu pilota.
Standardowa konfiguracja dev nadal wskazuje `gemma4:12b-it-q4_K_M`.

| Element | Ustalenie |
|---|---|
| Artefakt pilota | GGUF Q4_K_M, bez adaptera |
| Digest manifestu Ollama | `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c` |
| Osobny checkpoint do eksperymentów treningowych | `google/gemma-4-E4B-it`, rewizja `ee0ef6023621cff504d758262d4e04895a5af4a2` |
| Rola | Przyjazny asystent PL/EN do rozmów, informacji ogólnych, pracy z dokumentami i objaśniania wyników diagnozy |
| Narzędzia | W pilotażu tylko jawnie wybrane funkcje odczytu FileSkill. Zakres i uprawnienia sprawdza Venom. |
| Punkt odniesienia | Bazowa Gemma 4 12B. Adapter E4B QLoRA z kroku 125 zachowujemy jako kandydat badawczy. |

Przypięcie checkpointu HF określa bazę treningową. Digest GGUF identyfikuje
lokalny artefakt inferencyjny. Mamy dwie osobne tożsamości do odtworzenia.

## Podstawa wyboru

- Na 16 zadaniach w trzech rundach bazowy E4B zaliczał 15/16, a bazowy 12B
  14/16. Mediana czasu do pierwszego tekstu w czacie i pracy z dokumentem po
  rozgrzaniu wyniosła 64 ms dla E4B i 160 ms dla 12B. Zimny start E4B w tej
  pojedynczej próbie trwał dłużej. Dowód lokalny
  `data/training/gemma4-gguf-serial-20261107/REPORT.md`.
- Przez API Venoma potwierdzono czat PL/EN i RAG na kontrolowanych notatkach.
  Próby z krótkim budżetem odpowiedzi wymagały jawnego ustawienia
  `reasoning_effort=none`. Odczyt, listowanie, istnienie pliku i odmowy poza
  workspace potwierdzono z ograniczonym katalogiem. E4B potrafił błędnie
  opisać dowiązania jako katalogi mimo poprawnego wyniku FileSkill. Dowody
  lokalne `data/training/gemma4-e4b-venom-pilot-20261107/REPORT.md` oraz
  `data/training/gemma4-e4b-venom-pilot-20261107/scoped-list-exists-51f7b062/REPORT.md`.
- E4B QLoRA125 na G05 V2 poprawił własną bazę w zdalnej diagnostyce G04
  z 3/112 do 13/112. To za mało do kwalifikacji operatora. Dotychczasowe
  wyniki tego adaptera pochodzą z odrębnych konfiguracji zdalnego NF4 i
  lokalnego MLX INT4. Porównanie z bazowym GGUF w docelowym runtime pozostaje
  otwarte. Dowód lokalny `data/training/gemma4-pilot-session-20261103/SESSION_REPORT.md`.

## Tryby czatu i profil uruchomienia

- **Direct** przekazuje ostatnie pełne tury w ramach budżetu kontekstu i zwraca
  strumień bez automatycznego RAG i orkiestracji. Zapis rozmowy na hoście
  poprzedza zakończenie strumienia, a indeksowanie pamięci sesji nie blokuje
  wysłania kolejnej wiadomości. Czyszczenie sesji kończy się po trwającym
  indeksowaniu, a spóźniony zapis usuniętej tury jest odrzucany.
- **Normal** korzysta z historii, streszczenia i pamięci RAG. Przy pytaniu
  o nazwane źródło dobiera wpisy z bieżącej sesji i pamięci globalnej.
  Jeśli brakuje pasującego wpisu, model otrzymuje informację o braku źródła.
  Wynik FileSkill może być pełny, częściowy albo zawierać odmowę.
- **Complex** prowadzi zadania wymagające planowania istniejącą ścieżką
  `COMPLEX_PLANNING`. **Full** to osobny wymiar konfiguracji i nadal określa
  zakres usług uruchamianego stosu.

[Sesje czatu](CHAT_SESSION.md) · [Profile stosu](STACK_PROFILES.md)

## Decyzja o dotrenowaniu

**Odłożyć kolejny trening.** Najpierw domknąć zachowanie zwykłego czatu
i warstwę kontekstu w Venomie. Ostatnie tury, streszczenie starszego wątku,
pobieranie źródeł RAG, filtr sesji i budżet 4096 należą do aplikacji.
Wiedzę z dokumentów aktualizujemy w źródłach RAG. Poprawność wykonania,
uprawnienia i blokady nadal potwierdza kod.

Następnie zmierzyć bazę na nowych, zamrożonych przypadkach PL/EN. Sprawdzić
przyjazne odpowiedzi ogólne, dopytywanie, długą rozmowę i zmianę wcześniejszych
ustaleń, korzystanie ze źródeł oraz rozróżnienie wyniku narzędzia od hipotezy.
Jeśli w poprawnie złożonym kontekście zostaną powtarzalne błędy modelu,
zakres małego SFT/QLoRA może objąć:

1. Naturalną, zwięzłą odpowiedź w języku użytkownika oraz dopytanie przy
   rzeczywistym braku informacji.
2. Zachowanie decyzji, korekt i otwartych pytań podczas streszczania.
3. Odpowiedź opartą na źródle, zgłoszenie braku danych i wierne objaśnienie
   potwierdzonego wyniku narzędzia, w tym odmowy, błędu lub częściowego wyniku.

Materiał czerpać ze zweryfikowanych przebiegów. Oddzielić rodziny zadań
treningowych od zestawu końcowego. Adapter rozważać do pilotażu dopiero po
porównaniu z bazą w tej samej konfiguracji inferencji, z oceną dokładności,
języka, czasu do pierwszego tokenu i regresji ogólnych kompetencji. Umiejętność
naprawiania kodu Venoma to osobna kwalifikacja na rzeczywistych usterkach.

[Kontrakt modelu i treningu](../GEMMA4_OPERATOR.md) ·
[Katalog danych treningowych](DANE_TRENINGOWE.md)
