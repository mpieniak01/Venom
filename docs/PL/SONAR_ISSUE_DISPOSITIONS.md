# Rozliczenie pozostałych zgłoszeń Sonara — 19 października 2026

Sprawdzony main: `fabce6b322a6884ad938c98688e93dfe6f0eb638`, po PR #547–#550.
729 z pierwotnych 742 zgłoszeń zamknęły zmiany kodu. Pozostałe 13 uwag
utrzymaniowych oceniono indywidualnie: **9 false positive i 4 accepted**.
Akceptacja odstępstwa nie oznacza naprawy kodu ani podatności bezpieczeństwa.

| Przypadek | Liczba | Decyzja i uzasadnienie |
| --- | --- | --- |
| Nawiasy grupujące wielowierszowe napisy | 6 | False positive: zapewniają kontynuację wyrażenia, nie są zbędną zagnieżdżoną parą. |
| Pojedyncze długie wyrażenia w google_calendar_skill i platform_skill | 2 | Accepted: nawiasy są opcjonalne semantycznie, lecz Ruff po usunięciu odtwarza je z uwagi na długość wiersza. |
| Retry, parsowanie odpowiedzi i oczekiwanie na gotowość demona | 3 | False positive: kolejne operacje zależą od wyniku poprzednich; dokumentacja S9382 wprost dopuszcza ten przypadek. |
| Publiczne ToolPolicy.Auto | 1 | Accepted: zachowanie dotychczasowej nazwy konstruktora i zgodności wywołań. |
| Timeout sondy ONNX | 1 | Accepted: timeout określa limity faz HTTPX, a nie czas całej operacji; zastąpienie go jednym asyncio.timeout zmienia kontrakt. |

Pełne klucze, lokalizacje, uzasadnienia, testy i warunki ponownej oceny:
[rejestr indywidualnych decyzji](../SONAR_ISSUE_DISPOSITIONS.md#individual-decisions).
Każda decyzja dotyczy tylko opisanego zgłoszenia. Nie wyłączamy reguł, nie
stosujemy NOSONAR i nie obniżamy bramek. Przy zmianie kontraktu lub kodu trzeba
ponownie ocenić decyzję, nawet gdy Sonar zachowa wcześniejszy status.

Walidacja: 92 testy backendu PASS, 6 testów retry PASS, 3 testy gotowości demona
PASS, Ruff dla 8 plików PASS. Dwa przypadki formatowania sprawdzono także przez
porównanie AST i ponowne formatowanie. Nie wykonano fizycznych testów robota,
modeli ani pomiarów timeoutów rzeczywistej sieci.

Zmiana repozytorium dotyczy wyłącznie Markdown: hard gates skipped by policy;
changed-lines coverage N/A. Kod wykonawczy i zależności pozostają bez zmian.
Wcześniejsza bramka main: 3981 PASS / 8 SKIP — nie jest nowym uruchomieniem testów
w ramach tego przeglądu.
