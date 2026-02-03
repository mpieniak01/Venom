# 076: PR coverage + testy o wysokim ROI — raport realizacji

## Cel i zakres
Podniesienie jakości raportu coverage przez odcięcie szumu oraz dołożenie testów
jednostkowych z wysokim ROI (bez E2E).

## Zmiany w coverage
- Dodano `.coveragerc` z filtrowaniem:
  - omit: `*/__init__.py`, `venom_core/main.py`, `tests/*`.
  - exclude_lines: `if __name__ == "__main__":`, `pragma: no cover`, gałęzie debug/logging.
- Efekt: raport skupia się na logice domenowej zamiast glue/boilerplate.

## Nowe testy
- `tests/test_runtime_controller_roi.py`:
  - ścieżki decyzyjne zależności usług oraz scenariusz „already running”.
- `tests/test_audio_stream_handler_roi.py`:
  - kontrola start/stop nagrywania i VAD (RMS).
- `tests/test_system_routes_roi.py`:
  - walidacja zależności (metrics collector), IoT bridge off, brak usługi.
- `tests/test_executive_agent_roi.py`:
  - parsowanie roadmapy i tworzenie Vision/Milestone/Task.
- `tests/test_main_setup_router_dependencies.py`:
  - poprawne powiązanie zależności routerów w `main.py`.
- `tests/test_git_skill_roi.py`:
  - brak repo + komunikat konfliktu merge.
- `tests/test_ingestion_engine_roi.py`:
  - detekcja typów plików, chunking, walidacja URL.
- `tests/test_desktop_sensor_roi.py`:
  - filtr prywatności i status sensora.
- `tests/test_model_manager_roi.py`:
  - rejestracja/aktywacja wersji, porównanie metryk, quota guard, walidacja adaptera.

## Wpływ na coverage
- Pokrycie istotnych ścieżek w:
  - `venom_core/services/runtime_controller.py`
  - `venom_core/api/routes/system.py`
  - `venom_core/api/audio_stream.py`
  - `venom_core/agents/executive.py`
  - `venom_core/main.py`
  - `venom_core/execution/skills/git_skill.py`
  - `venom_core/memory/ingestion_engine.py`
  - `venom_core/perception/desktop_sensor.py`
  - `venom_core/core/model_manager.py`

## Ryzyka i ograniczenia
- Testy omijają realne procesy/IO (mocki) — brak integracji z usługami systemowymi.
- `main.py` testowany tylko w zakresie `setup_router_dependencies`.
