# Plan Wdrożenia: Refaktoryzacja DX i Standardyzacja Skills (nr 100)

**Cel:** Poprawa Developer Experience (DX) i jakości kodu poprzez wprowadzenie klasy bazowej dla umiejętności (`BaseSkill`), usunięcie duplikacji kodu oraz stworzenie dokumentacji dla twórców.

**Krytyczne:** Każda zmiana musi być zweryfikowana testami. System po refaktoryzacji musi działać identycznie jak przed.

---

## 1. Zakres Zmian (Scope)

### A. Core (`venom_core/execution/skills/base_skill.py`)
- [NEW] Klasa `BaseSkill`:
    - Automatyczna inicjalizacja loggera (`self.logger`).
    - Metoda pomocnicza `safe_execute` lub dekorator do obsługi wyjątków.
    - Metody pomocnicze do walidacji ścieżek (przeniesione z `FileSkill`).

### B. Refaktoryzacja Umiejętności
- Zmiana dziedziczenia: `GitSkill(BaseSkill)`, `ChronoSkill(BaseSkill)`, `FileSkill(BaseSkill)`.
- Usunięcie zduplikowanego kodu (boilerplate `logger = ...`, `try/except`).

### C. Dokumentacja
- [NEW] `docs/DEV_GUIDE_SKILLS.md`: Przewodnik "Jak stworzyć nowego Skilla".

### D. Testy (Krytyczne)
- [NEW] `tests/test_base_skill.py`: Testy jednostkowe dla nowej klasy bazowej.
- Weryfikacja istniejących testów (`test_git_skill.py` jeśli istnieją, lub stworzenie nowych testów regresyjnych).

---

## 2. Plan Realizacji

### Faza 1: Fundamenty
1.  [x] Utworzenie `venom_core/execution/skills/base_skill.py`.
2.  [x] Napisanie testów jednostkowych dla `BaseSkill`.

### Faza 2: Migracja (Iteracyjna)
3.  [x] Refaktoryzacja `FileSkill` (jako wzorcowa implementacja).
4.  [x] Refaktoryzacja `GitSkill`.
5.  [x] Refaktoryzacja `ChronoSkill`.

### Faza 3: Dokumentacja
6.  [x] Stworzenie `docs/DEV_GUIDE_SKILLS.md`.

---

## 3. Strategia Testowania
- **Unit Tests:** `pytest tests/` dla każdej modyfikowanej klasy.
- **Manual Verification:** Uruchomienie przykładowego scenariusza użycia GitSkill po refaktoryzacji.
