# Czat i voice: admission oraz środowisko CUDA

## Start GPU

API uruchamiane przez `scripts/dev/start_stack.sh` korzysta z wrappera
`scripts/llm/with_gpu_libraries.py`. Wrapper przed startem procesu dodaje biblioteki
`nvidia/*/lib` z venv wybranego interpretera oraz sterownik WSL do ścieżki loadera.
Nie importuje Torch, nie instaluje pakietów i nie zmienia globalnego środowiska.
Obejmuje to układ CUDA 13 `nvidia/cu13/lib`.

Dla syntezy GPU ustaw `TTS_USE_CUDA=true`. Załadowany głos musi mieć
`CUDAExecutionProvider`; niepowodzenie nie może być przedstawione jako poprawna
synteza ciszy. Wybór jest zachowany przy przełączaniu modelu TTS. Status audio
udostępnia `tts_device`, `tts_execution_providers` i `tts_error_code`.
`tts_dependency_unavailable` oznacza także błąd biblioteki natywnej, np. CUDA,
nie tylko brak samego pakietu Piper. Nie zastępuj lokalnej instalacji GPU CPU
w celu usunięcia błędu loadera.

## HTTP 409 i kontrolowane recovery

`runtime_busy` może oznaczać trwałą kwarantannę po niepewnym zakończeniu pracy.
Odczytaj snapshot admission, proces właściciela oraz ledger w trybie read-only.
Nie usuwaj wpisów SQL ani pliku bazy na podstawie samego wieku/PID.

Dla osieroconej operacji hosta wymagane są wszystkie dowody:

1. API zostało kontrolowanie zatrzymane, a poprzedni proces już nie działa.
2. Ledger nie zawiera lease eksperymentu ani nowej/obcej operacji. Zapisana
   tożsamość konkretnej operacji jest porównana ponownie pod blokadą hosta.
3. Backend obsługujący operację jest bezczynny: dla Ollama `/api/ps` zwraca
   pustą listę i nie działa runner. Pozostałe generacyjne workery są zatrzymane.
   Samo rozłączenie klienta, `empty_cache()` lub brak PID API nie wystarcza.
4. Zaufany callback ponownie sprawdza te warunki w publicznym
   `get_runtime_admission().recover(confirm_quiescent=...)`.
5. Po starcie przez istniejący launcher potwierdź `available/0`, spójny runtime,
   odpowiedź czatu i rzeczywistą syntezę GPU. Ping/pong voice nie potwierdza
   rozpoznawania mowy ani odpowiedzi modelu.

MAF zwalnia admission po rzeczywistym odrzuceniu HTTP przed generacją. Retry
nie może zamaskować wcześniejszego niepewnego żądania. Strumień bez jawnego końca,
timeout i anulowanie nadal wymagają potwierdzenia bezczynności przed recovery.
