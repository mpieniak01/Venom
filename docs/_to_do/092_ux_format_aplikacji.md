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
*   **Status (kod + UI):** Zrealizowane. Endpoint istnieje, UI w Brain → Hygiene (Cache Management) ma akcję Flush. Potwierdzone na widoku `/brain` (zakładka Higiena).

### 2. Unifikacja Panelu Higieny (Brain Hygiene)
*   **Problem:** Funkcje czyszczenia są rozrzucone (Cockpit: Session, Brain: Global/Lessons).
*   **Zadanie:**
    *   Zebrać wszystkie funkcje "sprzątające" w jednym spójnym widoku (np. `Brain -> Maintenance Tab`).
    *   Ujednolicić komunikaty (Toast messages) i potwierdzenia (Confirm Dialogs).
*   **Status (kod + UI):** Zrealizowane. Brain → Hygiene zawiera Cache Management i Lesson Pruning, z confirm dialogami.

### 3. Weryfikacja UX (Format)
*   Upewnić się, że wskaźniki użycia pamięci (ikony 🎓/🧠 w czacie) są czytelne i działają poprawnie (wynik walidacji 088).
*   Sprawdzić responsywność nowych paneli na mobile (Rider-Pi scenario).
*   **Status (manual + e2e):** Ikony 🎓/🧠 potwierdzone testami E2E. Pozostaje mobile.

## Kluczowe aspekty z analizy (kontrakt danych)
- Brain → Hygiene korzysta z:
  - `DELETE /api/v1/memory/cache/semantic` (Flush Semantic Cache)
  - `DELETE /api/v1/memory/global` (Wipe Global Memory)
  - `GET /api/v1/lessons/stats` (Statystyki lekcji: `total_lessons`, `tag_distribution`)
  - `POST /api/v1/lessons/dedupe`, `DELETE /api/v1/lessons/purge`
  - `DELETE /api/v1/lessons/prune/ttl`, `.../prune/tag`, `.../prune/latest`
- Badge "Węzły/Krawędzie" w Brain pobiera:
  - Memory: `/api/v1/memory/graph` → `stats.nodes/edges` (zgodne)
  - Repo: `/api/v1/graph/summary` → backend zwraca `nodes/edges/last_updated` oraz zachowuje `total_nodes/total_edges`.
- Pole "Aktualizacja" w Brain ma pokrycie (`lastUpdated`/`last_updated`) z `/api/v1/graph/summary`.

## Status na dziś
- [x] Endpointy cache + UI "Cache Management" (Brain → Hygiene).
- [x] Unifikacja panelu higieny w Brain + confirm dialogi.
- [x] Weryfikacja UX: ikony 🎓/🧠 w czacie (E2E).
- [x] Ujednolicony kontrakt `/api/v1/graph/summary` (nodes/edges/last_updated) z zachowaniem kompatybilności wstecznej.

## Zakres wyłączony z PR
- [ ] Weryfikacja responsywności paneli na mobile (Rider‑Pi scenario) — **odkładamy poza ten PR**.

## Dodatkowy zakres (w tym PR)
- [x] Dodać tryb zwiniętego menu bocznego (minimalistyczny — tylko ikony).
- [x] Wykorzystać istniejące ikony modułów/ekranów jako reprezentację pozycji menu.
- [x] Dodać przełącznik zwijania/rozwijania w pasku bocznym.
- [x] Zapewnić płynną animację przejścia (wejście/wyjście, szerokość, tooltips).

## Uwaga z testów E2E (27.01.2026)
- Dodano testy `web-next/tests/chat-context-icons.spec.ts`.
- Scenariusz "pokazuje 🎓/🧠 gdy context_used zawiera lessons/memory_entries" **przechodzi** po naprawie przepływu `contextUsed`.

## Oczekiwany Rezultat
Aplikacja ma sprawiać wrażenie kompletnego "kokpitu", gdzie żaden proces (nawet cache) nie dzieje się "za plecami" użytkownika bez możliwości interwencji.

## Powiązane pliki
- `venom_core/api/routes/memory.py`
- `web-next/components/brain/lesson-pruning.tsx`
- `docs/ARCHITECTURE_REVIEW.md` (Wersja 1.0)
