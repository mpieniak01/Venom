# Polski asystent multimodalny Venoma — Omni i Gemma 4 E4B

[English version](../EN/POLISH_MULTIMODAL_ASSISTANT_EXPERIMENT.md)

Raport porównuje lokalne profile **LiquidAI LFM3-Omni-2B** i **Gemma 4 E4B** w Venom Studio i pełnym Venomie (Full). Obejmuje sparowany pomiar z 11 listopada 2026 r., wcześniejsze próby jakości i zamknięcie pilotażu treningu Omni.

W powtórce Ollamy oba modele zaczynały bez wag w pamięci. Mediana do pierwszej treści to **2,882 s dla Omni i 11,532 s dla Gemmy** przy zimnym modelu oraz **0,032 s i 0,105 s** po załadowaniu. W osobnej, większej próbie jakości Gemma zaliczyła **254/280 (90,71%)**, Omni **209/280 (74,64%)**. Wyniki są opisane według protokołu, którego dotyczą.

## Sprzęt, modele i sposób oceny

- Jeden host Windows 11 z Ubuntu w WSL2, RTX 3060 z 12 GiB VRAM i lokalną Ollamą 0.40.14. Próby Chrome odtwarzały te same nagrania przez wirtualny mikrofon. Poszczególne konfiguracje uruchamiano kolejno.
- Testowane tagi Ollamy to `lfm3-omni:2b` i `gemma4:e4b`. Oba pakiety miały oznaczenie GGUF Q4_K_M. Zapisane rozmiary pakietów to odpowiednio ok. 2,05 GB i 6,58 GB na dysku.
- `pl-assistant-v1` zawiera 48 scenariuszy walidacyjnych i 200 końcowych. Podziały mają odrębne rodziny przypadków, dokumenty i syntetyczne głosy. Część nagrań ma szum 18 dB SNR. Sumy manifestów i mediów ustalono przed pomiarem. Rezerwowy zestaw B do oceny adapterów głosowych pozostał zamknięty.
- Ścisłe trafienie uwzględnia poprawność wartości i formatu po normalizacji do słów. Dodatkowa etykieta lub niepoprawna odmiana może obniżyć wynik. WER to stopa błędów słów w transkrypcji. Osobno sprawdzaliśmy zachowanie kluczowych nazw, liczb i relacji, ponieważ pojedyncze słowo może zmienić znaczenie.
- GPU oznacza szczyt użycia całego urządzenia, a RAM użycie WSL jako `MemTotal − MemAvailable`. Obie liczby obejmują pozostałe procesy hosta. Modelowe próby i odsłuch prowadziliśmy osobno od bramek kodu.

## Pomiar sparowany Ollamy — od pustej pamięci do zwolnienia modelu

Próba z 11 listopada 2026 r., rewizja Venoma `4b57d8c3`, Ubuntu-Venom w WSL2, RTX 3060 12 GiB (sterownik 621.14) i lokalna Ollama 0.40.14. Osobna instancja Ollamy korzystała z tych samych dwóch przypiętych pakietów. Produkcyjny Venom nie miał aktywnych tur i nie uczestniczył w pomiarze. Przed próbą zwolniono jego bezczynny model, po próbie odtworzono wcześniejszy stan.

1. Przed pomiarem załadowano i zwolniono oba pakiety po jednym razie. Pamięć podręczna plików systemu pozostała aktywna. Zimna tura oznacza brak modelu w `/api/ps`; nie mierzy startu systemu ani pierwszego odczytu z dysku.
2. W sześciu parach zamieniano kolejność Omni → Gemma i Gemma → Omni. Każdą próbę rozpoczynano z pustym `/api/ps`. Oba modele dostały tę samą krótką prośbę o definicję kwadratu: jedna tura na raz, temperatura 0, ziarno 42, kontekst 4096, limit 128 tokenów, bez trybu rozumowania. Zachowano szablony i ustawienia właściwe pakietom, w tym dołączony wariant dekodowania Gemmy.
3. Po pierwszej turze każdy model wykonał tych samych osiem scenariuszy z bloku walidacji, a następnie ponownie odpowiedział na pytanie o kwadrat. Przed następnym ramieniem wysłano żądanie zwolnienia i czekano na pusty `/api/ps`. Log wykonania potwierdził przeniesienie wszystkich warstw modelu językowego na CUDA (Omni 25/25, Gemma 43/43). Bufory w RAM są częścią obu profili.

| Metryka (6 powtórzeń na model) | Omni | Gemma E4B |
| --- | ---: | ---: |
| Zimny start · czas ładowania zgłoszony przez Ollamę, mediana (min–max) | 2,787 s (1,721–6,291) | 11,146 s (8,735–18,283) |
| Zimny start · czas do pierwszej treści, mediana (min–max) | 2,882 s (1,815–6,429) | 11,532 s (8,946–18,686) |
| Zimny start · pełna odpowiedź, mediana (min–max) | 2,998 s (1,927–6,592) | 12,113 s (9,514–19,439) |
| Model w pamięci · pierwsza treść, mediana (min–max) | 0,032 s (0,030–0,037) | 0,105 s (0,055–0,127) |
| Model w pamięci · pełna odpowiedź, mediana (min–max) | 0,146 s (0,139–0,155) | 0,637 s (0,587–0,696) |
| Model w pamięci · tempo dekodowania, mediana | 214,2 tokena/s | 71,3 tokena/s |
| Zwolnienie · żądanie → pusty `/api/ps`, mediana (min–max) | 0,070 s (0,065–0,134) | 0,383 s (0,377–0,406) |

Czas do pierwszej treści obejmuje wysłanie żądania i otrzymanie pierwszej treści w strumieniu. Odpowiedzi miały odpowiednio 24 i 38 tokenów. Tempo dekodowania pochodzi z licznika pakietu i zależy od tokenizera. Zakres min–max pokazuje rozrzut sześciu powtórzeń.

| Pamięć · cały GPU / WSL, mediana po 6 cyklach | Omni | Gemma E4B |
| --- | ---: | ---: |
| GPU przed zimną turą · mediana (min–max) | 2 039 MiB (2 033–2 163) | 2 090 MiB (2 038–2 163) |
| GPU · szczyt zimnej tury / przyrost względem stanu przed turą | 5 036 / +2 996 MiB | 6 722 / +4 633 MiB |
| GPU · szczyt przy załadowanym modelu, blok walidacji | 5 076 MiB | 6 766 MiB |
| RAM WSL przed zimną turą | 1 250 MiB | 1 246 MiB |
| RAM WSL · szczyt zimnej tury / przyrost względem stanu przed turą | 1 757 / +506 MiB | 4 733 / +3 424 MiB |
| RAM WSL · szczyt przy załadowanym modelu, blok walidacji | 1 951 MiB | 4 730 MiB |

GPU i RAM próbkowano co około 100 ms. Przyrost liczono dla każdego cyklu, po czym brano medianę, stąd może różnić się od różnicy zaokrąglonych median. Po każdym zwolnieniu odczytano pusty `/api/ps`; użycie GPU po zwolnieniu wróciło do 2 033–2 163 MiB. Próbki obejmują tło hosta, krótkie szczyty między odczytami mogą zostać pominięte. Są to pomiary toru Ollamy; pamięć aplikacji i dodatkowych komponentów mowy mierzono oddzielnie.

W tych samych cyklach powtórzono 48 zablokowanych scenariuszy walidacyjnych na model, na tekście wzorcowym i tam, gdzie dotyczy, z tym samym PNG, dokumentem i historią. W zadaniach narzędziowych wynik funkcji pochodził z danych testowych. Nie przekazywano nagrań w tej części.

| Zadanie · wejście wzorcowe | Omni | Gemma E4B |
| --- | ---: | ---: |
| Rozmowa | 10/10 | 10/10 |
| Dokumenty | 7/8 | 8/8 |
| Polecenia głosowe jako tekst | 7/10 | 6/10 |
| Obraz i pytanie jako tekst | 9/10 | 8/10 |
| Narzędzia i odpowiedź | 10/10 | 10/10 |
| **Łącznie** | **43/48** | **42/48** |

Wynik walidacji dotyczy tej macierzy i profilu Ollamy. Większy zbiór poniżej mierzy inny zakres, w tym wejście głosowe.

## Studio i Full — sparowane nagrania na rewizji pomiarowej

W tej samej rewizji odtworzono 68 tur w Google Chrome 146.0.7680.80 na WSL2. W każdym interfejsie były cztery pary, w kolejności Omni → Gemma, Gemma → Omni, Omni → Gemma, Gemma → Omni. Ramiona korzystały z osobnych procesów API, pustego stanu rozmowy i identycznych nagrań podanych przez wirtualny mikrofon. Każdy zimny cykl zaczynał się od pustego `/api/ps` po gotowości backendu. Na rozgrzanym modelu powtórzono ten sam plik `V-S01-1` i wykonano po 10 wspólnych przypadków walidacyjnych na konfigurację. Jedno rozgrzane odtworzenie `V-S01-1` należy do obu zestawień. Po cyklu sprawdzono zwolnienie modelu. Przygotowanie pamięci plików było wspólne jak w próbie Ollamy.

Studio używało Chat 2.0 (PCM przez HTTP), a Full widoku Voice w trybie Direct (WebM/Opus przez `/ws/audio`). Wejście porównywano **w obrębie tego samego interfejsu**. Studio z Omni używało natywnego ASR i głosu Omni (24 kHz); Studio z Gemmą — Whisper medium CUDA i Piper (22,05 kHz). Full potwierdzał natywne ASR Ollamy na każdej zaakceptowanej turze: Omni z natywną syntezą (24 kHz), Gemma z Piperem (22,05 kHz). W Studio pierwsza tura Gemmy obejmuje inicjalizację Whispera i Pipera na żądanie. Full przed każdą próbą zakończył zwykłą rozgrzewkę pomocniczego Whispera i Pipera dla obu profili, a ewentualnie załadowane przy starcie wagi Ollamy zwolniono przed pomiarem. Test dotyczy zimnego modelu Ollamy w gotowej aplikacji. Studio i Full zmierzono w osobnych seriach, bez porównywania stanów startu obu aplikacji. Pakiety i tory mowy są takie jak w profilach aplikacji, dlatego poniższe czasy obejmują też ASR, generowanie tekstu i syntezę.

Mierzymy od wysłania tury po zakończeniu nagrania do `playing` w Studio albo zaplanowanego startu źródła w działającym `AudioContext` w Full. Osobno mierzymy gotowy WAV HTTP w Studio i pierwszą odebraną porcję audio w Full. Są to zdarzenia przeglądarki, nie pomiar czasu na fizycznym głośniku. Czasy w tabeli obejmują wyłącznie przypadki, dla których odtworzenie potwierdzono w obu ramionach danej pary; w nawiasie jest liczba par. P95 metodą najbliższej rangi przy 10 parach to najwolniejsza z nich.

| Interfejs | Profil | Zimny WAV kontrolny · start audio, s: mediana (min–max; n) | Ten sam WAV po załadowaniu · start audio, s: mediana (min–max; n) | Rozgrzana walidacja · start audio, s: mediana / p95 (n) | Rozgrzana walidacja · audio z API, s: mediana / p95 (n) |
| --- | --- | ---: | ---: | ---: | ---: |
| Studio | Omni | 6,248 (3,488–8,586; 4) | 0,867 (0,739–1,466; 4) | 0,921 / 1,701 (10) | 0,916 / 1,696 (10) |
| Studio | Gemma E4B | 28,632 (26,649–29,005; 4) | 1,030 (0,976–1,164; 4) | 1,107 / 1,246 (10) | 1,103 / 1,240 (10) |
| Full | Omni | 1,931 (1,501–2,075; 4) | 0,782 (0,716–0,823; 4) | 0,856 / 1,323 (10) | 0,853 / 1,312 (10) |
| Full | Gemma E4B | 6,122 (5,156–6,560; 4) | 0,876 (0,783–3,396; 4) | 1,022 / 3,008 (10) | 1,018 / 2,961 (10) |

Ścisła odpowiedź i WER dotyczą dziesięciu rozgrzanych nagrań. WER jest średnią po dostępnych transkrypcjach; licznik kluczowej treści uwzględnia wszystkie próby. Rozpoczęcie odtwarzania nie oznacza poprawnej treści. Na czas ma też wpływ długość wygenerowanej odpowiedzi.

| Interfejs | Profil | Odtworzono · zimne / rozgrzana walidacja / ciepła kontrola | Ścisła odpowiedź · walidacja | Średni WER · walidacja (n) | Zachowana kluczowa treść · walidacja |
| --- | --- | ---: | ---: | ---: | ---: |
| Studio | Omni | 4/4 / 10/10 / 4/4 | 5/10 | 5,0% (10) | 8/10 |
| Studio | Gemma E4B | 4/4 / 10/10 / 4/4 | 6/10 | 2,0% (10) | 9/10 |
| Full | Omni | 4/4 / 10/10 / 4/4 | 5/10 | 5,0% (10) | 8/10 |
| Full | Gemma E4B | 4/4 / 10/10 / 4/4 | 7/10 | 9,0% (10) | 8/10 |

Pamięć obejmuje Chrome, backend, komponenty mowy i tło hosta. Każda komórka podaje mediany z czterech cykli. Szczyt obejmuje cały cykl nagrań w przeglądarce, po starcie aplikacji i przed zwolnieniem modelu. Punkt odniesienia zapisano po otwarciu Chrome, przed pierwszym nagraniem. Szczyty tury zimnej i rozgrzanej liczą próbki od wysłania do zakończenia pomiaru tury. Różnica median może odbiegać od mediany przyrostu.

| Interfejs | Profil | GPU · przed / szczyt bloku / przyrost (MiB) | GPU · szczyt zimny / rozgrzany (MiB) | RAM WSL · przed / szczyt bloku / przyrost (MiB) | RAM WSL · szczyt zimny / rozgrzany (MiB) |
| --- | --- | ---: | ---: | ---: | ---: |
| Studio | Omni | 2 025 / 5 082 / +3 057 | 5 068 / 5 082 | 1 444 / 2 587 / +1 129 | 2 477 / 2 587 |
| Studio | Gemma E4B | 2 025 / 8 115 / +6 090 | 7 931 / 8 115 | 1 506 / 7 190 / +5 745 | 7 031 / 7 190 |
| Full | Omni | 3 247 / 6 339 / +3 085 | 6 314 / 6 332 | 2 774 / 4 159 / +1 205 | 3 845 / 4 078 |
| Full | Gemma E4B | 3 208 / 8 211 / +5 000 | 8 122 / 8 204 | 2 853 / 7 644 / +4 745 | 7 331 / 7 627 |

We wszystkich 68 turach rozpoczęło się odtwarzanie. Na tym hoście Omni miało niższą medianę czasu do odtwarzania i mniejszy przyrost pamięci w obu interfejsach. Różnica czasu była największa przed załadowaniem wag. Na dziesięciu rozgrzanych nagraniach Gemma miała więcej ścisłych trafień w Studio i Full. W Full uzyskała ten wynik przy wyższym WER, więc poprawność transkrypcji i odpowiedzi warto oceniać osobno.

## Wynik jakościowy na zamrożonych 200 scenariuszach (pomiar historyczny)

Rewizja `c7849e83`, temperatura 0, ziarno 42, kontekst 4096 tokenów, limit 128 tokenów i wyłączony tryb rozumowania. Każdy model dostał 200 wejść z tekstem wzorcowym i 80 powtórek scenariuszy z nagraniem. Razem zebrano 560 ocen. Odpowiedź z obrazem miała ten sam obraz w obu wariantach wejścia. Backend używał natywnego ASR i syntezy Omni, a dla Gemmy Whisper medium i Pipera na CUDA.

| Zadanie i wejście | Omni | Gemma E4B |
| --- | ---: | ---: |
| Rozmowa · tekst wzorcowy | 40/40 | 40/40 |
| Dokumenty · tekst wzorcowy | 33/40 | 40/40 |
| Polecenia głosowe · tekst wzorcowy | 16/40 | 31/40 |
| Polecenia głosowe · nagranie | 7/40 | 23/40 |
| Obraz i pytanie · tekst wzorcowy | 37/40 | 40/40 |
| Obraz i pytanie · nagranie | 40/40 | 40/40 |
| Narzędzia i odpowiedź · tekst wzorcowy | 36/40 | 40/40 |
| **Łącznie** | **209/280** | **254/280** |

Przewaga Gemmy to 16,07 punktu procentowego. W porównaniu sparowanym oba modele zaliczyły 208 pomiarów, tylko Gemma 46, tylko Omni 1, a oba zawiodły w 25. Warianty tekstowy i głosowy tego samego scenariusza są powiązane. W grupie narzędzi oba modele uzyskały 40/40 dla wyboru funkcji i argumentu lub doprecyzowania. Różnica w tabeli obejmuje końcową odpowiedź na podstawie zamrożonego wyniku funkcji. Funkcje miały przygotowane odpowiedzi testowe.

| Metryka | Omni | Gemma E4B |
| --- | ---: | ---: |
| Średni WER na 40 nagraniach poleceń | 13,28% | 6,48% |
| Kluczowa treść w transkrypcji poleceń | 28/40 | 30/40 |
| Średni WER na 40 nagraniach pytań z obrazem | 16,94% | 1,11% |
| Kluczowa treść w transkrypcji pytań z obrazem | 30/40 | 36/40 |
| Błędy wykonania / syntezy próbek | 0 / 0 | 0 / 0 |

W tej serii Omni było już w pamięci, a Gemma ładowała się w pierwszej turze (16,99 s). Tabela zachowuje wyniki jakości i niezawodności. Do porównania ładowania, opóźnienia i pamięci służy nowy pomiar sparowany.

## Studio i Full — wcześniejsza walidacja i poprawka toru Full

Na rewizji `c7849e83` każda para model–interfejs miała 68 wyników przez aplikacyjne API (48 scenariuszy na tekście i 20 także na nagraniu). Łącznie wykonano 272 pomiary. Nagrania samych poleceń w Full używały WebSocket `/voice`. Próby łączące obraz i nagranie korzystały ze składanej ścieżki ASR → obraz z transkrypcją → odpowiedź → synteza. W walidacji narzędzi skrypt przekazywał zamrożony wynik po poprawnym wyborze funkcji. W Studio Gemma korzystała z Whispera i Pipera. W Full zapisane metadane ostatniej tury wskazały natywny dekoder Gemmy i Pipera. Późniejszy odbiór sprawdził dekoder osobno dla każdej tury.

| Profil | Interfejs | Ścisłe trafienia API | Ścisłe trafienia w Chrome |
| --- | --- | ---: | ---: |
| Omni | Studio | 50/68 | 4/10 |
| Omni | Full | 50/68 | 3/10 |
| Gemma E4B | Studio | 51/68 | 4/10 |
| Gemma E4B | Full | 48/68 | 1/10 |

W macierzy API dostarczono 79/80 WAV. Brakująca odpowiedź audio w Studio Gemmy zakończyła się HTTP 503 `audio_invalid_output`. Chrome odtworzył wszystkie 40 tur w stałej kolejności Omni → Gemma, bez kontrolowanej próby zimnego startu. W osobnym odbiorze przełączania Gemma → Omni → Gemma wszystkie sześć tur odtworzyło dźwięk. Wtedy sam selektor i zwolnienie modelu zajmowały 1,91–2,64 s, a ładowanie następowało przy pierwszej inferencji. Naprawiono utratę nagrania w Studio i przedwczesne potwierdzenie zwolnienia wag powodujące HTTP 503 w Full.

### Ponowny odbiór Gemmy po zmianie toru Full

Na rewizji `5cde42ef` Full wybierał natywne ASR lokalnej Gemmy z właściwym formatem instrukcji dla nagrania. Każda końcowa tura głosowa Full potwierdziła `ollama_audio_llm_piper`. W obu interfejsach Direct dostał regułę priorytetu dla bieżącego pytania, ustaleń użytkownika i żądanego formatu. Osobna próba włączenia natywnego ASR Gemmy w Studio dała 2/10 w Chrome wobec 4/10 w punkcie wyjścia, więc w Studio przywrócono Whisper medium na CUDA. Piper pozostał syntezą Gemmy w obu interfejsach.

| Interfejs | API / WS, nagrania | Chrome, ścisłe trafienia | WER Chrome | Start audio po zmianie, mediana / p95 |
| --- | ---: | ---: | ---: | ---: |
| Studio | 4/10 → 6/10 | 4/10 → 6/10 | 4% → 2% | 1,541 / 2,255 s |
| Full | 1/10 → 5/10 | 1/10 → 7/10 | 15% → 9% | 1,325 / 1,753 s |

Tekst wzorcowy wzrósł z 39/48 do 43/48 w obu interfejsach. W Chrome odtworzono po 10/10 odpowiedzi, a przez API dostarczono 9/10 w Studio i 10/10 w Full. W Studio powtórzył się błąd `audio_invalid_output`. Ta próba objęła wyłącznie Gemmę. Potwierdza efekt poprawki, a porównanie profili wymaga wspólnego protokołu.

## Próby diagnostyczne Omni

| Co sprawdziliśmy | Co pokazała próba |
| --- | --- |
| Polski prompt systemowy | Na tych samych 48 tekstach i 20 wspólnych transkrypcjach dodatkowa instrukcja obniżyła wynik tekstowy z 43/48 do 38/48. Nagrania pozostały na 14/20. Zachowano wariant bazowy. |
| Zmiana modelu i historia | Ten sam poprawnie rozpoznany zapis o tulipanach po zmianie modelu dziedziczył wcześniejszą błędną odpowiedź Gemmy. Korekta kontekstu przy ponowieniu przywróciła oczekiwany wynik w nowej rozmowie i po przełączeniu w obu UI. W szerszej sekwencji parafraz, korekt i dopytań wynik pierwotnych nagrań wzrósł z 0/8 do 2/8. Dodatkowe kontrole dały 6/8. |
| „Róże zamiast tulipanów” | Porównano WAV źródłowy z audio po przechwyceniu przez oba UI. Pojedyncza ponowna próba natywnego ASR przy niskiej pewności podniosła zachowanie relacji z 5/6 do 6/6 w Chrome. Ścisła fraza miała 3/6 z powodu odmiany. Na 20 nagraniach walidacyjnych WER wyniósł 3,125%, a kluczowe wskazania zachowano w 18/20. |
| Wybór źródła z obrazu i dopytanie | Po poprawkach macierz wzrosła z 26/36 do 36/36 w Studio i z 24/36 do 36/36 w Full. Po 31 przypadków w każdym transporcie użyło modelu. Pozostałe sprawdzały brak obrazu lub kontrolowane awarie. W Chrome zmieniono źródło dopytaniem bez ponownego dołączenia obrazu. |
| Kamera, bieżący stan i cisza | Po 9/9 prób przez Studio HTTP i Full WS. Sprawdzono pojedynczy JPEG z wirtualnej kamery, korektę wskazania, odczyt stanu, reakcję na awarię, brak obrazu i ciszę. Mediana do kompletnego WAV wyniosła 1,205 s w Studio i 0,990 s w Full. |

### Jakość polskiej mowy

- W odsłuchu jednego zdania o kwadracie jakość nagrań była porównywalna. Operator ocenił polski akcent Pipera `pl_PL-mc_speech-medium` jako naturalniejszy od Omni `female-polish`. Szersza ocena słuchaczy akcentu, prozodii i naturalności pozostaje do wykonania.
- Przygotowano 99 syntetycznych WAV do oceny wejścia (po 33 z Pipera, Omni i Microsoft Paulina Desktop). W pierwszej diagnozie ASR na otwartej części i próbce kontrolnej wyniki wyniosły odpowiednio 8/17, 14/17 i 13/17. Te nagrania przeznaczono do oceny.
- W kontrolowanej syntezie Omni ręcznie rozwinięte liczby, daty, godziny i skróty poprawiły automatyczną ocenę treści z 6/12 do 12/12 w BF16. W powtórce aplikacyjnej rozwinięcie poprawiło wynik z 1/12 do 11/12 w Studio i z 1/12 do 12/12 w Full. W zwykłych turach Direct oba interfejsy miały 2/6 dla odpowiedzi tekstowej i 0/6 dla treści audio w tej próbie.
- W osobnej próbie „Temperatura wynosi 24°C” dwa polskie głosy Omni uzyskały po 0/3 dla zapisu cyfrowego i po 0/3 dla zapisu słownego. Liczbę w wygenerowanym audio oceniał ponowny ASR Omni. To sygnał do odsłuchu i przyszłego treningu wyjścia głosowego. Ręcznie przygotowany tekst był warunkiem pomiaru, a jakość odczytu liczb nadal wymaga kwalifikacji.

## Czego nauczyły próby treningu Omni

Na tej samej RTX 3060 sprawdzono lokalny trening SFT LoRA BF16 z Transformers 5.22.2. Adapter Q/V r4 ma 292 864 parametry, a plik wag w próbie weryfikatora 1,12 MiB. Szczyt rezerwacji VRAM w opisanych próbach wyniósł od 4 588 do 6 048 MiB. Sprawdzano zapis i wznowienie w osobnym procesie. Metryki rezerwacji treningu mają inną definicję niż szczyty użycia całego urządzenia w testach aplikacji.

| Próba | Wynik diagnostyczny |
| --- | --- |
| Zachowanie tekstowe i narzędzia | Pilotaż 6/12 → 7/12. Kolejne iteracje na osobnych walidacjach dawały 10/32 → 22/32, 21/48 → 34/48, 40/64 → 52/64 i 36/57 → 44/57 względem bazy. Zostały regresje rozmowy, mylenie cytatu z poleceniem i problemy z dowodem. Wyniki mają różne zbiory i protokoły. |
| Ranking cytatu lub brak dowodu | Przy progach z kalibracji pointwise podał 5/64 poprawnych cytatów, listwise 10/64. Oba po filtrze poprawnie odmówiły w 64/64 pytaniach bez dowodu. Listwise wykonał 192 kroki w 169,8 s wobec 362,4 s pointwise. Próg jakości 52/64 pozostał nieosiągnięty. |
| Filtr źródła i dopasowanie faktu | Filtr przed rankingiem wyeliminował propozycje z niewskazanego dokumentu w nowej próbie. Nadal przechodziły mylące cytaty z właściwego źródła. W odłożonej próbie dopasowania obiektu, warunku, jednostki lub kolejności weryfikator LoRA zwrócił 3/32 trafnych cytatów i cztery błędy, przy celu 26/32 bez błędu. |
| Natywne wejście audio i obrazu | Enkodery i dekoder mowy pozostały zamrożone. Po 80 krokach wynik ścisły wzrósł z 8/32 do 15/32. Po pominięciu różnic wielkości liter argumentu wynik wyniósł 21/32 dla bazy i 22/32 dla adaptera. Większość poprawy dotyczyła formatu. |

Żaden adapter z opisanych prób nie spełnił kryteriów wdrożenia. Wyniki głównego porównania dotyczą profili bazowych.

### Wyniki pilotażu LoRA

Pilotaż natywnego rozumienia nagrań porównał bazę BF16 z checkpointami 12, 24, 36 i 48. LoRA r4 aktualizowała wyłącznie projekcje Q/V rdzenia językowego. Etykietą była tekstowa odpowiedź na nagranie. Enkodery i dekoder mowy pozostały zamrożone. W pilotażu wykorzystano 96 par treningowych i 24 walidacyjne.

| Próba | Baza Omni | LoRA, checkpoint 48 |
| --- | ---: | ---: |
| Walidacja · tekstowa odpowiedź na nagranie | 36/48 | 43/48 |
| Wcześniejsza próba odłożona · tekst | 18/24 | 16/24 |
| Świeże pary z innymi głosami syntetycznymi · tekst | 13/32 | 20/32 |
| Świeże pary · błędne zgody (mniej to lepiej) | 6/12 | 1/12 |
| Te same świeże pary · wejście wzorcowym tekstem | 25/32 | 25/32 |
| Te same świeże pary · zgodny tekst i mowa w `interleaved` | 13/32 | 13/32 |

W oddzielnej macierzy wyboru checkpointu baza i checkpointy 12, 24, 36, 48 zaliczyły odpowiednio 14, 16, 19, 19 i 20 z 24 pełnych par. Vosk sprawdził 72 WAV. Spośród 14 spornych odpowiedzi dwa krótkie „Tak” potwierdzono automatycznie, cztery odrzucono na podstawie tekstu, osiem pozostaje do ręcznego odsłuchu. Automatyczne rozpoznanie pomaga ocenić treść, a ocenę wymowy i prozodii trzeba wykonać osobno. Próby liczb i jednostek wydzielono: słowny zapis zdał 8/8 w pierwszej próbie osobnej syntezy, 2/5 na nowych wartościach, a w nowej próbie `interleaved` zapis cyfrowy miał 6/10 wobec 0/10 dla słownego. Nie ma podstaw do ogólnej zamiany cyfr na słowa.

Pilotaż zamknięto bez wdrożenia adaptera. Zarchiwizowano lokalnie 1 331 plików z manifestem SHA-256. Główny model wykonawczy i reguły Venoma odpowiadają za wybór narzędzia i wykonanie; Omni może objaśnić, dopytać i przekazać rozpoznaną intencję.


## Natywny dialog Omni w prototypie BF16

Tę próbę wykonano na osobnej gałęzi eksperymentalnej Venoma. W próbie LFM3‑Omni‑2B otrzymało nagranie i obraz w jednej turze, a Studio i Full odtworzyły dźwięk z tej samej generacji. Obecny tor Omni jest punktem odniesienia. Rozgrzana próba BF16 wygenerowała poprawne technicznie WAV w 96/96 turach. Ścisły tekst w trybie `interleaved` zaliczył 4/48 przypadków, a treść mowy 1/48. Tryb `audio` zaliczył 0/36 w ocenie mowy. Czasy do gotowego WAV na rozgrzanym modelu wyniosły 5,181 / 7,532 s w trybie przeplatanym i 5,992 / 7,911 s dla samego audio (mediana / p95). Całe GPU osiągnęło 10 878 MiB. Próby rozmowy w Chrome obejmowały ładowanie modelu i miały osobne czasy. Ocena mowy jest pomocniczą transkrypcją offline, a część nagrań syntetycznych również miała błędy rozpoznania. Wynik utrzymuje oba tryby w zakresie eksperymentu. Tor A na tych samych 48 scenariuszach uzyskał 19/48 w tekście i 12/48 w mowie.

W kontroli na tych samych wagach BF16, obrazie i nagraniach tor składany uzyskał 7/12 ścisłych odpowiedzi tekstowych i 2/12 mówionych, a generacja przeplatana odpowiednio 3/12 i 1/12. Po podmianie nagrania na tekst wzorcowy oba tory uzyskały 6/12 tekstowo i 2/12 głosowo. W ośmiu turach jednoturowych mediana do gotowego WAV wyniosła 1,677 s w torze składanym i 1,871 s w przeplatanym. To porównanie dwóch sposobów pracy tego samego Omni; wynik nie wchodzi do tabeli Omni–Gemma.

## Wybór profilu i odtworzenie pomiaru

**Gemma 4 E4B** pozostaje zalecanym profilem dla dokumentów i odpowiedzi wymagających ścisłego formatu na większym zamrożonym zbiorze. **Bazowe Omni** jest kandydatem do naturalnej polskiej rozmowy multimodalnej. Na tym hoście ładuje się szybciej i zajmuje mniej pamięci w porównaniu Ollamy. Wyniki z jednego hosta i głównie syntetycznych wejść wymagają osobnego potwierdzenia na naturalnych głosach i fizycznej kamerze. Zamknięty pilotaż LoRA i natywny dialog w BF16 pozostają materiałem badawczym.

Instrukcję uruchomienia, format wyników oraz wymagania dla zamrożonych wejść opisuje [polski benchmark asystenta](POLSKI_BENCHMARK_ASYSTENTA.md). Wersjonowane źródła to [skrypt benchmarku](../../scripts/ollama_bench/polish_benchmark.py), [definicje przypadków](../../scripts/ollama_bench/polish_cases.py) i [blokada sum manifestów](../../scripts/ollama_bench/polish_v1.lock.json). Zestawienia powyżej pochodzą z zapisanych przebiegów, a surowe nagrania, logi hosta i checkpointy pozostały w lokalnych artefaktach.

Lokalny indeks powtórki, skrypty i kontrolę sum zapisano w `test-results/omni-gemma-matched/README.md`.

Tożsamość pakietów użytych w porównaniu sparowanym i historycznym:

| Tag | Digest Ollamy |
| --- | --- |
| `lfm3-omni:2b` | `4c0ee9400634babb880868b873bcebf09fbbf1a5328e550bdbaff25888f1f7e2` |
| `gemma4:e4b` | `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c` |

Zobacz też [możliwości toru głosowego Venoma](VOICE_RUNTIME_CAPABILITIES.md) i [lokalny odbiór LFM3](LFM3_LOCAL_EVALUATION.md).
