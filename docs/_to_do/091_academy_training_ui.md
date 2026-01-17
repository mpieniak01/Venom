# PR 90: Akademia – trenowanie/fine-tuning modeli z poziomu UI

## Cel
Wprowadzić brakujący element strategii Venom: użytkownik ma móc przygotować dataset, uruchomić trening (LoRA/QLoRA) i aktywować nowy adapter z poziomu aplikacji. Zakres obejmuje brakujące zależności ML, API do orkiestracji treningu oraz nowy ekran w `web-next` do kontroli procesu.

## Stan obecny (as-is)
- Backend ma szkielety uczenia (`venom_core/agents/professor.py`, `venom_core/infrastructure/gpu_habitat.py`, `venom_core/learning/dataset_curator.py`, `venom_core/core/model_manager.py`), ale **nie są podłączone** do cyklu życia aplikacji (`main.py` ich nie inicjalizuje) ani do API/dispatcherów. Brak endpointów do datasetu/treningu/statusu/aktywizacji adaptera.
- Konfiguracja zawiera klucze Academy (`config.py`, `services/config_manager.py`) i są widoczne w panelu konfiguracji (`web-next/components/config/parameters-panel.tsx`), jednak UI nie ma ekranu sterowania treningiem ani podglądu datasetów/logów.
- Brak zależności do treningu w `requirements.txt` (unsloth/trl/peft/datasets/bitsandbytes + ewentualne cuda wheels), więc ścieżka GPUHabitat → Unsloth nie wystartuje.
- Brak persystentnej historii treningów/adapters (tylko pamięć w procesie w `Professor.training_history`), brak mapowania adapterów do ModelManager/LLM runtime.
- Brak strumieniowania logów z kontenerów treningowych; brak testów integracyjnych end-to-end (dataset → trening → aktywacja adaptera).

## Zakres PR
1) Backend: pełne API Academy (dataset, trening, statusy, listy modeli/adapterów, aktywacja).
2) Infrastruktura: zależności ML i sanity-check środowiska (GPU/nvidia-toolkit, fallback CPU).
3) UI: ekran Academy w `web-next` (dataset stats, przycisk „Start training”, logi, lista adapterów + aktywacja).
4) Observability i bezpieczeństwo: log stream (SSE/WebSocket), walidacja parametrów, limity zasobów.
5) Dokumentacja i testy (unit + E2E scenariusz start/monitor/aktywacja).

## Plan realizacji
1. **Zależności i środowisko**
   - Dodać do `requirements.txt` pakiety treningowe (unsloth, trl, peft, datasets, bitsandbytes) z uwagami o wersjach CUDA; uaktualnić README/.env.example o wymogi `nvidia-container-toolkit` i opcje CPU fallback.
   - W GPUHabitat dodać szybki self-check (brak Docker/GPU → zwrot controllera z komunikatem, skip start).

2. **Backend API (FastAPI)**
   - Zainicjalizować DatasetCurator + GPUHabitat + Professor + ModelManager w `main.py` (gdy `ENABLE_ACADEMY`), przekazać LessonsStore.
   - Nowy router `api/routes/academy.py` z operacjami: `POST /dataset` (kuracja + statystyki), `POST /train` (start job), `GET /train/{job}/status` (status + tail logów), `GET /adapters` (lista/metadata), `POST /adapters/activate` (hot-swap przez ModelManager/LLM router).
   - Zapisać historię jobów (JSONL w `data/training/jobs.jsonl` + metadane adapterów), aby UI miało źródło prawdy po restarcie.
   - Integracja z ModelManager/LLMServerController: możliwość aktywacji adaptera (PEFT) oraz rollback do bazowego modelu.

3. **UI web-next**
   - Nowy widok „Academy” (np. `/academy`) z sekcjami: statystyki LessonsStore/dataset, przycisk kuracji, formularz parametrów treningu (prefill z `.env`), live log viewer (SSE/WebSocket), tabela jobów z statusami, lista adapterów z akcją „Aktywuj”.
   - Hooki API w `lib/api-client.ts` + obsługa błędów (brak GPU/unsloth → komunikat).

4. **Observability i bezpieczeństwo**
   - Ograniczenia parametrów (range check dla lr/epochs/batch_size), walidacja ścieżek datasetu, gating zezwolenia (np. tylko ADMIN).
   - Stream logów z kontenera z ograniczeniem rozmiaru; cleanup kontenerów po zakończeniu.

5. **Testy i dokumentacja**
   - Testy jednostkowe: generator datasetu, walidacja API, mapowanie statusów kontenera.
   - Test E2E (mock Docker) dla ścieżki dataset → train → status → aktywacja.
   - Uzupełnić `docs/THE_ACADEMY.md` + README o nowy ekran i API.

## Kryteria akceptacji
- API pozwala utworzyć dataset, wystartować trening, odczytać status/logi i aktywować adapter; dane przetrwają restart backendu.
- UI pokazuje statystyki/dostępne adaptery i umożliwia start + monitoring joba bez ręcznego CLI.
- Zależności treningowe są dostępne z `pip install -r requirements.txt` (z opisem wymagań GPU/CPU).
- ModelManager/LLM runtime respektuje aktywowany adapter i umożliwia rollback.
- Logi treningu są dostępne (tail) i czyszczone po zakończeniu kontenera.

## Ryzyka/uwagi
- Wersje unsloth/trl/peft muszą być zgodne z aktualnym torch/CUDA; potrzebny lock/sekcja w README.
- Środowiska bez GPU muszą mieć jasny komunikat i tryb offline (mock/trening CPU z małymi modelami).
- Stabilność dockerowania: konieczne timeouty i auto-cleanup zawieszonych kontenerów.
