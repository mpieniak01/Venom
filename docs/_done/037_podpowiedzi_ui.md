# Zadanie: Implementacja systemu podpowiedzi (UX Helpers) i odkrywania funkcji

**Priorytet:** Średni/Wysoki
**Cel:** Ułatwienie użytkownikowi interakcji z systemem poprzez wizualne podpowiedzi (Chips) oraz komendę `/help`, eliminując syndrom "pustego pola tekstowego".

## 1. Frontend: Quick Action Chips (Sugestie Startowe)
**Plik:** `web/templates/index.html`, `web/static/css/app.css`
**Opis:** Dodać sekcję z kafelkami/przyciskami (Chips) pod wiadomością powitalną, sugerującymi dostępne scenariusze użycia.
**Wymagania:**
- Dodać kontener `.suggestion-grid` wewnątrz `.welcome-message`.
- Zdefiniować style dla przycisków sugerujących akcje (np. ikona + krótki tekst).
- Przykładowe kategorie:
  - 🎨 **Kreacja:** "Stwórz logo dla fintechu"
  - ☁️ **DevOps:** "Sprawdź status serwerów"
  - 🧠 **Research:** "Analiza trendów AI 2024"
  - 🛠️ **Kod:** "Napisz testy dla modułu API"

## 2. Frontend: Obsługa Logiki Sugestii
**Plik:** `web/static/js/app.js`
**Opis:** Kliknięcie w Chip powinno automatycznie wpisać treść do pola `taskInput` i opcjonalnie od razu wysłać wiadomość.
**Wymagania:**
- Dodać event listenery dla klasy `.suggestion-chip`.
- Po kliknięciu: przepisz tekst sugestii do `#taskInput` i ustaw focus.

## 3. Backend: Obsługa komendy `/help`
**Plik:** `venom_core/agents/chat.py` (lub `router`)
**Opis:** System powinien reagować na wpisanie "pomoc", "help" lub "co potrafisz?".
**Wymagania:**
- Zaimplementować wykrywanie intencji `HELP_REQUEST`.
- Zwrócić sformatowaną odpowiedź (Markdown/Widget) listującą dostępne Agenty i ich umiejętności na podstawie załadowanych pluginów w `SkillManager`.
- Odpowiedź powinna być dynamiczna (nie hardcoded text), generowana na podstawie `self.kernel.skills`.

## 4. Frontend: Kontekstowe Widgety Pomocy
**Plik:** `web/static/js/app.js` (metoda `renderCardWidget`)
**Opis:** Wykorzystać istniejący mechanizm Widgetów do wyświetlania pomocy.
**Wymagania:**
- Jeśli użytkownik zapyta o pomoc, Backend powinien zwrócić `CardWidget` z listą akcji (`widget.data.actions`), które po kliknięciu wywołują konkretne intencje.
- Dodać obsługę `submit_intent` w przyciskach kart (obecnie jest tam tylko `console.log` - patrz komentarz TODO w kodzie).

## Kryteria Akceptacji (DoD)
1. Po wejściu na stronę użytkownik widzi min. 4 kafelki z przykładami użycia.
2. Kliknięcie kafelka pozwala na szybkie rozpoczęcie zadania.
3. Wpisanie "Co potrafisz?" zwraca czytelną listę dostępnych modułów (nie surowy JSON).
4. `CardWidget` potrafi wysłać komendę zwrotną do backendu po kliknięciu przycisku akcji.
