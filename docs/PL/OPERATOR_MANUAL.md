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

## 3. Profile Wydajności (Runtime)

W panelu konfiguracji możesz też przełączać tryby pracy Venoma (Profile):

*   **⚡ Full Stack**: Uruchamia wszystko (AI, Backend, UI, Bazy). Do normalnej, pełnej pracy.
*   **🍃 Light**: Uruchamia tylko Backend i UI. Oszczędza baterię/zasoby, gdy nie potrzebujesz generowania kodu przez AI (np. tylko przeglądasz pliki).
*   **🛑 LLM OFF**: Całkowite wyłączenie modeli językowych. Przydatne na słabszych maszynach lub gdy chcesz pracować manualnie.

---

## 4. Rekomendacje Sprzętowe (Hardware)

Wybór odpowiedniego silnika AI (Runtime) ma kluczowe znaczenie dla stabilności systemu, zwłaszcza na słabszym sprzęcie.

### 🐢 Ollama (Zalecane dla "Low-Spec")
Jeśli Twój komputer ma:
*   Mniej niż 16GB RAM.
*   Słabą kartę graficzną (poniżej 8GB VRAM) lub zintegrowaną grafikę.
*   Problemy ze stabilnością działania vLLM (błędy OOM, crashe).

**ZALECENIE: Wybierz OLLAMA.**
Jest to silnik zoptymalizowany pod kątem niskiego zużycia zasobów. Działa nieco wolniej, ale jest znacznie stabilniejszy i zużywa mniej pamięci VRAM/RAM niż vLLM. Idealny do pracy na laptopach i starszych stacjach roboczych.

### 🚀 vLLM (Zalecane dla "High-Performance")
Jeśli dysponujesz:
*   Mocną kartą graficzną NVIDIA (np. RTX 3090/4090, A100).
*   Dużą ilością pamięci VRAM (>12GB).

**ZALECENIE: Wybierz vLLM.**
Oferuje on bezkonkurencyjną szybkość (tokeny na sekundę), ale jest bardzo wymagający („chciwy”) na pamięć. Na słabszych konfiguracjach może powodować niestabilność systemu.

---

## 5. Panel Konfiguracji: Parametry Systemu

Oprócz zarządzania kosztami dysku i usługami, zakładka `Parametry` w `/config` pozwala na sterowanie zachowaniem agentów.

*   **Tryb AI (AI Mode)**: Decyduje, czy Venom działa w pełni lokalnie ("Local"), czy hybrydowo ("Hybrid" - np. ciężkie zadania w chmurze). Domyślnie: **Local**.
*   **Hive (Przetwarzanie rozproszone)**: Włącza/wyłącza architekturę rozproszoną (Queue Worker).
*   **Shadow (Desktop Awareness)**: Jeśli włączone, agent działający w tle monitoruje zdarzenia systemowe, próbując proaktywnie wykrywać problemy.
*   **Ghost (GUI Automation)**: Zezwala Venomowi na sterowanie myszką i klawiaturą (RPA). **Domyślnie wyłączone** ze względów bezpieczeństwa.

> [!TIP]
> Zmieniając parametry (np. wyłączając Shadow), system może wymagać restartu, aby zwolnić zasoby.

---

## 6. Rozwiązywanie Problemów (Troubleshooting)

Typowe sytuacje, które możesz napotkać jako Operator:

### 🔴 System nie odpowiada ("Connection Refused")
*   **Przyczyna**: Kontener dockera (`venom-backend`) nie działa lub się restartuje.
*   **Rozwiązanie**: Sprawdź logi w terminalu. Upewnij się, że Docker Desktop jest uruchomiony. W ostateczności wykonaj `docker-compose restart`.

### 🟡 Model "mieli" w nieskończoność (Timeout)
*   **Przyczyna**: Wybrany model jest zbyt duży dla Twojej karty graficznej (vLLM OOM) lub zbyt wolny (CPU).
*   **Rozwiązanie**:
    1.  Przełącz Runtime na **Ollama** w `/config`.
    2.  Wybierz mniejszy model (np. `gemma:2b` lub `llama3:8b-quantized`).

### 🟠 Brak miejsca na dysku
*   **Przyczyna**: Nagromadzenie "Snów" (Dream Timelines) lub cache modeli.
*   **Rozwiązanie**: Wejdź w `/config` -> Usługi -> Storage i wyczyść sekcję **Dreams** oraz **Cache**.

### ⚪ Interface jest po angielsku, mimo że chcę Polski
*   **Przyczyna**: Ustawienia przeglądarki lub brak zapisanego wyboru.
*   **Rozwiązanie**: Kliknij ikonę flagi/języka w pasku bocznym (Sidebar) i wybierz "PL". Ustawienie zostanie zapamiętane.

---

## 7. Powiązana dokumentacja Workflow

1. `docs/PL/THE_WORKFLOW_CONTROL.md` - przewodnik operatorski kompozytora workflow.
2. `docs/PL/WORKFLOW_CONTROL_PLANE_API.md` - kontrakt API i reason code.

---

*Dokument ten będzie rozwijany wraz z nowymi funkcjami systemu.*
