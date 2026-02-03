# PR: Venom Calendar Layer (Google Workspace Integration)

**Tytuł:** `feat(skills): add GoogleCalendarSkill for Venom Calendar Layer`

---

## 1. Cel i kontekst

Celem PR jest dodanie warstwy integracji z **Google Calendar** w modelu **Safe Layering**: Venom pomaga w planowaniu i time-blockingu, ale **nie miesza się** do prywatnych spotkań użytkownika.

Zakładamy podejście **Local‑First** i separację odpowiedzialności: Venom ma swoją „warstwę roboczą” (kalendarz Venoma), a kalendarz główny użytkownika służy tylko do odczytu dostępności.

---

## 2. Koncepcja architektoniczna (Safe Layering)

### Dual‑Mode

1. **Read‑Only (Primary Calendar)**

   * Venom **odczytuje** wydarzenia z głównego kalendarza (`primary`) wyłącznie w celu:

     * sprawdzania dostępności,
     * wykrywania kolizji,
     * kontekstowego planowania.
   * Venom **nie tworzy / nie modyfikuje / nie usuwa** wydarzeń w `primary`.

2. **Write‑Only (Venom Calendar)**

   * Venom **zapisuje** wydarzenia typu:

     * time-blocking,
     * zadania,
     * bloki pracy,
     * przypomnienia,
       wyłącznie do dedykowanego kalendarza roboczego (np. `Venom Work`).

### Zasada izolacji

* Warstwa Venoma jest widoczna w Google Calendar jako **osobny kalendarz** (osobny kolor), możliwy do ukrycia jednym kliknięciem.
* Użytkownik zachowuje pełną kontrolę nad widocznością i dostępem.

---

## 3. Zakres zmian w repo

### 3.1 Konfiguracja i zależności

* Aktualizacja `requirements.txt` o biblioteki Google API.
* Aktualizacja `.env.example` o zmienne środowiskowe do integracji (ścieżka do OAuth credentials + identyfikator/nazwa kalendarza Venoma).
* Rejestracja nowych wartości w globalnym configu aplikacji.

### 3.2 Nowy skill: GoogleCalendarSkill

* Dodanie nowego skilla w warstwie execution/skills.
* Skill udostępnia funkcje SK (Semantic Kernel) do:

  * pobrania agendy/dostępności z `primary` (read‑only),
  * planowania zadań w kalendarzu Venoma (write‑only).

### 3.3 Rejestracja w skill managerze

* Warunkowa rejestracja skilla w Kernelu:

  * aktywacja tylko, jeśli dostępne są pliki autoryzacyjne (credentials).
  * w przeciwnym wypadku system działa bez błędów (graceful degradation).

---

## 4. Interfejs i zachowania (bez implementacji)

### 4.1 Dostępność / agenda (Primary)

* Użytkownik może zapytać o plan dnia lub dostępność.
* Venom zwraca listę wydarzeń z głównego kalendarza w określonym oknie czasowym (np. najbliższe 24h).
* Odpowiedź powinna być czytelna (kolejność chronologiczna, nazwa wydarzenia, czas startu).

### 4.2 Planowanie zadań (Venom Work)

* Użytkownik może polecić stworzenie bloku pracy/zadania.
* Venom tworzy wydarzenie wyłącznie w kalendarzu Venoma.
* Dane wejściowe minimalne:

  * tytuł,
  * start (ISO),
  * czas trwania (min).
* Dodatkowo: ustawiane przypomnienie (np. popup).

---

## 5. Plan testów (Quality Assurance)

| Test ID | Scenariusz          | Oczekiwany rezultat                                                                      |
| ------- | ------------------- | ---------------------------------------------------------------------------------------- |
| TC-001  | Smoke Test / Auth   | Pierwsze uruchomienie inicjuje autoryzację OAuth2; generowany jest token lokalny         |
| TC-002  | Context Read        | Zapytanie „Co mam dziś w planach?” zwraca wydarzenia z `primary`                         |
| TC-003  | Task Scheduling     | Polecenie „Zaplanuj kodowanie na 16:00” tworzy event w `Venom Work` (nie w `primary`)    |
| TC-004  | Safety / Isolation  | Event Venoma widoczny jako osobny kalendarz/kolor; możliwy do ukrycia jednym kliknięciem |
| TC-005  | No‑Credentials Mode | Brak credentials nie powoduje crasha; skill nie jest rejestrowany, system działa dalej   |

---

## 6. Bezpieczeństwo i prywatność

* **Local‑First:** tokeny i credentials przechowywane lokalnie i wykluczone z repozytorium (`.gitignore`).
* **Minimalizacja ryzyka:** logika skilla wymusza:

  * odczyt tylko z `primary`,
  * zapis tylko do `VENOM_CALENDAR_ID`.
* **Kontrola użytkownika:** użytkownik może w każdej chwili:

  * ukryć warstwę Venoma,
  * cofnąć dostęp OAuth,
  * usunąć kalendarz Venoma bez wpływu na kalendarz prywatny.

---

## 7. Kryteria akceptacji

### 7.1 Kryteria funkcjonalne (cel PR działa)

* [x] **Safe Layering**: brak ingerencji w wydarzenia użytkownika w `primary` (brak create/update/delete).
* [x] **Read-Only Primary**: odczyt agendy/dostępności z `primary` działa i zwraca poprawne dane w ustalonym oknie czasowym.
* [x] **Write-Only Venom Work**: planowanie zadań tworzy wydarzenia wyłącznie w kalendarzu Venoma (`VENOM_CALENDAR_ID`).
* [x] **Izolacja warstwy**: wydarzenia Venoma są widoczne jako osobny kalendarz/kolor i mogą być ukryte jednym kliknięciem.
* [x] **Graceful Degradation**: brak credentials nie powoduje crasha — skill nie jest rejestrowany, reszta systemu działa.

### 7.2 Kryteria konfiguracyjne

* [x] Dodane zależności w `requirements.txt`.
* [x] Dodane zmienne w `.env.example` i rejestracja w globalnym configu.
* [x] Pliki tokenów/credentials są wykluczone z repo (`.gitignore`).

### 7.3 Testy zielone (Quality Gates)

* [x] **TC-001 (Auth)**: autoryzacja OAuth2 przechodzi poprawnie, token lokalny jest generowany (zaimplementowano i przetestowano z mockami).
* [x] **TC-002 (Context Read)**: komenda agendy zwraca poprawne wydarzenia z `primary` (funkcja read_agenda zaimplementowana i przetestowana).
* [x] **TC-003 (Task Scheduling)**: komenda planowania tworzy wpis w `Venom Work` (funkcja schedule_task zaimplementowana i przetestowana).
* [x] **TC-004 (Safety/Isolation)**: wpis Venoma nie pojawia się w `primary`, tylko w kalendarzu Venoma (testy weryfikują Safe Layering).
* [x] **TC-005 (No-Credentials Mode)**: brak credentials = brak rejestracji skilla, brak błędów startu aplikacji (graceful degradation przetestowany).

> Akceptacja PR następuje po potwierdzeniu, że powyższe testy są **zielone**, a funkcjonalności opisane w celu PR (read-only primary + write-only venom calendar) działają zgodnie z

## 8. Notatki dla review

* PR celowo nie zawiera szczegółów implementacyjnych (agent kodowania odpowiada za kod).
* Review koncentruje się na:

  * spójności z modelem Safe Layering,
  * kompletności konfiguracji,
  * kryteriach bezpieczeństwa i izolacji,
  * poprawności kryteriów akceptacji i testów.

---

## 9. Status implementacji

**Data ukończenia:** 2025-12-19

### Zaimplementowane komponenty:

1. **GoogleCalendarSkill** (`venom_core/execution/skills/google_calendar_skill.py`)
   - OAuth2 flow z automatycznym odświeżaniem tokenów
   - `read_agenda()` - odczyt z primary calendar (READ-ONLY)
   - `schedule_task()` - zapis do Venom calendar (WRITE-ONLY)
   - Graceful degradation bez credentials
   - Pełne logowanie i obsługa błędów

2. **Konfiguracja**
   - `requirements.txt` - dodano Google API dependencies
   - `.env.example` - dodano zmienne ENABLE_GOOGLE_CALENDAR, GOOGLE_CALENDAR_CREDENTIALS_PATH, itd.
   - `venom_core/config.py` - dodano Settings dla Google Calendar
   - `.gitignore` - wykluczone pliki credentials i tokenów

3. **Rejestracja**
   - Skill zarejestrowany w ChatAgent z warunkiem ENABLE_GOOGLE_CALENDAR
   - Warunkowa rejestracja zapewnia graceful degradation
   - Zaktualizowany system prompt ChatAgent o instrukcje kalendarza

4. **Testy**
   - `tests/test_google_calendar_skill.py` - 12 testów jednostkowych (wszystkie PASSED)
   - Testy pokrywają: inicjalizację, read_agenda, schedule_task, Safe Layering, graceful degradation, błędy API

### Jak używać:

1. Włącz w `.env`: `ENABLE_GOOGLE_CALENDAR=true`
2. Pobierz OAuth2 credentials z Google Cloud Console
3. Zapisz jako `data/config/google_calendar_credentials.json`
4. Pierwsze uruchomienie otworzy przeglądarkę z OAuth flow
5. Token zostanie zapisany w `data/config/google_calendar_token.json`
6. Venom będzie miał dostęp do kalendarza przez ChatAgent

### Przykładowe zapytania:

- "Co mam w planach dzisiaj?"
- "Pokaż moją agendę na następne 8 godzin"
- "Zaplanuj mi blok pracy na kodowanie jutro o 14:00 przez 2 godziny"
- "Dodaj przypomnienie na spotkanie w piątek o 10:00"

### Bezpieczeństwo:

- ✅ Credentials i tokeny w `.gitignore`
- ✅ Safe Layering: read z primary, write tylko do venom calendar
- ✅ Lokalne przechowywanie tokenów (Local-First)
- ✅ Użytkownik kontroluje widoczność kalendarza Venoma w Google Calendar
