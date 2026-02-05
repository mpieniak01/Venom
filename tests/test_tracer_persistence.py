import asyncio
import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from venom_core.core.tracer import RequestTracer, TraceStatus


@pytest.mark.asyncio
async def test_tracer_persistence():
    # Tworzymy plik tymczasowy na historię
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        trace_path = Path(tmp.name)

        # 1. Inicjalizacja tracera z plikiem
        tracer = RequestTracer(trace_file_path=str(trace_path))

        # 2. Utworzenie śladu
        req_id = uuid4()
        tracer.create_trace(req_id, "Test prompt")
        tracer.add_step(req_id, "Component", "Action", "ok", "Details")
        tracer.update_status(req_id, TraceStatus.COMPLETED)

        # Weryfikacja zapisu w pamięci
        assert tracer.get_trace_count() == 1

        # Czekamy na asynchroniczny zapis
        await asyncio.sleep(1.2)

        # 3. Weryfikacja zapisu na dysku (bez asynchronii w save_traces - proste sprawdzenie)
        assert trace_path.exists()
        content = trace_path.read_text()
        data = json.loads(content)
        assert len(data) == 1
        assert data[0]["request_id"] == str(req_id)
        assert data[0]["prompt"] == "Test prompt"
        assert len(data[0]["steps"]) == 1

        # 4. Symulacja restartu - nowa instancja tracera z tym samym plikiem
        new_tracer = RequestTracer(trace_file_path=str(trace_path))

        # 5. Weryfikacja odczytu
        assert new_tracer.get_trace_count() == 1
        loaded_trace = new_tracer.get_trace(req_id)
        assert loaded_trace is not None
        assert loaded_trace.request_id == req_id
        assert loaded_trace.prompt == "Test prompt"
        assert loaded_trace.status == TraceStatus.COMPLETED


if __name__ == "__main__":
    # Ręczne uruchomienie dla pewności w środowisku bez pytest
    asyncio.run(test_tracer_persistence())
    print("Test passed!")
