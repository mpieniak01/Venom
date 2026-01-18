# Release Review

## Status: Release Candidate 1
To podsumowanie obejmuje zmiany oczekujące na zatwierdzenie.

### 1. Dokumentacja (Documentation)
- **Master Vision (v2.0):** Zaktualizowano `VENOM_MASTER_VISION_V1.md` (PL/EN) o sekcję "Wizja Docelowa 2.0" oraz integrację IoT (Google Home).
- **Cleanup (Task 095):** Przygotowano plan refaktoryzacji (`docs/_to_do/095_refaktoryzacja_architektury.md`).
- **User Guide (Task 099):** Stworzono drafty `OPERATOR_MANUAL.md` (PL/EN).
- **Process Engine (v2.0):** Dodano koncepcję `PROCESS_ENGINE_CONCEPT.md`.
- **Inne:** Aktualizacje w `TREE.md`, `README.md`, `THE_CHRONOMANCER.md` (spójność).

### 2. Backend (Venom Core)
- **LLM Controller:** Optymalizacje w `venom_core/core/llm_server_controller.py` (obsługa vLLM/Ollama).
- **Benchmark Service:** Poprawki w `services/benchmark.py` i `api/routes/benchmark.py` (stabilność, argumenty).
- **System API:** Zmiany w `api/routes/system.py` (metryki, monitoring).
- **Memory API:** Zmiany w `api/routes/memory.py` (cache flush).
- **Config:** Zmiany w `venom_core/config.py`.

### 3. Frontend (Web Next)
- **Benchmark UI:** Nowe komponenty `benchmark-results.tsx` i hooki `use-benchmark.ts`.
- **Brain UI:** Zmiany w `brain-home.tsx` (zakładki, hygiene panel).
- **Config Panel:** Updates w `services-panel.tsx`.
- **Layout:** `author-signature.tsx` (Social links), sidebar updates.
- **i18n:** Aktualizacje tłumaczeń (PL/EN/DE).

### 4. Nowe Komponenty (Untracked)
- `web-next/components/brain/cache-management.tsx`
- `web-next/components/brain/hygiene-panel.tsx`
- `web-next/components/layout/author-signature.tsx`

### 5. Runtime / Start Stosu
- **Makefile:** Start stosu respektuje `ACTIVE_LLM_SERVER` z `.env` (Ollama vs vLLM), zatrzymuje drugi runtime i używa właściwego healthchecka.
- **Makefile:** `make start` nie wywala błędem, gdy UI już działa (pomija start UI).
- **Backend start:** Autokorekta modelu LLM przy starcie, gdy skonfigurowany model nie istnieje u aktywnego providera.

### 6. LLM / Modele
- **Model registry:** Aktywacja modelu Ollama potrafi sama dołożyć model do manifestu, jeśli istnieje w Ollama.
- **Runtime params:** Bezpieczne ograniczenie `max_tokens` oraz retry po błędzie z kontekstem (naprawa regexa).
- **Prompt trimming:** Ucinanie promptu w trybie direct (`/llm/simple`) dla vLLM przy małym kontekście.
- **Hidden prompts:** Pomijanie hidden prompts przy małym kontekście vLLM i czyszczenie po restarcie (boot_id).
- **Learning log:** Czyszczenie `requests.jsonl` po restarcie (boot_id).
- **State:** Czyszczenie `state_dump.json` po restarcie (boot_id).

### 7. Frontend (Web Next) – LLM
- **LLM UI:** Dodany brakujący import `activateRegistryModel` w Cockpit (zapobiega crashowi przy aktywacji).

### 8. Testy
- **ResearcherAgent:** Test limitu tokenów uwzględnia Ollama (`num_predict` w `extension_data`) i vLLM cap.

## Plan Weryfikacji
1. **Tests:** Uruchomienie pełnego suite testów (`make test` / `pytest`).
2. **Pre-commit:** Sprawdzenie lintów i formatowania.
3. **Fixes:** Naprawa ewentualnych regresji przed merge.
