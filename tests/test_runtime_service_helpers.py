from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psutil

from venom_core.core import model_manager_storage as mstorage
from venom_core.services import runtime_health_checks as rhc
from venom_core.services import runtime_provider_ops as rpo
from venom_core.services import runtime_state_machine as rsm


def _enums() -> tuple[SimpleNamespace, SimpleNamespace]:
    class _Named:
        def __init__(self, name: str) -> None:
            self.name = name

    service_type = SimpleNamespace(
        HIVE="hive",
        NEXUS="nexus",
        BACKGROUND_TASKS="background",
        BACKEND="backend",
        UI="ui",
        ACADEMY=_Named("ACADEMY"),
        INTENT_EMBEDDING_ROUTER=_Named("INTENT_EMBEDDING_ROUTER"),
        LLM_OLLAMA="llm_ollama",
    )
    service_status = SimpleNamespace(
        RUNNING="running",
        STOPPED="stopped",
        ERROR="error",
    )
    return service_type, service_status


def test_runtime_state_machine_helpers_cover_all_branches() -> None:
    st, ss = _enums()
    info = SimpleNamespace(status=None, port=None)
    settings = SimpleNamespace(
        ENABLE_HIVE=True,
        ENABLE_NEXUS=True,
        NEXUS_PORT=7711,
        VENOM_PAUSE_BACKGROUND_TASKS=False,
        ENABLE_ACADEMY=True,
        ENABLE_INTENT_EMBEDDING_ROUTER=False,
    )

    rsm.update_config_managed_status(
        info=info,
        service_type=st.HIVE,
        settings=settings,
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.status == ss.RUNNING

    rsm.update_config_managed_status(
        info=info,
        service_type=st.NEXUS,
        settings=settings,
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.status == ss.RUNNING and info.port == 7711

    settings.VENOM_PAUSE_BACKGROUND_TASKS = True
    rsm.update_config_managed_status(
        info=info,
        service_type=st.BACKGROUND_TASKS,
        settings=settings,
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.status == ss.STOPPED

    rsm.update_config_managed_status(
        info=info,
        service_type=st.ACADEMY,
        settings=settings,
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.status == ss.RUNNING

    rsm.update_config_managed_status(
        info=info,
        service_type=st.INTENT_EMBEDDING_ROUTER,
        settings=settings,
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.status == ss.STOPPED

    assert (
        rsm.config_controlled_result(service_type=st.HIVE, service_type_enum=st)[
            "success"
        ]
        is False
    )
    assert (
        rsm.config_controlled_result(service_type="x", service_type_enum=st)["message"]
        == "Nieznany typ usługi"
    )

    warn_calls: list[str] = []
    logger = SimpleNamespace(
        warning=lambda msg, *_args, **_kwargs: warn_calls.append(msg)
    )
    settings.ENABLE_HIVE = False
    assert (
        rsm.check_service_dependencies(
            service_type=st.HIVE,
            get_service_status_fn=lambda _svc: SimpleNamespace(status=ss.RUNNING),
            settings=settings,
            service_type_enum=st,
            service_status_enum=ss,
            logger=logger,
        )
        == "Hive jest wyłączone w konfiguracji (ENABLE_HIVE=false)"
    )
    settings.ENABLE_HIVE = True
    settings.ENABLE_NEXUS = False
    assert "Nexus jest wyłączone" in rsm.check_service_dependencies(
        service_type=st.NEXUS,
        get_service_status_fn=lambda _svc: SimpleNamespace(status=ss.RUNNING),
        settings=settings,
        service_type_enum=st,
        service_status_enum=ss,
        logger=logger,
    )
    settings.ENABLE_NEXUS = True
    assert "Nexus wymaga działającego backendu" in rsm.check_service_dependencies(
        service_type=st.NEXUS,
        get_service_status_fn=lambda _svc: SimpleNamespace(status=ss.STOPPED),
        settings=settings,
        service_type_enum=st,
        service_status_enum=ss,
        logger=logger,
    )
    assert (
        "Background tasks wymagają działającego backendu"
        in rsm.check_service_dependencies(
            service_type=st.BACKGROUND_TASKS,
            get_service_status_fn=lambda _svc: SimpleNamespace(status=ss.STOPPED),
            settings=settings,
            service_type_enum=st,
            service_status_enum=ss,
            logger=logger,
        )
    )
    assert (
        rsm.check_service_dependencies(
            service_type=st.UI,
            get_service_status_fn=lambda _svc: SimpleNamespace(status=ss.STOPPED),
            settings=settings,
            service_type_enum=st,
            service_status_enum=ss,
            logger=logger,
        )
        is None
    )
    assert warn_calls


def test_runtime_health_checks_helpers_cover_paths(tmp_path, monkeypatch) -> None:
    st, ss = _enums()
    info = SimpleNamespace(
        pid=None,
        cpu_percent=None,
        memory_mb=None,
        uptime_seconds=None,
        status=None,
        port=None,
        error_message=None,
        runtime_version=None,
    )

    rhc.apply_process_metrics(
        info=info,
        pid=10,
        get_process_info_fn=lambda _pid: {
            "cpu_percent": 3.0,
            "memory_mb": 64.0,
            "uptime_seconds": 12.3,
        },
    )
    assert info.pid == 10 and info.uptime_seconds == 12

    rhc.apply_process_metrics(info=info, pid=11, get_process_info_fn=lambda _pid: None)
    pid_path = tmp_path / "x.pid"
    pid_path.write_text("42", encoding="utf-8")
    assert rhc.read_pid_file(pid_files={"svc": pid_path}, service_type="svc") == 42
    assert (
        rhc.read_pid_file(
            pid_files={"svc": tmp_path / "missing.pid"}, service_type="svc"
        )
        is None
    )

    rhc.update_pid_file_service_status(
        info=info,
        service_type=st.BACKEND,
        read_pid_file_fn=lambda _svc: None,
        get_process_info_fn=lambda _pid: {"cpu_percent": 1.0, "memory_mb": 2.0},
        apply_process_metrics_fn=lambda _info, _pid: None,
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.status == ss.STOPPED

    rhc.update_pid_file_service_status(
        info=info,
        service_type=st.BACKEND,
        read_pid_file_fn=lambda _svc: 99,
        get_process_info_fn=lambda _pid: None,
        apply_process_metrics_fn=lambda _info, _pid: None,
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.status == ss.STOPPED

    applied: list[int] = []
    rhc.update_pid_file_service_status(
        info=info,
        service_type=st.BACKEND,
        read_pid_file_fn=lambda _svc: 99,
        get_process_info_fn=lambda _pid: {"cpu_percent": 1.0, "memory_mb": 2.0},
        apply_process_metrics_fn=lambda _info, pid: applied.append(pid),
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.status == ss.RUNNING and info.port == 8000 and applied == [99]

    rhc.update_pid_file_service_status(
        info=info,
        service_type=st.UI,
        read_pid_file_fn=lambda _svc: 77,
        get_process_info_fn=lambda _pid: {"cpu_percent": 1.0, "memory_mb": 2.0},
        apply_process_metrics_fn=lambda _info, _pid: None,
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.port == 3000

    rhc.update_pid_file_service_status(
        info=info,
        service_type=st.UI,
        read_pid_file_fn=lambda _svc: (_ for _ in ()).throw(RuntimeError("pid-fail")),
        get_process_info_fn=lambda _pid: None,
        apply_process_metrics_fn=lambda _info, _pid: None,
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.status == ss.ERROR and "pid-fail" in str(info.error_message)

    assert rhc.check_port_listening(
        process_monitor=SimpleNamespace(check_port_listening=lambda p: p == 12), port=12
    )

    info.runtime_version = None
    rhc.update_llm_status(
        info=info,
        port=11434,
        process_match="ollama",
        service_type=st.LLM_OLLAMA,
        check_port_listening_fn=lambda _p: False,
        apply_process_metrics_fn=lambda _i, _pid: None,
        get_service_runtime_version_fn=lambda _svc: "v0",
        refresh_ollama_runtime_version_fn=lambda **_kw: "v1",
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert info.status == ss.STOPPED

    class _Proc:
        def __init__(self, pid: int, name: str, cmd: list[str]) -> None:
            self.info = {"pid": pid, "name": name, "cmdline": cmd}

    monkeypatch.setattr(
        rhc.psutil,
        "process_iter",
        lambda _attrs: iter(
            [
                _Proc(10, "none", []),
                _Proc(11, "ollama", ["serve"]),
            ]
        ),
    )
    got_pids: list[int] = []
    rhc.update_llm_status(
        info=info,
        port=11434,
        process_match="ollama",
        service_type=st.LLM_OLLAMA,
        check_port_listening_fn=lambda _p: True,
        apply_process_metrics_fn=lambda _i, pid: got_pids.append(pid),
        get_service_runtime_version_fn=lambda _svc: "v0",
        refresh_ollama_runtime_version_fn=lambda **_kw: "v2",
        service_type_enum=st,
        service_status_enum=ss,
    )
    assert (
        info.status == ss.RUNNING and got_pids == [11] and info.runtime_version == "v2"
    )

    class _FailProc:
        def __init__(self, exc: Exception) -> None:
            self._exc = exc

        @property
        def info(self):
            raise self._exc

    monkeypatch.setattr(
        rhc.psutil,
        "process_iter",
        lambda _attrs: iter(
            [_FailProc(psutil.NoSuchProcess(1)), _FailProc(psutil.AccessDenied(2))]
        ),
    )
    rhc.update_llm_status(
        info=info,
        port=11434,
        process_match="ollama",
        service_type=st.LLM_OLLAMA,
        check_port_listening_fn=lambda _p: True,
        apply_process_metrics_fn=lambda _i, _pid: None,
        get_service_runtime_version_fn=lambda _svc: "v0",
        refresh_ollama_runtime_version_fn=lambda **_kw: "v3",
        service_type_enum=st,
        service_status_enum=ss,
    )


def test_model_manager_storage_helpers_cover_safety_paths(
    tmp_path, monkeypatch
) -> None:
    assert mstorage.is_valid_model_name("phi3:latest")
    assert not mstorage.is_valid_model_name("../bad")

    original_exists = Path.exists
    monkeypatch.setattr(
        Path,
        "exists",
        lambda self: str(self) == "/usr/lib/wsl/drivers" or original_exists(self),
    )
    assert mstorage.resolve_models_mount() == Path("/usr/lib/wsl/drivers")

    monkeypatch.setattr(
        Path,
        "exists",
        lambda self: False
        if str(self) == "/usr/lib/wsl/drivers"
        else original_exists(self),
    )
    assert mstorage.resolve_models_mount() == Path("/")
    monkeypatch.setattr(Path, "exists", original_exists)

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    logger_calls: list[str] = []
    logger = SimpleNamespace(error=lambda msg, *_args: logger_calls.append(msg))

    assert (
        mstorage.delete_local_model_file(
            model_info={"path": str(tmp_path / "outside")},
            models_dir=models_dir,
            logger=logger,
        )
        is False
    )

    missing = models_dir / "missing.gguf"
    assert (
        mstorage.delete_local_model_file(
            model_info={"path": str(missing)},
            models_dir=models_dir.resolve(),
            logger=logger,
        )
        is False
    )

    model_file = models_dir / "ok.gguf"
    model_file.write_text("x", encoding="utf-8")
    assert (
        mstorage.delete_local_model_file(
            model_info={"path": str(model_file)},
            models_dir=models_dir.resolve(),
            logger=logger,
        )
        is True
    )
    model_dir = models_dir / "dir_model"
    model_dir.mkdir()
    (model_dir / "blob").write_text("x", encoding="utf-8")
    assert (
        mstorage.delete_local_model_file(
            model_info={"path": str(model_dir)},
            models_dir=models_dir.resolve(),
            logger=logger,
        )
        is True
    )
    assert logger_calls


class _Subprocess:
    DEVNULL = object()

    def __init__(self, *, run_code: int = 0, run_err: str = "") -> None:
        self.run_code = run_code
        self.run_err = run_err
        self.popen_fail = False
        self.run_fail = False

    def Popen(self, *_args, **_kwargs):  # noqa: N802
        if self.popen_fail:
            raise RuntimeError("popen-fail")
        return SimpleNamespace(pid=1)

    def run(self, *_args, **_kwargs):
        if self.run_fail:
            raise RuntimeError("run-fail")
        return SimpleNamespace(returncode=self.run_code, stderr=self.run_err)


def test_runtime_provider_ops_cover_success_and_failure_branches(tmp_path) -> None:
    process = _Subprocess()
    ok_status = lambda _svc: SimpleNamespace(status="running", pid=5)  # noqa: E731
    down_status = lambda _svc: SimpleNamespace(status="stopped", pid=None)  # noqa: E731

    assert rpo.start_backend(
        project_root=tmp_path,
        get_service_status_fn=ok_status,
        backend_service_type="backend",
        service_status_running="running",
        subprocess_module=process,
        time_module=SimpleNamespace(sleep=lambda _s: None),
    )["success"]
    assert not rpo.start_backend(
        project_root=tmp_path,
        get_service_status_fn=down_status,
        backend_service_type="backend",
        service_status_running="running",
        subprocess_module=process,
        time_module=SimpleNamespace(sleep=lambda _s: None),
    )["success"]
    process.popen_fail = True
    assert not rpo.start_backend(
        project_root=tmp_path,
        get_service_status_fn=ok_status,
        backend_service_type="backend",
        service_status_running="running",
        subprocess_module=process,
        time_module=SimpleNamespace(sleep=lambda _s: None),
    )["success"]

    process2 = _Subprocess(run_code=0)
    assert rpo.stop_backend(project_root=tmp_path, subprocess_module=process2)[
        "success"
    ]
    process2.run_code = 1
    process2.run_err = "bad"
    assert not rpo.stop_backend(project_root=tmp_path, subprocess_module=process2)[
        "success"
    ]
    process2.run_fail = True
    assert not rpo.stop_backend(project_root=tmp_path, subprocess_module=process2)[
        "success"
    ]

    assert rpo.start_ui(
        get_service_status_fn=ok_status,
        ui_service_type="ui",
        service_status_running="running",
    )["success"]
    assert not rpo.start_ui(
        get_service_status_fn=down_status,
        ui_service_type="ui",
        service_status_running="running",
    )["success"]
    assert rpo.stop_ui()["success"]
