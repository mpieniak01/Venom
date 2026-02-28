from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from venom_core.api.routes import academy_conversion
from venom_core.core import model_registry_providers
from venom_core.core.service_monitor import ServiceHealthMonitor
from venom_core.execution.onnx_llm_client import GENAI_CONFIG_FILENAME, OnnxLlmClient


@contextmanager
def _dummy_lock(_path: Path):
    yield


def test_onnx_path_resolution_and_message_format(tmp_path: Path):
    model_dir = tmp_path / "model"
    nested = model_dir / "nested"
    nested.mkdir(parents=True)
    (nested / GENAI_CONFIG_FILENAME).write_text("{}", encoding="utf-8")

    settings = SimpleNamespace(
        ONNX_LLM_ENABLED=True,
        ONNX_LLM_MODEL_PATH=str(model_dir),
        ONNX_LLM_EXECUTION_PROVIDER="cpu",
        ONNX_LLM_PRECISION="int4",
        ONNX_LLM_MAX_NEW_TOKENS=32,
        ONNX_LLM_TEMPERATURE=0.1,
    )
    client = OnnxLlmClient(settings=settings)
    resolved = client._resolve_runtime_model_path()
    assert resolved is not None and resolved.name == "nested"

    text = client._messages_to_text(
        [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "   "},
        ]
    )
    assert "system: s" in text
    assert "assistant: a" in text


@pytest.mark.asyncio
async def test_service_monitor_gpu_parse_and_no_nvidia(monkeypatch: pytest.MonkeyPatch):
    monitor = ServiceHealthMonitor(
        registry=SimpleNamespace(
            get_all_services=lambda: [],
            get_critical_services=lambda: [],
        )
    )
    parsed = monitor._parse_nvidia_smi_output("10, 100\ninvalid\n20,200")
    assert parsed == [(10.0, 100.0), (20.0, 200.0)]

    monkeypatch.setattr(
        "venom_core.core.service_monitor.shutil.which", lambda _cmd: None
    )
    assert monitor.get_gpu_memory_usage() is None


@pytest.mark.asyncio
async def test_academy_conversion_selection_and_dataset_ids(tmp_path: Path):
    workspace = {
        "base_dir": tmp_path,
        "metadata_file": tmp_path / "files.json",
        "source_dir": tmp_path / "source",
        "converted_dir": tmp_path / "converted",
    }
    items = [
        {"category": "converted", "selected_for_training": True, "file_id": "ok-id"},
        {"category": "converted", "selected_for_training": True, "file_id": "../bad"},
        {"category": "source", "selected_for_training": True, "file_id": "src"},
    ]

    selected = academy_conversion.get_selected_converted_file_ids(
        workspace=workspace,
        user_conversion_metadata_lock_fn=_dummy_lock,
        load_user_conversion_metadata_fn=lambda _path: items,
        check_path_traversal_fn=lambda fid: ".." not in fid,
    )
    assert selected == ["ok-id"]

    explicit = academy_conversion.resolve_conversion_file_ids_for_dataset(
        requested_ids=["a", "b"],
        selected_ids_fn=lambda: ["x"],
    )
    fallback = academy_conversion.resolve_conversion_file_ids_for_dataset(
        requested_ids=None,
        selected_ids_fn=lambda: ["x"],
    )
    assert explicit == ["a", "b"]
    assert fallback == ["x"]


def test_model_registry_provider_generation_schema_edges():
    schema = model_registry_providers.create_default_generation_schema()
    assert schema["temperature"].default == 0.7
    assert schema["max_tokens"].max == 8192
