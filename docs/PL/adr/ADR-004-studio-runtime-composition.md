# ADR-004: Osobne kompozycje aplikacji Venom i Studio

Data: 2026-10-31. Status: decyzja implementacyjna; kwalifikacja wydania jest
zapisywana osobno. Częściowo zastępuje wybór jednego wdrożenia z
[ADR-003](ADR-003-chat-2-shell.md), zachowując kontrakty rozmowy i bezpieczeństwa.

## Kontekst

Osobna trasa `/chat2` usuwa stary kokpit i jego telemetrię z drzewa rozmowy.
Nadal działa jednak w aplikacji z pełnymi trasami i backendem inicjalizującym
zbędne usługi. Theme nie zmienia tej granicy startu. Operator potrzebuje wejścia
skupionego na rozmowie, z zachowaniem obecnej aplikacji i danych środowiska.

## Decyzja

1. Zachowujemy Next.js/FastAPI. `venom` i `studio` to jawne warianty aplikacji,
   niezależne od Full/Light i dev/preprod. Przed zmianą zatrzymujemy właściciela;
   bez dwóch właścicieli wspólnych danych lub lokalnych silników.
2. Studio używa `web-studio`, wyłącznie tras `/` i `/chat2`, własnego wykrywania
   tras, artefaktów/cache/public i metadanych. Współdzieli komponenty Chat 2.0,
   kontroler, providery, fonty/globalne style i zainstalowane zależności `web-next`.
   Nie kopiujemy ekranów, logiki biznesowej, mirrorów modułów ani proxy.
   Link do klasycznego `/chat` ukrywamy tylko w osobnym Studio; domyślne zachowanie
   wspólnego komponentu w istniejącej aplikacji pozostaje.
3. Uruchamiamy `venom_core.studio_main:app`: jawny podzbiór istniejących funkcji
   endpointów ze wspólnymi schematami, ochroną, admission, budżetami,
   identyfikatorami żądań, historią i anulowaniem. Bez importu wejścia Full,
   duplikowania handlerów i cichego fallbacku do nieobecnych endpointów Full.
   Zapis motywu zachowuje GET/POST config/runtime z ochroną localhost Full,
   bez kopiowania ekranu konfiguracji.
4. Używamy konfiguracji i trwałych danych środowiska: SessionStore, katalogów
   pamięci/materiałów, stanu dostawcy i namespace kolejek/cache. Nie powstaje baza
   Studio, migracja ani druga kolejka. Izolacja dev/preprod i preprod tylko do
   odczytu pozostają. Storage przeglądarki należy do originu, używa wspólnych
   kluczy i nie zastępuje historii serwera.
5. Istniejący Orchestrator i zależności wykonania/pamięci powstają dopiero przy
   obsługiwanym Normal/MAF. Zachowujemy prawdziwy ingest pamięci Direct:
   dotychczasowy VectorStore powstaje, gdy jest potrzebny. Skonfigurowane STT/TTS
   inicjalizuje się przy pierwszym użyciu, bez warmup przy starcie. Nie dodajemy
   automatycznego RAG, treningu, ekranów ani drugiego loadera. Nadal obowiązuje
   obecny wybór runtime i własność lokalnych silników.
6. Start/stop/status wariantów używają wspólnego resolvera, serializowanego
   lifecycle i proxy. Tożsamość artefaktu obejmuje aplikację i wspólne wejścia,
   także worklet. Jawny stop zatrzymuje tylko zweryfikowane API/UI i własne
   lokalne silniki. Obce, podmienione i nieweryfikowalne rekordy powodują błąd.
   Przed sprzątaniem kończymy aktywne i natywne zadania. Węższy historyczny stop
   API/UI pozostaje osobny.
7. Automaty sprawdzają zgodność tras/schematów/ochrony, tożsamość handlerów,
   zakazane importy, rozmowę/audio na atrapach, wymagane zasoby i cleanup.
   Build, pomiary operacyjne i kwalifikacja prawdziwych dostawców/audio stanowią
   osobne dowody. Atrapy i liczba tras nie dowodzą oszczędności RAM ani gotowości
   prod. Rzeczywisty Test Zero nadal wymaga zlecenia operatora.

## Skutki

Frontend i API mogą mieć mniejszy zakres startu przy jednej implementacji rozmowy
i wspólnych danych. Osobne artefakty dodają obsługę lifecycle, bez nowego frameworka
lub storage. Style globalne i instalacja zależności są wspólne. Normal/MAF, ingest
i głos mogą po starcie doładować cięższe komponenty. Te stany mierzymy oddzielnie,
bez obietnicy stale lekkiego procesu.

## Wycofanie

Zatrzymaj własne Studio i uruchom Venoma w tym samym środowisku zweryfikowanym
launcherem. Bez usuwania danych i migracji historii. Opcjonalne `/chat2` w Full
zachowuje kontrakt flagi buildu; to inny wybór niż osobny wariant aplikacji.

[Instrukcja operatora](../STUDIO.md) · [English ADR](../../adr/ADR-004-studio-runtime-composition.md)
