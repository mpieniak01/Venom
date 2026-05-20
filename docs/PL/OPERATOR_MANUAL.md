> [!IMPORTANT]
> **STATUS: DRAFT W OPRACOWANIU**
> Ten dokument jest w trakcie tworzenia.

# Podręcznik Operatora Venom (Operator Manual)

Witaj w Podręczniku Operatora. Ten dokument służy do wyjaśnienia, jak korzystać z systemu Venom na co dzień, rozumieć wyświetlane wskaźniki i zarządzać jego zasobami. W przeciwieństwie do dokumentacji technicznej, skupiamy się tutaj na *użyteczności*, a nie *implementacji*.

## 1. Kluczowe Pojęcia

Aby efektywnie współpracować z Venomem, warto zrozumieć dwa fundamenty jego działania: **Timelines** (Linie Czasowe) oraz **Dreams** (Sny).

### ⏳ Timelines (Linie Czasowe)
Wyobraź sobie Timelines jako **punkty zapisu w grze** lub **alternatywne wersje rzeczywistości**.

*   **Po co to jest?** Venom pozwala Ci bezpiecznie eksperymentować. Zanim wprowadzisz ryzykowne zmiany w kodzie, system (lub Ty ręcznie) tworzy "migawkę" (snapshot) obecnego stanu.
*   **Jak to działa dla Ciebie?** Jeśli eksperyment się nie uda, możesz natychmiast cofnąć się do punktu wyjścia, nie tracąc działającego systemu.
*   **User/Core Timelines**: To są Twoje "główne" zapisy – backupy przed refactoringiem, punkty kontrolne projektu. Są cenne i zazwyczaj chcesz je zachować.
*   **Przykład Użycia**: Planujesz duży refactoring nawigacji. Tworzysz Timeline o nazwie "przed-refactorem-nav". Jeśli w połowie pracy kod przestanie się kompilować, jednym kliknięciem przywracasz stan "przed-refactorem-nav".

### 🌙 Dreams (Sny)
Sny to proces **samodoskonalenia** Venoma w czasie wolnym.

*   **Co to jest?** Gdy nie używasz systemu (lub w nocy), Venom analizuje swoją bazę wiedzy i wymyśla hipotetyczne problemy programistyczne, a następnie próbuje je rozwiązać.
*   **Po co?** Każdy rozwiązany "sen" staje się nową umiejętnością (lekcją), którą Venom może wykorzystać w przyszłości, pomagając Tobie.
*   **Dream Timelines**: Każdy sen odbywa się w odizolowanej linii czasowej, aby nie zaśmiecać Twojego głównego projektu. Te dane mogą zajmować dużo miejsca, ale są w pełni odtwarzalne (można je bezpiecznie usuwać).
*   **Przykład**: Venom zauważył, że wczoraj miałeś problem z konfiguracją Nginx. W nocy "przyśnił" sobie scenariusz naprawy pliku `nginx.conf`, przetestował go w izolacji i teraz "wie", jak to zrobić poprawnie, gdy zapytasz o to jutro.

---

## 2. Panel Konfiguracji: Koszty Dysku

W sekcji `/config` (Konfiguracja) znajdziesz panel **"Koszty dysku"**. Służy on do monitorowania zdrowia Twojego środowiska pracy.

### Jak czytać wskaźniki?

Panel dzieli dane na kilka kategorii. Oto najważniejsze z nich, o które możesz pytać:

#### 🟣 Dane: dreaming (timelines)
*   **Co to jest?**: Miejsce zajmowane na dysku przez **Sny** (historyczne symulacje treningowe).
*   **Czy mogę to usunąć?**: **TAK**. To są dane "historyczne". Usunięcie ich nie zepsuje projektu, jedynie stracisz możliwość podejrzenia "jak Venom rozwiązał tamten konkretny sen" (ale wyciągnięta z niego wiedza/lekcja jest już zapisana w pamięci i pozostanie bezpieczna).
*   **Zalecenie**: Jeśli brakuje Ci miejsca na dysku, to pierwszy kandydat do czyszczenia.

#### 🔵 Dane: timelines (user/core)
*   **Co to jest?**: Miejsce zajmowane przez **Twoje** punkty przywracania i backupy projektowe.
*   **Czy mogę to usunąć?**: **OSTROŻNIE**. Usunięcie tych danych oznacza utratę możliwości cofnięcia się do starych wersji projektu. Rób to tylko dla starych, niepotrzebnych już checkpointów.

#### 🟢 Modele LLM
*   **Co to jest?**: Pliki "mózgów" (np. Gemma, Llama). Są bardzo duże (często kilkadziesiąt GB).
*   **Czy mogę to usunąć?**: Jeśli usuniesz model, Venom pobierze go ponownie przy następnym uruchomieniu (co może potrwać i zużyć transfer).

#### 🟡 Build / Cache (np. `web-next/.next`)
*   **Co to jest?**: Pliki tymczasowe generowane przez aplikację, aby działała szybciej.
*   **Czy mogę to usunąć?**: **TAK**. System odbuduje je sobie automatycznie w razie potrzeby. Bezpieczne do czyszczenia w razie awarii.

### Zarządzanie Miejscem
Jeśli wskaźnik użycia dysku świeci się na czerwono:
1.  Sprawdź **Dane: dreaming (timelines)** – zazwyczaj to one rosną najszybciej.
2.  Wyczyść stare cache (np. `.next`).
3.  Przejrzyj swoje **User Timelines** i usuń bardzo stare eksperymenty.

---

## 3. Chat Operator

Zachowanie czatu, stan sesji, toolsy, kontrola runtime i skróty Makefile są opisane w:

- [CHAT_OPERATOR.md](CHAT_OPERATOR.md)
- [CHAT_SESSION.md](CHAT_SESSION.md)
- [CHAT_OPERATOR EN](../CHAT_OPERATOR.md)

Używaj tych dokumentów jako źródła prawdy dla czatu. Ten podręcznik ma pozostać skupiony na ogólnej administracji systemu i wysokopoziomowym workflow.

Ten podręcznik celowo nie wylicza pełnego kontraktu tooli czatu ani pełnej powierzchni targetów `make`; te szczegóły są w `CHAT_OPERATOR.md`.

---

*Dokument ten będzie rozwijany wraz z nowymi funkcjami systemu.*
