# 073: Dedykowany ekran zarządzania modelami (Ollama + HuggingFace) i umiejetnosc tlumaczenia
Status: wykonane

## Cel
Zbudować osobny ekran do zarządzania modelami LLM, zasilany integracją
z **ollama.com** i **huggingface.co** (trendy + instalacja/aktywacja/usuwanie).

## Stan obecny w kodzie
- Zapoznaj sie z obecna struktura web-next
- Backend ma `ModelRegistry` i endpointy:
  - `GET /api/v1/models/providers` (lista modeli z providerów),
  - `POST /api/v1/models/registry/install`, `DELETE /api/v1/models/registry/{name}`,
  - `POST /api/v1/models/activate`,
  - `GET /api/v1/models/operations`.
- `ModelRegistry`:
  - Ollama: pobiera listę z `http://localhost:11434/api/tags`.
  - HuggingFace: lista modeli jest **stubem** (statyczna lista 2 modeli).
  - Brak realnego API do trendów HF/Ollama.
- `GET /api/v1/models` zwraca lokalne modele + `providers` bucket (ollama/vllm).

## Zakres
1. **Nowy ekran**
   - Dedykowana ścieżka w UI (np. `/models`).
   - Sekcje: trendy, zainstalowane, dostępne do pobrania.

2. **Integracja z zewnętrznymi API**
   - Pobranie trendów i list modeli z `ollama.com`.
   - Pobranie trendów i list modeli z `huggingface.co`.
   - Cache i rate‑limit, fallback bez internetu.

3. **Operacje na modelach**
   - Instalacja (pobranie) modelu.
   - Aktywacja modelu dla runtime.
   - Usunięcie modelu.
   - Statusy operacji (progress, błąd, sukces).

4. **Kontrakt danych**
   - Spójne mapowanie: provider → runtime → model.
   - Walidacja kompatybilności (np. Ollama-only vs vLLM).

## Kryteria akceptacji
- Ekran prezentuje trendy i listy modeli z obu źródeł.
- Użytkownik może łatwo zainstalować, aktywować i usunąć model.
- UI pokazuje status operacji i obsługuje błędy.
- Lista modeli jest spójna z runtime i nie miesza providerów.

## Postęp realizacji
- [x] Backend: endpoint `/api/v1/models/trending` + integracje HF/Ollama z cache i fallbackiem.
- [x] Backend: spójny kontrakt danych w katalogu/trendach + walidacja runtime.
- [x] UI: ekran `/models` z sekcjami Trendy/Zainstalowane/Dostępne i statusami operacji.
- [x] Telemetria: logi install/remove/activate oraz toast w UI.
- [x] Dokumentacja: aktualizacja `docs/MODEL_MANAGEMENT.md`.
- [x] UI/UX: manualne odświeżanie sekcji (bez polling), cache w `localStorage`.
- [x] UI/UX: News + Papers z osobnymi boxami, RSS HuggingFace blog + papers (HTML parsing).
- [x] UI/UX: akordeony dla wszystkich sekcji, układ kolumn dla Ollama/HF i vLLM/Ollama.
- [x] UI/UX: podgląd statusu runtime i aktywnego modelu po prawej od nagłówka.
- [x] UI/UX: "Przegląd modeli" z opisem w jednym wierszu tej samej wysokości, a boxy "Status serwera" i "Aktywny model" wyrównane do prawej.
- [x] Backend: uniwersalny endpoint tłumaczeń `/api/v1/translate` z użyciem aktywnego modelu.
- [x] Backend: tłumaczenie news/papers w `/api/v1/models/news?lang=pl|en|de`.
- [x] UI: cache news/papers per język (PL/EN/DE) + ręczne odświeżanie.

## Dodatkowe zmiany (poza pierwotnym zakresem)
- Nowy endpoint `/api/v1/models/news`:
  - `type=blog` (RSS z `https://huggingface.co/blog/feed.xml`).
  - `type=papers` (parsowanie HTML z `https://huggingface.co/papers/month/YYYY-MM`).
- Cache danych news/papers w UI (localStorage).
- Sortowanie news/papers (najnowsze/najstarsze).
- Endpoint `/api/v1/translate` (uniwersalne tłumaczenia treści w oparciu o aktywny runtime).

## Analiza: tłumaczenia treści news/papers
- W repozytorium nie ma dedykowanego „skill” do automatycznego tłumaczenia treści (lista skilli nie zawiera takiej funkcji).
- Jest system i18n UI (`web-next/lib/i18n`) z językami PL/EN/DE, ale to tylko statyczne tłumaczenia interfejsu.
- Zaimplementowano uniwersalne API tłumaczeń (`/api/v1/translate`) wykorzystujące aktywny runtime/model.

### Co zostało wdrożone
1. **Endpoint tłumaczeń**:
   - Backend: `/api/v1/translate`, używa aktywnego runtime/modelu.
   - Wejście: `text`, `source_lang`, `target_lang`, `use_cache`.
   - Wyjście: `translated_text`.
2. **Cache per język (opcjonalny)**:
   - UI: cache treści news/papers w trzech wersjach: PL/EN/DE (localStorage).
   - Klucz cache uwzględnia język panelu (np. `models-blog-hf-pl`).
   - Jeśli źródło jest po angielsku, UI serwuje wersję zgodną z językiem użytkownika
     (flaga języka z `LanguageProvider`), a przy braku tłumaczenia wywołuje API i zapisuje wynik.
3. **Ograniczenie długości tłumaczeń**:
   - Dla długich treści (papers) tłumaczony jest tylko początkowy fragment tekstu.
   - Ma to ograniczyć czas odpowiedzi i ryzyko timeoutów.

## Otwarte tematy do zaplanowania (Task 073)
- Doprecyzowanie limitów, TTL i fallbacków dla tłumaczeń (jeśli cache będzie użyty).
- Podział długich treści na krótsze fragmenty i pełne tłumaczenie całego tekstu.

## Scenariusze testowe
1. **Nowości (News) - pobranie + cache per język**
   - Ustaw język panelu na PL, odśwież Nowości.
   - Oczekiwane: lista z tłumaczeniem PL, zapis w `localStorage` (klucz `models-blog-hf-pl`).
   - Zmień język na EN/DE, odśwież ponownie.
   - Oczekiwane: osobne cache per język, brak mieszania treści.
2. **Gazeta (Papers) - tłumaczenie fragmentu**
   - Odśwież Gazetę.
   - Oczekiwane: skrócony opis (fragment) przetłumaczony, brak 500.
   - Sprawdź, czy „Zobacz” jest w linii z „Autor”.
3. **Manualne odświeżanie sekcji**
   - Odśwież Nowości/Papers/Trendy/Katalog.
   - Oczekiwane: tylko dana sekcja się przeładowuje, reszta bez zmian.
4. **Tryb offline**
   - Odłącz internet, odśwież Nowości/Papers.
   - Oczekiwane: dane z cache + badge `Cache offline` jeśli dostępne.
5. **Daty**
   - Sprawdź format dat w Nowościach i Papers (krótki dzień tygodnia + lokalizacja językowa).
6. **Akordeony**
   - Zwiń/rozwiń każdy blok.
   - Oczekiwane: przycisk wyrównany do tytułu po prawej, poprawne ukrywanie treści.

## Do zrobienia
1. **Backend: integracje**
   - Dodać nowe endpointy: np. `GET /api/v1/models/trending?provider=...`.
   - Ollama: pobierać trendy z publicznego API (brak w kodzie).
   - HuggingFace: pobierać trendy przez HF Hub API (brak w kodzie).
   - Cache (np. TTL 15-60 min) + fallback do ostatniego wyniku.
2. **Backend: kontrakt danych**
   - Zdefiniować spójny format: `provider`, `model_name`, `display_name`,
     `size_gb`, `runtime`, `tags`, `downloads`, `likes`.
   - Walidować kompatybilność: `ollama` → runtime `ollama`,
     HF → runtime `vllm`.
3. **UI: nowy ekran**
   - Strona `/models` z sekcjami: Trendy, Zainstalowane, Dostępne.
   - Akcje: install, activate, delete, podgląd statusu operacji.
   - Widoczny stan offline (brak Internetu) i link do instrukcji.
4. **Telemetria**
   - Log operacji: install/remove/activate z providerem i runtime.
   - Ewentualne powiadomienia toast o sukcesie/błędzie.

## Proponowane pliki do zmiany
- `web-next/app/models/page.tsx` (nowy ekran)
- `web-next/components/models/*`
- `web-next/hooks/use-api.ts`
- `venom_core/api/routes/models.py`
- `venom_core/core/model_manager.py`
- `venom_core/core/model_registry.py`
- `docs/MODEL_MANAGEMENT.md`

## Zależności / uwagi dla wykonawcy
- `ModelRegistry` już obsługuje Ollama listę lokalną, ale HF jest statyczny stub.
- Trzeba odróżnić listy: lokalne (z `/api/v1/models`) vs zewnętrzne trendy.
- Wymagany publiczny client HTTP (np. `httpx`) + caching po stronie backendu.
- Bez internetu ekran powinien pokazywać dane z cache lub „brak danych”.
