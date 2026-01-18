# 092: Format Aplikacji i Domknięcie UX (Conscious User)

## Kontekst
W ramach zadań `088` (Memory Hygiene) i `090` (Semantic Cache) wdrożono zaawansowane mechanizmy zarządzania pamięcią i optymalizacji czatu backendowego. Audyt UI wykazał jednak, że interfejs użytkownika (Frontend) nie nadążył w pełni za tymi zmianami, pozostawiając pewne luki w kontroli ("Blind Spots"), które stoją w sprzeczności z filozofią "Single Conscious User".

## Cel
Dopracowanie "formatu aplikacji" (UI/UX), aby każdy mechanizm backendowy (Cache, Memory, Lessons) miał swoją reprezentację w interfejsie i podlegał pełnej kontroli użytkownika.

## Zakres Prac

### 1. Semantic Cache Control (Luka z 090)
*   **Problem:** Obecnie Semantic Cache (ukryte prompty) jest "czarną skrzynką". Użytkownik nie może go wyczyścić bez dostępu do terminala.
*   **Zadanie:**
    *   Backend: Dodać endpoint `DELETE /api/v1/memory/cache/semantic` (lub rozszerzyć `/global` o opcję `include_cache=true`).
    *   Frontend: Dodać sekcję "Cache Management" w Settings lub Brain -> Hygiene.
    *   UI: Przycisk "Flush Semantic Cache" z licznikiem wpisów.

### 2. Unifikacja Panelu Higieny (Brain Hygiene)
*   **Problem:** Funkcje czyszczenia są rozrzucone (Cockpit: Session, Brain: Global/Lessons).
*   **Zadanie:**
    *   Zebrać wszystkie funkcje "sprzątające" w jednym spójnym widoku (np. `Brain -> Maintenance Tab`).
    *   Ujednolicić komunikaty (Toast messages) i potwierdzenia (Confirm Dialogs).

### 3. Weryfikacja UX (Format)
*   Upewnić się, że wskaźniki użycia pamięci (ikony 🎓/🧠 w czacie) są czytelne i działają poprawnie (wynik walidacji 088).
*   Sprawdzić responsywność nowych paneli na mobile (Rider-Pi scenario).

## Oczekiwany Rezultat
Aplikacja ma sprawiać wrażenie kompletnego "kokpitu", gdzie żaden proces (nawet cache) nie dzieje się "za plecami" użytkownika bez możliwości interwencji.

## Powiązane pliki
- `venom_core/api/routes/memory.py`
- `web-next/components/brain/lesson-pruning.tsx`
- `docs/ARCHITECTURE_REVIEW.md` (Wersja 1.0)
