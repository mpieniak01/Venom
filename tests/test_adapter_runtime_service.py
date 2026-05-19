"""Direct new-code coverage entrypoint for adapter_runtime_service.

This module intentionally re-exports academy adapter runtime service tests so
the changed-lines fallback resolver can pick the canonical direct test path:
tests/test_adapter_runtime_service.py.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.test_academy_adapter_runtime_service import *  # noqa: F401,F403
from venom_core.services.academy import adapter_runtime_service as ars


class _BadStr:
    def __str__(self) -> str:
        raise RuntimeError("boom")


def test_parse_positive_numeric_defaults_on_bad_str_and_invalid_values() -> None:
    assert ars._parse_positive_float(_BadStr(), default=0.25) == 0.25
    assert ars._parse_positive_int(_BadStr(), default=15360) == 15360


def test_resolve_limits_defaults_without_env_or_settings(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMY_ADAPTER_MERGE_MAX_RSS_MB", raising=False)
    monkeypatch.delenv("VENOM_ADAPTER_MERGE_MAX_RSS_MB", raising=False)
    monkeypatch.delenv("ACADEMY_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC", raising=False)
    monkeypatch.delenv("VENOM_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC", raising=False)
    settings = SimpleNamespace(
        ACADEMY_ADAPTER_MERGE_MAX_RSS_MB=None,
        ACADEMY_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC=None,
    )
    assert ars._resolve_merge_memory_limit_mb(settings_obj=settings) == 15360
    assert ars._resolve_memory_monitor_interval_sec(settings_obj=settings) == 0.25


def test_read_process_rss_mb_returns_zero_when_proc_unavailable() -> None:
    assert ars._read_process_rss_mb(pid=999999999) == 0.0


def test_terminate_process_with_grace_calls_kill_when_still_running(
    monkeypatch,
) -> None:
    class _Proc:
        def __init__(self) -> None:
            self.signaled = False
            self.killed = False

        def send_signal(self, _sig) -> None:
            self.signaled = True

        def poll(self):
            return None

        def kill(self) -> None:
            self.killed = True

    proc = _Proc()
    with patch.object(ars.time, "monotonic", side_effect=[0.0, 10.0]):
        ars._terminate_process_with_grace(
            process=proc, stop_event=ars.threading.Event()
        )
    assert proc.signaled is True
    assert proc.killed is True


def test_monitor_subprocess_memory_marks_exceeded_and_terminates(monkeypatch) -> None:
    class _Proc:
        pid = 123

        def poll(self):
            return None

    state = {"peak_rss_mb": 0.0, "exceeded": False}
    stop = ars.threading.Event()
    monkeypatch.setattr(ars, "_read_process_rss_mb", lambda pid: 200.0)
    terminated = {"called": False}

    def _terminate(*, process, stop_event):
        terminated["called"] = True
        stop_event.set()

    monkeypatch.setattr(ars, "_terminate_process_with_grace", _terminate)
    ars._monitor_subprocess_memory(
        process=_Proc(),
        state=state,
        stop_event=stop,
        max_rss_mb=100,
        monitor_interval_sec=0.01,
    )
    assert state["exceeded"] is True
    assert terminated["called"] is True


def test_build_onnx_export_cmd_covers_execution_provider_and_precision(
    tmp_path: Path,
) -> None:
    cmd = ars._build_onnx_export_cmd(
        builder_script=tmp_path / "builder.py",
        export_input=tmp_path / "input",
        execution_provider="cpu",
        precision="int4",
        tmp_dir=tmp_path / "out",
    )
    assert cmd[0] == ars.sys.executable
    assert "-e" in cmd and "cpu" in cmd
    assert "-p" in cmd and "int4" in cmd


def test_resolve_onnx_builder_script_error_message_includes_default_paths(monkeypatch):
    monkeypatch.delenv("ONNX_GENAI_BUILDER_SCRIPT", raising=False)
    with (
        patch.object(ars, "_resolve_first_existing_file", return_value=None),
        patch.object(ars, "_resolve_installed_onnx_builder", return_value=None),
        patch.object(ars, "_resolve_repo_root", return_value=Path("/tmp/repo")),
    ):
        with pytest.raises(FileNotFoundError, match="default paths"):
            ars._resolve_onnx_builder_script(
                settings_obj=SimpleNamespace(ONNX_BUILDER_SCRIPT="")
            )
