# 095: Refaktoryzacja Architektury (Cleanup & Decoupling)

Status: Do realizacji.

## 1. Wykrywanie Martwego Kodu (Dead Code Analysis)
Zidentyfikowano pliki stanowiące "fairy tales" (zaślepki bez implementacji):

1.  **`venom_core/agents/writer.py`** (21 B) - Pusty moduł.
2.  **`venom_core/perception/antenna.py`** (22 B) - Pusty moduł.
3.  **`venom_core/infrastructure/onnx_runtime.py`** (27 B)
    -   *Status:* STUB (Pusty plik).
    -   *Wyjaśnienie:* Plik jest pusty. Obsługa modeli ONNX (Phi3, TTS) znajduje się w `model_manager.py` oraz `audio_engine.py`. Usuwamy tylko ten martwy plik, **nie** technologię ONNX z projektu.

**Akcja:** Fizyczne usunięcie plików i czyszczenie importów.

## 2. Wykrywanie Monolitów (Backend)
Zidentyfikowano moduły o zbyt dużej odpowiedzialności (God Objects):

1.  **`venom_core/core/orchestrator/orchestrator_core.py`** (~82KB, 2115 linii)
    -   *Problem:* Zarządza wszystkim: task dispatch, kernel, event broadcasting, tracing, error handling.
    -   *Rekomendacja:* Wydzielenie `TaskManager`, `EventBroadcaster`, `KernelLifecycleManager`.

2.  **`venom_core/api/routes/system.py`** (~49KB, 1492 linii)
    -   *Problem:* Router "od wszystkiego": metrics, services, scheduler, IoT, LLM control, Cost Guard.
    -   *Rekomendacja:* Podział na `routes/metrics.py`, `routes/llm.py`, `routes/services.py`.

## 3. Analiza Frontend (Next.js)
Struktura katalogów `web-next` jest generalnie poprawna (podział na `components/ui`, `layout` itp.), ALE wykryto krytyczny monolit:

1.  **`web-next/components/cockpit/cockpit-home.tsx`** (~202KB, **5379 linii**!)
    -   *Problem:* Ogromny plik zawierający logikę całego dashboardu, renderowanie 3D, wykresy, logikę biznesową i style.
    -   *Rekomendacja:* Bezwzględny podział na mniejsze komponenty (np. `CockpitVisualizer`, `CockpitMetrics`, `CockpitControlPanel`).

## 4. Standaryzacja CSS (SCC)
-   **Global Styles:** Prawidłowo używany jeden plik `app/globals.css` + Tailwind.
-   **Inline Styles:** Wykryto użycie `style={{ ... }}` wewnątrz TSX (szczególnie w `cockpit-home.tsx` i `inspector/page.tsx`).
    -   *Problem:* Mieszanie logiki stylów (np. `width: 100%`) z klasami Tailwind.
    -   *Rekomendacja:* Zamiana statycznych styli inline na klasy Tailwind (np. `w-full h-full`). Pozostawienie inline tylko dla wartości dynamicznych (np. progress bar percentage, 3D transform coordinates).

## Plan Wykonawczy
1.  **Faza 1 (Szybka):** Usunięcie martwego kodu (Writer, Antenna, ONNX).
2.  **Faza 2 (Backend):** Refaktoryzacja `system.py` (najłatwiejszy monolit do podziału).
3.  **Faza 3 (Frontend):** Rozbicie `cockpit-home.tsx` (wymaga ostrożności, critical path).
4.  **Faza 4 (Backend):** Refaktoryzacja `Orchestrator` (szczególnie ryzykowna, wymaga solidnych testów).
