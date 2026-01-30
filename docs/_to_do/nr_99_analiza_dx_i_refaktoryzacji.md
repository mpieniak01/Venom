# Analiza Jakości Kodu i DX (Developer Experience)

**Data:** 2026-01-30
**Autor:** Antigravity (Agent)
**Status:** Zakończone

---

## 1. Wnioski z Analizy

Przeanalizowano kluczowe komponenty `venom_core`: `swarm.py` (integracja AutoGen), `agents/base.py` (logika agentów) oraz przykładowe umiejętności (`skills/`).

### Mocne Strony
1.  **Wysoka Spójność:** Wszystkie skille podążają za tym samym wzorcem (dekoratory `@kernel_function`, typowanie `Annotated`, obsługa błędów try/except).
2.  **Solidne Typowanie:** Kod jest dobrze otypowany, co ułatwia pracę z IDE.
3.  **Separacja Odpowiedzialności:** Logika biznesowa (np. Git, Chronos) jest wydzielona z samych klas Skill (które pełnią rolę adapterów dla LLM).

### Obszary do Poprawy (DX & Maintenance)
1.  **Boilerplate w Skillach:** Każda metoda skilla powtarza ten sam schemat obsługi błędów:
    ```python
    try:
        ...
    except Exception as e:
        logger.error(...)
        return f"Error: {e}"
    ```
    To narusza zasadę DRY i utrudnia zmianę strategii logowania błędów w przyszłości.

2.  **Brak Klasy Bazowej:** Skille są luźnymi klasami. Brak `BaseSkill` uniemożliwia współdzielenie logiki (np. dostępu do `SETTINGS` czy standardowego loggera).

3.  **Skryta Integracja AutoGen:** Logika mapowania funkcji Semantic Kernel na AutoGen Tools w `swarm.py` jest skomplikowana ("magiczna") i oparta na introspekcji. Może być trudna do debugowania.

4.  **Brak Dokumentacji dla Contributorów:** Nowy programista chcący dodać narzędzie musi "zgadywać" wzorzec na podstawie istniejących plików.

---

## 2. Rekomendacje Refaktoryzacji

Zamiast wdrażać zewnętrzne standardy (jak MCP), proponuję **wewnętrzną standaryzację**, która ułatwi rozwój systemu:

### A. Wprowadzenie `BaseSkill`
Stworzenie klasy bazowej dla wszystkich umiejętności:
```python
class BaseSkill:
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    def safe_execute(self, func, *args, **kwargs):
        # Centralna obsługa błędów
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.logger.error(f"Skill error: {e}")
            return f"❌ Błąd wykonania: {e}"
```
*Alternatywnie: Dekorator `@safe_skill_execution`.*

### B. Dokumentacja "How-To"
Dodanie pliku `docs/DEV_GUIDE_SKILLS.md` opisującego:
- Jak stworzyć nowy skill.
- Wymagane dekoratory i typy.
- Zasady obsługi błędów (zwracaj string, nie rzucaj wyjątków).

### C. Upraszczenie `swarm.py`
Refaktoryzacja `_register_venom_functions` w celu zwiększenia czytelności (dodanie typów, wydzielenie logiki konwersji typów SK -> AutoGen).

---

## 3. Plan Działania (Next Steps)
Czy chcesz, abym zrealizował któryś z powyższych punktów?

1.  **Stworzyć `BaseSkill` / Dekorator obsługi błędów?**
2.  **Napisać `DEV_GUIDE_SKILLS.md`?**
3.  **Zostawić jak jest (status quo)?**
