# Polski asystent multimodalny Venoma — Omni i Gemma 4 E4B

[English version](../EN/POLISH_MULTIMODAL_ASSISTANT_EXPERIMENT.md)

Porównanie z 10 listopada 2026 r. obejmuje lokalne profile **LiquidAI LFM3-Omni-2B** i **Gemma 4 E4B** w Venom Studio oraz pełnym Venomie (Full). Badaliśmy poprawność rozmowy, odpowiedzi z dokumentów, rozumienie mowy i obrazu, wybór narzędzi, czas do rozpoczęcia odtwarzania i pamięć. Osobne próby sprawdzały przełączanie modeli, jakość polskiej syntezy i przydatność adapterów Omni.

Gemma uzyskała **254/280 (90,71%)** ścisłych trafień na zamrożonym benchmarku, Omni **209/280 (74,64%)**. W pierwotnym pomiarze aplikacji Omni szybciej zaczynało odtwarzać i miało niższe szczyty użycia pamięci. Późniejsza naprawa natywnego ASR Gemmy poprawiła jej wynik w Full z **1/10 do 7/10** w Chrome. Te trzy wyniki dotyczą różnych protokołów.

## Sprzęt, modele i sposób oceny

- Jeden host Windows 11 z Ubuntu w WSL2, RTX 3060 z 12 GiB VRAM i lokalną Ollamą 0.40.14. Studio i Full korzystały ze wspólnego backendu. Próby przeglądarkowe w Chrome używały wirtualnego mikrofonu i zapisanych nagrań.
- Testowane tagi Ollamy to `lfm3-omni:2b` i `gemma4:e4b`. Oba pakiety miały oznaczenie GGUF Q4_K_M. Zapisane rozmiary pakietów to odpowiednio ok. 2,05 GB i 6,58 GB na dysku.
- `pl-assistant-v1` zawiera 48 scenariuszy walidacyjnych i 200 końcowych. Podziały mają odrębne rodziny przypadków, dokumenty i syntetyczne głosy. Część nagrań ma szum 18 dB SNR. Sumy manifestów i mediów ustalono przed pomiarem. Rezerwowy zestaw B do oceny adapterów głosowych pozostał zamknięty.
- Ścisłe trafienie uwzględnia poprawność wartości i formatu po normalizacji do słów. Dodatkowa etykieta lub niepoprawna odmiana może obniżyć wynik. WER to stopa błędów słów w transkrypcji. Osobno sprawdzaliśmy zachowanie kluczowych nazw, liczb i relacji, ponieważ pojedyncze słowo może zmienić znaczenie.
- GPU oznacza szczyt użycia całego urządzenia, a RAM użycie WSL jako `MemTotal − MemAvailable`. Obie liczby obejmują pozostałe procesy hosta. Modelowe próby i odsłuch prowadziliśmy osobno od bramek kodu.

## Wynik jakościowy na zamrożonych 200 scenariuszach

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
| Czas do odpowiedzi tekstowej · rozmowa, mediana / p95 | 0,053 / 0,060 s | 0,095 / 0,122 s |
| Czas do odpowiedzi tekstowej · polecenia z nagrania, mediana / p95 | 0,326 / 0,668 s | 0,654 / 1,085 s |
| Mediana do gotowego WAV · polecenia, po 8 próbek | 0,511 s | 0,951 s |
| Mediana do gotowego WAV · obraz i pytanie, po 8 próbek | 0,608 s | 0,821 s |
| Szczyt GPU | 7 962 MiB | 9 741 MiB |
| Szczyt RAM WSL | 5 081 MiB | 7 950 MiB |
| Błędy wykonania / syntezy próbek | 0 / 0 | 0 / 0 |

Gotowość WAV mierzy czas od rozpoczęcia przetwarzania wejścia do otrzymania pliku przez skrypt. Ładowanie zapisano osobno. W tej serii Omni było już w pamięci, a Gemma ładowała się przez 16,99 s. Pomiary pierwszej tury mają różne stany początkowe.

## Studio i Full — walidacja, odtwarzanie i pamięć

Na rewizji `c7849e83` każda para model–interfejs miała 68 wyników przez aplikacyjne API (48 scenariuszy na tekście i 20 także na nagraniu). Łącznie wykonano 272 pomiary. Nagrania samych poleceń w Full używały WebSocket `/voice`. Próby łączące obraz i nagranie korzystały ze składanej ścieżki ASR → obraz z transkrypcją → odpowiedź → synteza. W walidacji narzędzi skrypt przekazywał zamrożony wynik po poprawnym wyborze funkcji. W Studio Gemma korzystała z Whispera i Pipera. W Full zapisane metadane ostatniej tury wskazały natywny dekoder Gemmy i Pipera. Późniejszy odbiór sprawdził dekoder osobno dla każdej tury.

| Profil | Interfejs | Ścisłe trafienia API | Ścisłe trafienia w Chrome | Start audio w Chrome, mediana / p95 | Szczyt GPU | Szczyt RAM WSL |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Omni | Studio | 50/68 | 4/10 | 1,210 / 1,425 s | 7 235 MiB | 5 556 MiB |
| Omni | Full | 50/68 | 3/10 | 1,191 / 1,509 s | 7 498 MiB | 5 517 MiB |
| Gemma E4B | Studio | 51/68 | 4/10 | 2,641 / 5,576 s | 9 871 MiB | 9 570 MiB |
| Gemma E4B | Full | 48/68 | 1/10 | 4,532 / 10,276 s | 8 865 MiB | 9 439 MiB |

Osobna seria Chrome użyła 10 tych samych nagrań na konfigurację. Odtwarzanie zaczęło się we wszystkich 40 turach. Pomiar trwał od końca nagrania do zdarzenia `playing` w Studio lub startu źródła w działającym `AudioContext` w Full. Modele były rozgrzane, kolejność była stała (Omni → Gemma), a długie odpowiedzi wpływały na wynik. Pamięć próbkowano co ok. 289 ms (mediana odstępu, 2233 próbki). W macierzy API dostarczono 79/80 WAV. Brakująca odpowiedź audio w Studio Gemmy zakończyła się HTTP 503 `audio_invalid_output`.

We wcześniejszej serii krótkiej odtworzono wszystkie 16 tur. Mediany trzech kolejnych tur wyniosły odpowiednio **1,258 / 1,330 s** w Studio i Full dla Omni oraz **4,128 / 1,473 s** dla Gemmy. Pierwsza zimna tura Gemmy w Full zajęła **13,206 s**. W osobnym odbiorze przełączania Gemma → Omni → Gemma wszystkie sześć tur odtworzyło dźwięk. Sam selektor i zwolnienie modelu zajmowały od 1,91 do 2,64 s, a ładowanie odbywało się przy pierwszej inferencji. Naprawiono utratę nagrania w Studio oraz przypadek 503 w Full, w którym potwierdzenie zwolnienia modelu przychodziło przed jego faktycznym usunięciem z pamięci.

### Ponowny odbiór Gemmy po zmianie toru Full

Na rewizji `5cde42ef` Full wybierał natywne ASR lokalnej Gemmy z właściwym formatem instrukcji dla nagrania. Każda końcowa tura głosowa Full potwierdziła `ollama_audio_llm_piper`. W obu interfejsach Direct dostał regułę priorytetu dla bieżącego pytania, ustaleń użytkownika i żądanego formatu. Osobna próba włączenia natywnego ASR Gemmy w Studio dała 2/10 w Chrome wobec 4/10 w punkcie wyjścia, więc w Studio przywrócono Whisper medium na CUDA. Piper pozostał syntezą Gemmy w obu interfejsach.

| Interfejs | API / WS, nagrania | Chrome, ścisłe trafienia | WER Chrome | Start audio po zmianie, mediana / p95 |
| --- | ---: | ---: | ---: | ---: |
| Studio | 4/10 → 6/10 | 4/10 → 6/10 | 4% → 2% | 1,541 / 2,255 s |
| Full | 1/10 → 5/10 | 1/10 → 7/10 | 15% → 9% | 1,325 / 1,753 s |

Tekst wzorcowy wzrósł z 39/48 do 43/48 w obu interfejsach. W Chrome odtworzono po 10/10 odpowiedzi, a przez API dostarczono 9/10 w Studio i 10/10 w Full. W Studio powtórzył się błąd `audio_invalid_output`. Po zmianie toru zmierzono ponownie opóźnienie i jakość na tych samych nagraniach. Tabele pamięci oraz zamrożony wynik 200 scenariuszy pochodzą z wcześniejszych konfiguracji.

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

## Wybór profilu i odtworzenie pomiaru

**Gemma 4 E4B** jest zalecanym profilem jakościowym dla zadań z zamrożonego benchmarku, w tym dokumentów i odpowiedzi wymagających ścisłego formatu. **Bazowe Omni** jest profilem eksperymentalnym natywnej polskiej rozmowy głosowej z natywnym wejściem i wyjściem, niższym opóźnieniem i mniejszym zużyciem pamięci w pierwotnym pomiarze. Nowszy tor Full potwierdził, że Gemma może obsłużyć natywne wejście głosowe i odtwarzanie przez Pipera. Wybór profilu zależy od priorytetu między jakością odpowiedzi, szybkością, pamięcią i naturalnością mowy. Pomiary obejmują jeden host i w większości syntetyczne nagrania. Odbiór fizycznej kamery i szerszy odsłuch pozostają osobnymi zadaniami.

Instrukcję uruchomienia, format wyników oraz wymagania dla zamrożonych wejść opisuje [polski benchmark asystenta](POLSKI_BENCHMARK_ASYSTENTA.md). Wersjonowane źródła to [skrypt benchmarku](../../scripts/ollama_bench/polish_benchmark.py), [definicje przypadków](../../scripts/ollama_bench/polish_cases.py) i [blokada sum manifestów](../../scripts/ollama_bench/polish_v1.lock.json). Zestawienia powyżej pochodzą z zapisanych przebiegów, a surowe nagrania, logi hosta i checkpointy pozostały w lokalnych artefaktach.

Tożsamość modeli w porównaniu końcowym:

| Tag | Digest Ollamy |
| --- | --- |
| `lfm3-omni:2b` | `4c0ee9400634babb880868b873bcebf09fbbf1a5328e550bdbaff25888f1f7e2` |
| `gemma4:e4b` | `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c` |

Zobacz też [możliwości toru głosowego Venoma](VOICE_RUNTIME_CAPABILITIES.md) i [lokalny odbiór LFM3](LFM3_LOCAL_EVALUATION.md).
