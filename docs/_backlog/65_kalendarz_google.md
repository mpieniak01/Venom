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

* [ ] **Safe Layering**: brak ingerencji w wydarzenia użytkownika w `primary` (brak create/update/delete).
* [ ] **Read-Only Primary**: odczyt agendy/dostępności z `primary` działa i zwraca poprawne dane w ustalonym oknie czasowym.
* [ ] **Write-Only Venom Work**: planowanie zadań tworzy wydarzenia wyłącznie w kalendarzu Venoma (`VENOM_CALENDAR_ID`).
* [ ] **Izolacja warstwy**: wydarzenia Venoma są widoczne jako osobny kalendarz/kolor i mogą być ukryte jednym kliknięciem.
* [ ] **Graceful Degradation**: brak credentials nie powoduje crasha — skill nie jest rejestrowany, reszta systemu działa.

### 7.2 Kryteria konfiguracyjne

* [ ] Dodane zależności w `requirements.txt`.
* [ ] Dodane zmienne w `.env.example` i rejestracja w globalnym configu.
* [ ] Pliki tokenów/credentials są wykluczone z repo (`.gitignore`).

### 7.3 Testy zielone (Quality Gates)

* [ ] **TC-001 (Auth)**: autoryzacja OAuth2 przechodzi poprawnie, token lokalny jest generowany.
* [ ] **TC-002 (Context Read)**: komenda agendy zwraca poprawne wydarzenia z `primary`.
* [ ] **TC-003 (Task Scheduling)**: komenda planowania tworzy wpis w `Venom Work`.
* [ ] **TC-004 (Safety/Isolation)**: wpis Venoma nie pojawia się w `primary`, tylko w kalendarzu Venoma.
* [ ] **TC-005 (No-Credentials Mode)**: brak credentials = brak rejestracji skilla, brak błędów startu aplikacji.

> Akceptacja PR następuje po potwierdzeniu, że powyższe testy są **zielone**, a funkcjonalności opisane w celu PR (read-only primary + write-only venom calendar) działają zgodnie z

## 8. Notatki dla review

* PR celowo nie zawiera szczegółów implementacyjnych (agent kodowania odpowiada za kod).
* Review koncentruje się na:

  * spójności z modelem Safe Layering,
  * kompletności konfiguracji,
  * kryteriach bezpieczeństwa i izolacji,
  * poprawności kryteriów akceptacji i testów.
