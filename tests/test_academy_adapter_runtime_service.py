from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from venom_core.services.academy import adapter_runtime_service as ars


def _make_adapter_dir(tmp_path: Path, *, metadata: dict | None = None) -> Path:
    adapter_dir = tmp_path / "adapter_case"
    (adapter_dir / "adapter").mkdir(parents=True, exist_ok=True)
    if metadata is not None:
        (adapter_dir / "metadata.json").write_text(
            json.dumps(metadata),
            encoding="utf-8",
        )
    return adapter_dir


def test_resolve_ollama_create_from_model_prefers_runtime_training_base(tmp_path: Path):
    runtime_base = tmp_path / "runtime-base"
    runtime_base.mkdir(parents=True)
    (runtime_base / "config.json").write_text("{}", encoding="utf-8")
    (runtime_base / "model.safetensors").write_text("weights", encoding="utf-8")
    adapter_dir = _make_adapter_dir(
        tmp_path,
        metadata={"parameters": {"training_base_model": str(runtime_base)}},
    )

    resolved, use_experimental = ars._resolve_ollama_create_from_model(
        adapter_dir=adapter_dir,
        requested_model="gemma3:latest",
    )

    assert resolved == str(runtime_base.resolve())
    assert use_experimental is True


def test_resolve_ollama_create_from_model_falls_back_to_requested_model(tmp_path: Path):
    adapter_dir = _make_adapter_dir(
        tmp_path,
        metadata={"parameters": {"training_base_model": "/tmp/not-runtime"}},
    )

    resolved, use_experimental = ars._resolve_ollama_create_from_model(
        adapter_dir=adapter_dir,
        requested_model="gemma3:latest",
        is_runtime_model_dir_fn=lambda _path: False,
    )

    assert resolved == "gemma3:4b"
    assert use_experimental is False


def test_resolve_ollama_create_from_model_maps_hf_repo_to_ollama_alias(
    tmp_path: Path,
):
    adapter_dir = _make_adapter_dir(
        tmp_path,
        metadata={"parameters": {"training_base_model": "/tmp/not-runtime"}},
    )

    resolved, use_experimental = ars._resolve_ollama_create_from_model(
        adapter_dir=adapter_dir,
        requested_model="unsloth/gemma-2-2b-it",
        is_runtime_model_dir_fn=lambda _path: False,
    )

    assert resolved == "gemma2:2b"
    assert use_experimental is False


def test_resolve_hf_cache_snapshot_for_repo_id_uses_latest_snapshot_with_config(
    tmp_path: Path,
):
    repo_root = tmp_path
    snapshots = (
        repo_root
        / "models"
        / "cache"
        / "huggingface"
        / "hub"
        / "models--acme--model"
        / "snapshots"
    )
    older = snapshots / "older"
    newer = snapshots / "newer"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "config.json").write_text("{}", encoding="utf-8")
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    resolved = ars._resolve_hf_cache_snapshot_for_repo_id(
        repo_id="acme/model",
        settings_obj=SimpleNamespace(REPO_ROOT=str(repo_root)),
    )

    assert resolved == str(older.resolve())


def test_resolve_hf_cache_snapshot_for_repo_id_returns_empty_for_invalid_repo_id(
    tmp_path: Path,
):
    resolved = ars._resolve_hf_cache_snapshot_for_repo_id(
        repo_id="gemma3",
        settings_obj=SimpleNamespace(REPO_ROOT=str(tmp_path)),
    )
    assert resolved == ""


def test_resolve_adapter_training_base_for_ollama_gguf_uses_local_path(tmp_path: Path):
    local_base = tmp_path / "local-base"
    local_base.mkdir(parents=True)
    (local_base / "config.json").write_text("{}", encoding="utf-8")
    adapter_dir = _make_adapter_dir(
        tmp_path,
        metadata={"parameters": {"training_base_model": str(local_base)}},
    )

    resolved = ars._resolve_adapter_training_base_for_ollama_gguf(
        adapter_dir=adapter_dir,
        requested_from_model="gemma3:latest",
    )

    assert resolved == str(local_base.resolve())


def test_resolve_adapter_training_base_for_ollama_gguf_uses_hf_snapshot_fallback(
    tmp_path: Path,
):
    adapter_dir = _make_adapter_dir(
        tmp_path,
        metadata={"base_model": "acme/model"},
    )
    with patch.object(
        ars,
        "_resolve_hf_cache_snapshot_for_repo_id",
        return_value=str((tmp_path / "snapshot").resolve()),
    ):
        resolved = ars._resolve_adapter_training_base_for_ollama_gguf(
            adapter_dir=adapter_dir,
            requested_from_model="gemma3:latest",
        )

    assert resolved == str((tmp_path / "snapshot").resolve())


def test_resolve_adapter_training_base_for_ollama_gguf_raises_when_unresolvable(
    tmp_path: Path,
):
    adapter_dir = _make_adapter_dir(
        tmp_path,
        metadata={"base_model": "unknown/repo"},
    )
    with patch.object(ars, "_resolve_hf_cache_snapshot_for_repo_id", return_value=""):
        with pytest.raises(
            RuntimeError, match="Cannot resolve local HF base model snapshot"
        ):
            ars._resolve_adapter_training_base_for_ollama_gguf(
                adapter_dir=adapter_dir,
                requested_from_model="gemma3:latest",
            )


def test_resolve_llama_cpp_convert_script_prefers_explicit_script_env(
    tmp_path: Path, monkeypatch
):
    convert_script = tmp_path / "convert_lora_to_gguf.py"
    convert_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setenv("VENOM_LLAMA_CPP_CONVERT_SCRIPT", str(convert_script))

    resolved = ars._resolve_llama_cpp_convert_script(
        settings_obj=SimpleNamespace(ACADEMY_LLAMA_CPP_DIR="", REPO_ROOT=str(tmp_path))
    )
    assert resolved == convert_script.resolve()


def test_resolve_llama_cpp_convert_script_uses_settings_dir(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("VENOM_LLAMA_CPP_CONVERT_SCRIPT", raising=False)
    monkeypatch.delenv("VENOM_LLAMA_CPP_DIR", raising=False)
    llama_dir = tmp_path / "llama.cpp"
    llama_dir.mkdir(parents=True)
    convert_script = llama_dir / "convert_lora_to_gguf.py"
    convert_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    resolved = ars._resolve_llama_cpp_convert_script(
        settings_obj=SimpleNamespace(
            ACADEMY_LLAMA_CPP_DIR=str(llama_dir), REPO_ROOT=str(tmp_path)
        )
    )
    assert resolved == convert_script.resolve()


def test_resolve_llama_cpp_convert_script_raises_when_missing(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("VENOM_LLAMA_CPP_CONVERT_SCRIPT", raising=False)
    monkeypatch.delenv("VENOM_LLAMA_CPP_DIR", raising=False)
    with pytest.raises(FileNotFoundError, match="convert_lora_to_gguf.py not found"):
        ars._resolve_llama_cpp_convert_script(
            settings_obj=SimpleNamespace(
                ACADEMY_LLAMA_CPP_DIR="", REPO_ROOT=str(tmp_path)
            )
        )


def test_resolve_existing_ollama_adapter_gguf_prefers_named_candidate(tmp_path: Path):
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})
    gguf_path = adapter_dir / "adapter" / "Adapter-F16-LoRA.gguf"
    gguf_path.write_text("gguf", encoding="utf-8")

    resolved = ars._resolve_existing_ollama_adapter_gguf(adapter_dir=adapter_dir)
    assert resolved == gguf_path


def test_resolve_existing_ollama_adapter_gguf_falls_back_to_any_gguf(tmp_path: Path):
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})
    gguf_path = adapter_dir / "adapter" / "custom.gguf"
    gguf_path.write_text("gguf", encoding="utf-8")

    resolved = ars._resolve_existing_ollama_adapter_gguf(adapter_dir=adapter_dir)
    assert resolved == gguf_path


def test_ensure_ollama_adapter_gguf_returns_existing_file(tmp_path: Path):
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})
    gguf_path = adapter_dir / "adapter" / "Adapter-F16-LoRA.gguf"
    gguf_path.write_text("gguf", encoding="utf-8")

    resolved = ars._ensure_ollama_adapter_gguf(
        adapter_dir=adapter_dir,
        from_model="gemma3:latest",
    )
    assert resolved == gguf_path.resolve()


def test_ensure_ollama_adapter_gguf_raises_when_adapter_dir_missing(tmp_path: Path):
    adapter_dir = tmp_path / "missing-adapter-dir"
    adapter_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="Adapter path not found"):
        ars._ensure_ollama_adapter_gguf(
            adapter_dir=adapter_dir,
            from_model="gemma3:latest",
        )


def test_ensure_ollama_adapter_gguf_raises_when_conversion_fails(tmp_path: Path):
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})
    with (
        patch.object(
            ars,
            "_resolve_adapter_training_base_for_ollama_gguf",
            return_value="/tmp/base",
        ),
        patch.object(
            ars,
            "_resolve_llama_cpp_convert_script",
            return_value=tmp_path / "convert_lora_to_gguf.py",
        ),
        patch.object(
            ars.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=1, stdout="", stderr="conversion failed"
            ),
        ),
    ):
        with pytest.raises(RuntimeError, match="conversion failed"):
            ars._ensure_ollama_adapter_gguf(
                adapter_dir=adapter_dir,
                from_model="gemma3:latest",
            )


def test_ensure_ollama_adapter_gguf_raises_when_output_not_found_after_conversion(
    tmp_path: Path,
):
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})
    with (
        patch.object(
            ars,
            "_resolve_adapter_training_base_for_ollama_gguf",
            return_value="/tmp/base",
        ),
        patch.object(
            ars,
            "_resolve_llama_cpp_convert_script",
            return_value=tmp_path / "convert_lora_to_gguf.py",
        ),
        patch.object(
            ars,
            "_resolve_existing_ollama_adapter_gguf",
            side_effect=[None, None],
        ),
        patch.object(
            ars.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        ),
    ):
        with pytest.raises(RuntimeError, match="no \\*\\.gguf file found"):
            ars._ensure_ollama_adapter_gguf(
                adapter_dir=adapter_dir,
                from_model="gemma3:latest",
            )


def test_deploy_adapter_to_chat_runtime_ollama_uses_resolved_from_model_and_experimental(
    tmp_path: Path,
):
    runtime_base = tmp_path / "runtime-base"
    runtime_base.mkdir(parents=True)
    (runtime_base / "config.json").write_text("{}", encoding="utf-8")
    (runtime_base / "weights.safetensors").write_text("weights", encoding="utf-8")

    models_dir = tmp_path / "models"
    adapter_id = "adapter-1"
    adapter_dir = models_dir / adapter_id
    (adapter_dir / "adapter").mkdir(parents=True, exist_ok=True)
    (adapter_dir / "metadata.json").write_text(
        json.dumps({"parameters": {"training_base_model": str(runtime_base)}}),
        encoding="utf-8",
    )

    settings_obj = SimpleNamespace(ACADEMY_MODELS_DIR=str(models_dir))
    mgr = MagicMock()
    mgr.create_ollama_modelfile.return_value = "venom-adapter-adapter-1"
    config_manager_obj = MagicMock()
    get_active_llm_runtime_fn = MagicMock(
        return_value=SimpleNamespace(provider="ollama", model_name="codestral:latest")
    )

    with patch.object(
        ars,
        "_ensure_ollama_adapter_gguf",
        return_value=adapter_dir / "adapter" / "Adapter-F16-LoRA.gguf",
    ):
        payload = ars._deploy_adapter_to_chat_runtime(
            mgr=mgr,
            adapter_id=adapter_id,
            runtime_id="ollama",
            model_id="gemma3:latest",
            settings_obj=settings_obj,
            deploy_deps={
                "require_trusted_adapter_base_model_fn": lambda **_kw: "gemma-3-4b-it",
                "canonical_runtime_model_id_fn": lambda value: (
                    "gemma-3-4b-it"
                    if value.strip().lower() in {"gemma3:latest", "gemma3:4b"}
                    else value.strip().lower()
                ),
                "config_manager_obj": config_manager_obj,
                "compute_llm_config_hash_fn": lambda *_args: "hash-123",
                "runtime_endpoint_for_hash_fn": lambda *_args,
                **_kwargs: "http://localhost:11434/v1",
                "is_runtime_model_dir_fn": lambda path: Path(path).resolve()
                == runtime_base.resolve(),
                "get_active_llm_runtime_fn": get_active_llm_runtime_fn,
            },
        )

    assert payload["deployed"] is True
    assert payload["runtime_id"] == "ollama"
    mgr.create_ollama_modelfile.assert_called_once_with(
        version_id=adapter_id,
        output_name="venom-adapter-adapter-1",
        from_model=str(runtime_base.resolve()),
        use_experimental=True,
    )
    config_manager_obj.update_config.assert_called_once()


def test_deploy_adapter_to_chat_runtime_ollama_raises_runtime_unavailable_when_daemon_offline(
    tmp_path: Path,
):
    models_dir = tmp_path / "models"
    adapter_id = "adapter-offline"
    adapter_dir = models_dir / adapter_id
    (adapter_dir / "adapter").mkdir(parents=True, exist_ok=True)
    (adapter_dir / "metadata.json").write_text(
        json.dumps({"parameters": {"training_base_model": "gemma3:4b"}}),
        encoding="utf-8",
    )

    settings_obj = SimpleNamespace(ACADEMY_MODELS_DIR=str(models_dir))
    mgr = MagicMock()
    mgr.create_ollama_modelfile.return_value = None

    with (
        patch.object(
            ars,
            "_ensure_ollama_adapter_gguf",
            return_value=adapter_dir / "adapter" / "Adapter-F16-LoRA.gguf",
        ),
        patch.object(
            ars.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="could not connect to ollama server",
            ),
        ),
    ):
        with pytest.raises(RuntimeError, match="ADAPTER_RUNTIME_SERVICE_UNAVAILABLE"):
            ars._deploy_adapter_to_chat_runtime(
                mgr=mgr,
                adapter_id=adapter_id,
                runtime_id="ollama",
                model_id="gemma3:4b",
                settings_obj=settings_obj,
                deploy_deps={
                    "require_trusted_adapter_base_model_fn": lambda **_kw: "gemma-3-4b-it",
                    "canonical_runtime_model_id_fn": lambda value: (
                        "gemma-3-4b-it"
                        if value.strip().lower() in {"gemma3:latest", "gemma3:4b"}
                        else value.strip().lower()
                    ),
                    "config_manager_obj": MagicMock(),
                    "compute_llm_config_hash_fn": lambda *_args: "hash-offline",
                    "runtime_endpoint_for_hash_fn": lambda *_args,
                    **_kwargs: "http://localhost:11434/v1",
                    "is_runtime_model_dir_fn": lambda _path: False,
                    "get_active_llm_runtime_fn": lambda: SimpleNamespace(
                        provider="ollama",
                        model_name="gemma3:4b",
                    ),
                },
            )


def test_probe_ollama_runtime_unavailable_reason_returns_none_when_probe_succeeds() -> (
    None
):
    with patch.object(
        ars.subprocess,
        "run",
        return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    ):
        assert ars._probe_ollama_runtime_unavailable_reason() is None


def test_probe_ollama_runtime_unavailable_reason_handles_missing_cli() -> None:
    with patch.object(ars.subprocess, "run", side_effect=FileNotFoundError()):
        message = ars._probe_ollama_runtime_unavailable_reason()
    assert message is not None
    assert "Ollama CLI is not available" in message


def test_probe_ollama_runtime_unavailable_reason_handles_timeout() -> None:
    with patch.object(
        ars.subprocess,
        "run",
        side_effect=ars.subprocess.TimeoutExpired(cmd=["ollama", "list"], timeout=10),
    ):
        message = ars._probe_ollama_runtime_unavailable_reason()
    assert message is not None
    assert "probe timed out" in message


def test_probe_ollama_runtime_unavailable_reason_handles_generic_error() -> None:
    with patch.object(ars.subprocess, "run", side_effect=RuntimeError("boom")):
        message = ars._probe_ollama_runtime_unavailable_reason()
    assert message is not None
    assert "probe failed: boom" in message


def test_deploy_adapter_to_chat_runtime_ollama_raises_deploy_failed_when_probe_ok(
    tmp_path: Path,
):
    models_dir = tmp_path / "models"
    adapter_id = "adapter-probe-ok"
    adapter_dir = models_dir / adapter_id
    (adapter_dir / "adapter").mkdir(parents=True, exist_ok=True)
    (adapter_dir / "metadata.json").write_text(
        json.dumps({"parameters": {"training_base_model": "gemma3:4b"}}),
        encoding="utf-8",
    )

    settings_obj = SimpleNamespace(ACADEMY_MODELS_DIR=str(models_dir))
    mgr = MagicMock()
    mgr.create_ollama_modelfile.return_value = None

    with (
        patch.object(
            ars,
            "_ensure_ollama_adapter_gguf",
            return_value=adapter_dir / "adapter" / "Adapter-F16-LoRA.gguf",
        ),
        patch.object(
            ars, "_probe_ollama_runtime_unavailable_reason", return_value=None
        ),
    ):
        with pytest.raises(RuntimeError, match="ADAPTER_RUNTIME_DEPLOY_FAILED"):
            ars._deploy_adapter_to_chat_runtime(
                mgr=mgr,
                adapter_id=adapter_id,
                runtime_id="ollama",
                model_id="gemma3:4b",
                settings_obj=settings_obj,
                deploy_deps={
                    "require_trusted_adapter_base_model_fn": lambda **_kw: "gemma-3-4b-it",
                    "canonical_runtime_model_id_fn": lambda value: (
                        "gemma-3-4b-it"
                        if value.strip().lower() in {"gemma3:latest", "gemma3:4b"}
                        else value.strip().lower()
                    ),
                    "config_manager_obj": MagicMock(),
                    "compute_llm_config_hash_fn": lambda *_args: "hash-probe-ok",
                    "runtime_endpoint_for_hash_fn": lambda *_args,
                    **_kwargs: "http://localhost:11434/v1",
                    "is_runtime_model_dir_fn": lambda _path: False,
                    "get_active_llm_runtime_fn": lambda: SimpleNamespace(
                        provider="ollama",
                        model_name="gemma3:4b",
                    ),
                },
            )


def test_run_subprocess_with_memory_guard_writes_monitor_file(tmp_path: Path):
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})
    result = ars._run_subprocess_with_memory_guard(
        cmd=["/bin/bash", "-lc", "python3 - <<'PY'\nprint('ok')\nPY"],
        stage="unit_test",
        adapter_dir=adapter_dir,
        timeout_sec=10,
        max_rss_mb=1024,
        monitor_interval_sec=0.1,
    )
    assert result.returncode == 0
    monitor_file = adapter_dir / "resource_monitor.jsonl"
    assert monitor_file.exists()
    assert "unit_test" in monitor_file.read_text(encoding="utf-8")


def test_run_subprocess_with_memory_guard_raises_on_limit(tmp_path: Path):
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})
    with patch.object(ars, "_read_process_rss_mb", return_value=128.0):
        with pytest.raises(RuntimeError, match="exceeded memory guard"):
            ars._run_subprocess_with_memory_guard(
                cmd=[
                    "/bin/bash",
                    "-lc",
                    "python3 - <<'PY'\nimport time\ntime.sleep(2)\nprint('done')\nPY",
                ],
                stage="unit_test_limit",
                adapter_dir=adapter_dir,
                timeout_sec=15,
                max_rss_mb=32,
                monitor_interval_sec=0.1,
            )


def test_resolve_merge_memory_limit_mb_prefers_academy_env(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMY_ADAPTER_MERGE_MAX_RSS_MB", "12345")
    monkeypatch.setenv("VENOM_ADAPTER_MERGE_MAX_RSS_MB", "99999")

    value = ars._resolve_merge_memory_limit_mb(
        settings_obj=SimpleNamespace(ACADEMY_ADAPTER_MERGE_MAX_RSS_MB=7777)
    )

    assert value == 12345


def test_resolve_memory_monitor_interval_prefers_academy_env(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMY_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC", "0.33")
    monkeypatch.setenv("VENOM_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC", "0.75")

    value = ars._resolve_memory_monitor_interval_sec(
        settings_obj=SimpleNamespace(ACADEMY_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC=0.5)
    )

    assert value == pytest.approx(0.33)


def test_format_adapter_merge_error_maps_missing_dependency() -> None:
    err = ars._format_adapter_merge_error(
        stderr="ModuleNotFoundError: No module named 'torch'",
        stdout="",
    )
    assert "Missing Python dependency 'torch'" in err
    assert "Install 'torch'" in err


def test_parse_helpers_return_defaults_for_invalid_values() -> None:
    assert ars._parse_positive_float("not-a-number", default=0.25) == pytest.approx(
        0.25
    )
    assert ars._parse_positive_int("not-a-number", default=15360) == 15360


def test_resolve_limits_fall_back_to_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMY_ADAPTER_MERGE_MAX_RSS_MB", raising=False)
    monkeypatch.delenv("VENOM_ADAPTER_MERGE_MAX_RSS_MB", raising=False)
    monkeypatch.delenv("ACADEMY_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC", raising=False)
    monkeypatch.delenv("VENOM_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC", raising=False)

    settings = SimpleNamespace(
        ACADEMY_ADAPTER_MERGE_MAX_RSS_MB=0,
        ACADEMY_ADAPTER_MEMORY_MONITOR_INTERVAL_SEC=0,
    )
    assert ars._resolve_merge_memory_limit_mb(settings_obj=settings) == 15360
    assert ars._resolve_memory_monitor_interval_sec(
        settings_obj=settings
    ) == pytest.approx(0.25)


def test_read_process_rss_mb_returns_zero_for_missing_pid() -> None:
    assert ars._read_process_rss_mb(pid=999_999_999) == pytest.approx(0.0)


def test_format_adapter_merge_error_passthrough_and_unknown_dependency() -> None:
    assert (
        ars._format_adapter_merge_error(stderr="regular stderr", stdout="")
        == "regular stderr"
    )
    unknown = ars._format_adapter_merge_error(
        stderr="ModuleNotFoundError: No module named 'custom_dep'",
        stdout="",
    )
    assert unknown == "ModuleNotFoundError: No module named 'custom_dep'"


def test_resolve_local_training_base_model_for_merge_invalid_cases(
    tmp_path: Path,
) -> None:
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})

    with patch.object(
        ars,
        "_load_adapter_metadata",
        return_value={"parameters": {}},
    ):
        assert (
            ars._resolve_local_training_base_model_for_merge(adapter_dir=adapter_dir)
            == ""
        )

    bad_local = tmp_path / "bad-local"
    bad_local.mkdir(parents=True, exist_ok=True)
    with patch.object(
        ars,
        "_load_adapter_metadata",
        return_value={"parameters": {"training_base_model": str(bad_local)}},
    ):
        assert (
            ars._resolve_local_training_base_model_for_merge(adapter_dir=adapter_dir)
            == ""
        )


def test_resolve_local_training_base_model_for_merge_uses_hf_snapshot_fallback(
    tmp_path: Path,
) -> None:
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})
    snapshot = tmp_path / "snapshot-ok"
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")

    with (
        patch.object(
            ars,
            "_load_adapter_metadata",
            return_value={
                "parameters": {"training_base_model": "unsloth/gemma-2-2b-it"}
            },
        ),
        patch.object(
            ars,
            "_resolve_hf_cache_snapshot_for_repo_id",
            return_value=str(snapshot.resolve()),
        ),
    ):
        assert ars._resolve_local_training_base_model_for_merge(
            adapter_dir=adapter_dir
        ) == str(snapshot.resolve())


def test_build_hf_cache_env_sets_local_cache_paths(tmp_path: Path) -> None:
    settings = SimpleNamespace(REPO_ROOT=str(tmp_path))
    env = ars._build_hf_cache_env(base_env={}, settings_obj=settings)
    assert env["HF_HOME"] == str(
        (tmp_path / "models" / "cache" / "huggingface").resolve()
    )
    assert env["HUGGINGFACE_HUB_CACHE"] == str(
        (tmp_path / "models" / "cache" / "huggingface" / "hub").resolve()
    )
    assert env["TRANSFORMERS_CACHE"] == str(
        (tmp_path / "models" / "cache" / "huggingface" / "hub").resolve()
    )


def test_resolve_onnx_deploy_base_model_prefers_cached_snapshot(tmp_path: Path) -> None:
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})
    snapshot = tmp_path / "hf-snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    with (
        patch.object(
            ars,
            "_require_trusted_adapter_base_model",
            return_value="unsloth/gemma-2-2b-it",
        ),
        patch.object(
            ars,
            "_resolve_local_training_base_model_for_merge",
            return_value="",
        ),
        patch.object(
            ars,
            "_resolve_hf_cache_snapshot_for_repo_id",
            return_value=str(snapshot.resolve()),
        ),
    ):
        resolved = ars._resolve_onnx_deploy_base_model(adapter_dir=adapter_dir)
    assert resolved == str(snapshot.resolve())


def test_resolve_onnx_deploy_base_model_raises_for_missing_local_repo_id(
    tmp_path: Path,
) -> None:
    adapter_dir = _make_adapter_dir(tmp_path, metadata={})
    with (
        patch.object(
            ars,
            "_require_trusted_adapter_base_model",
            return_value="unsloth/gemma-2-2b-it",
        ),
        patch.object(
            ars,
            "_resolve_local_training_base_model_for_merge",
            return_value="",
        ),
        patch.object(
            ars,
            "_resolve_hf_cache_snapshot_for_repo_id",
            return_value="",
        ),
    ):
        with pytest.raises(
            ValueError, match="ADAPTER_BASE_MODEL_NOT_AVAILABLE_LOCALLY"
        ):
            ars._resolve_onnx_deploy_base_model(adapter_dir=adapter_dir)


def test_resolve_onnx_builder_script_uses_installed_module_path(tmp_path: Path) -> None:
    installed_file = tmp_path / "installed_builder.py"
    installed_file.write_text("# installed builder", encoding="utf-8")

    settings = SimpleNamespace(ONNX_BUILDER_SCRIPT="", REPO_ROOT=str(tmp_path))
    with (
        patch.dict("os.environ", {"ONNX_GENAI_BUILDER_SCRIPT": ""}),
        patch.object(ars, "_resolve_repo_root", return_value=tmp_path),
        patch.object(
            ars.importlib,
            "import_module",
            return_value=SimpleNamespace(__file__=str(installed_file)),
        ),
    ):
        resolved = ars._resolve_onnx_builder_script(settings_obj=settings)

    assert resolved == installed_file.resolve()


@pytest.mark.parametrize(
    "config_payload",
    [
        None,
        "{bad-json",
        json.dumps([]),
        json.dumps({"model_type": "gemma3", "text_config": []}),
    ],
)
def test_prepare_gemma3_text_export_input_dir_invalid_input_returns_none(
    tmp_path: Path,
    config_payload: str | None,
) -> None:
    adapter_dir = tmp_path / "adapter"
    merged_dir = tmp_path / "merged"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    merged_dir.mkdir(parents=True, exist_ok=True)
    config_path = merged_dir / "config.json"
    if config_payload is not None:
        config_path.write_text(config_payload, encoding="utf-8")

    assert (
        ars._prepare_gemma3_text_export_input_dir(
            merged_dir=merged_dir,
        )
        is None
    )


def test_prepare_gemma3_text_export_input_dir_falls_back_to_copy(
    tmp_path: Path,
) -> None:
    adapter_dir = tmp_path / "adapter"
    merged_dir = tmp_path / "merged"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    merged_dir.mkdir(parents=True, exist_ok=True)
    (merged_dir / "config.json").write_text(
        json.dumps(
            {
                "model_type": "gemma3",
                "text_config": {"hidden_size": 2560, "vocab_size": 262208},
            }
        ),
        encoding="utf-8",
    )
    (merged_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    subdir = merged_dir / "assets"
    subdir.mkdir(parents=True, exist_ok=True)
    (subdir / "vocab.txt").write_text("vocab", encoding="utf-8")

    with patch.object(Path, "symlink_to", side_effect=OSError("symlink disabled")):
        out_dir = ars._prepare_gemma3_text_export_input_dir(
            merged_dir=merged_dir,
        )

    assert out_dir is not None
    assert (out_dir / "tokenizer.json").exists()
    assert (out_dir / "assets" / "vocab.txt").exists()


def test_prepare_gemma3_text_export_input_dir_cleans_temp_on_copy_failure(
    tmp_path: Path,
) -> None:
    adapter_dir = tmp_path / "adapter"
    merged_dir = tmp_path / "merged"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    merged_dir.mkdir(parents=True, exist_ok=True)
    (merged_dir / "config.json").write_text(
        json.dumps(
            {
                "model_type": "gemma3",
                "text_config": {"hidden_size": 2560, "vocab_size": 262208},
            }
        ),
        encoding="utf-8",
    )
    (merged_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

    with (
        patch.object(Path, "symlink_to", side_effect=OSError("symlink disabled")),
        patch.object(ars.shutil, "copy2", side_effect=RuntimeError("copy failed")),
    ):
        with pytest.raises(RuntimeError, match="copy failed"):
            ars._prepare_gemma3_text_export_input_dir(
                merged_dir=merged_dir,
            )
    assert not list(adapter_dir.glob("runtime_onnx_export_input_tmp_*"))


def test_parse_helpers_return_defaults_when_str_raises() -> None:
    class _BadValue:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    assert ars._parse_positive_float(_BadValue(), default=0.75) == pytest.approx(0.75)
    assert ars._parse_positive_int(_BadValue(), default=42) == 42


def test_deploy_adapter_to_vllm_runtime_success_updates_previous_model(
    tmp_path: Path,
) -> None:
    models_dir = tmp_path / "models"
    adapter_id = "adapter-vllm"
    adapter_dir = models_dir / adapter_id
    (adapter_dir / "adapter").mkdir(parents=True, exist_ok=True)
    runtime_model_dir = tmp_path / "runtime-model"
    runtime_model_dir.mkdir(parents=True, exist_ok=True)
    (runtime_model_dir / "chat_template.jinja").write_text(
        "{{ prompt }}", encoding="utf-8"
    )

    settings = SimpleNamespace(ACADEMY_MODELS_DIR=str(models_dir))
    config_manager_obj = MagicMock()
    restart_runtime = MagicMock()

    with (
        patch.object(ars, "_require_trusted_adapter_base_model", return_value="gemma3"),
        patch.object(
            ars, "_resolve_local_training_base_model_for_merge", return_value=""
        ),
    ):
        payload = ars._deploy_adapter_to_vllm_runtime(
            adapter_id=adapter_id,
            settings_obj=settings,
            config_manager_obj=config_manager_obj,
            compute_llm_config_hash_fn=lambda *_args: "hash-vllm",
            runtime_endpoint_for_hash_fn=lambda *_args,
            **_kwargs: "http://localhost:8001/v1",
            build_vllm_runtime_model_from_adapter_fn=lambda **_kwargs: runtime_model_dir,
            is_runtime_model_dir_fn=lambda _path: True,
            restart_vllm_runtime_fn=restart_runtime,
            get_active_llm_runtime_fn=lambda: SimpleNamespace(
                provider="vllm",
                model_name="old-model",
            ),
        )

    assert payload["deployed"] is True
    assert payload["runtime_id"] == "vllm"
    assert payload["runtime_model_path"] == str(runtime_model_dir)

    updates = config_manager_obj.update_config.call_args.args[0]
    previous_key = ars.previous_model_key_for_server("vllm")
    assert updates[previous_key] == "old-model"
    assert updates["LLM_CONFIG_HASH"] == "hash-vllm"
    restart_runtime.assert_called_once()


def test_deploy_adapter_to_vllm_runtime_raises_for_non_runtime_model_dir(
    tmp_path: Path,
) -> None:
    models_dir = tmp_path / "models"
    adapter_id = "adapter-vllm-invalid"
    adapter_dir = models_dir / adapter_id
    (adapter_dir / "adapter").mkdir(parents=True, exist_ok=True)
    runtime_model_dir = tmp_path / "runtime-invalid"
    runtime_model_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch.object(ars, "_require_trusted_adapter_base_model", return_value="gemma3"),
        patch.object(
            ars, "_resolve_local_training_base_model_for_merge", return_value=""
        ),
    ):
        with pytest.raises(RuntimeError, match="Failed to prepare runtime-usable vLLM"):
            ars._deploy_adapter_to_vllm_runtime(
                adapter_id=adapter_id,
                settings_obj=SimpleNamespace(ACADEMY_MODELS_DIR=str(models_dir)),
                build_vllm_runtime_model_from_adapter_fn=lambda **_kwargs: runtime_model_dir,
                is_runtime_model_dir_fn=lambda _path: False,
                restart_vllm_runtime_fn=lambda **_kwargs: None,
                get_active_llm_runtime_fn=lambda: SimpleNamespace(
                    provider="vllm",
                    model_name="old-model",
                ),
            )


def test_runtime_helper_paths_and_onnx_export_cmd(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    file_path = root / "entry.json"

    safe_path = ars._resolve_safe_child_file_path(
        parent_dir=root,
        file_name="entry.json",
    )
    assert safe_path == file_path.resolve()

    ars._write_json_file_in_dir(
        directory=root,
        file_name="entry.json",
        payload={"ok": True},
    )
    assert json.loads(file_path.read_text(encoding="utf-8")) == {"ok": True}

    cmd = ars._build_onnx_export_cmd(
        builder_script=tmp_path / "builder.py",
        export_input=tmp_path / "input-model",
        execution_provider="cpu",
        precision="fp16",
        tmp_dir=tmp_path / "out",
    )
    assert cmd[0] == ars.sys.executable
    assert cmd[-1] == str((tmp_path / "out"))

    runtime_tmp = ars._prepare_runtime_tmp_dir(name="academy-test")
    assert runtime_tmp.exists()
    ars._cleanup_optional_dir(runtime_tmp)
    assert not runtime_tmp.exists()
    ars._cleanup_optional_dir(None)


def test_subprocess_guard_helpers_timeout_and_memory_exceeded(monkeypatch) -> None:
    class _FakeProcess:
        def __init__(self):
            self.pid = 123
            self._timed_out = False
            self.killed = False

        def communicate(self, timeout: int | None = None):
            if timeout is not None and not self._timed_out:
                self._timed_out = True
                raise ars.subprocess.TimeoutExpired(cmd=["cmd"], timeout=timeout)
            return ("", "")

        def kill(self):
            self.killed = True

        def poll(self):
            return None

    process = _FakeProcess()
    with pytest.raises(RuntimeError, match="merge timed out after 1s"):
        ars._communicate_or_raise_timeout(process=process, timeout_sec=1, stage="merge")
    assert process.killed is True

    state: dict[str, object] = {"peak_rss_mb": 0.0, "exceeded": False}
    stop_event = threading.Event()
    terminate_called = {"value": False}

    monkeypatch.setattr(ars, "_read_process_rss_mb", lambda pid: 256.0)
    monkeypatch.setattr(
        ars,
        "_terminate_process_with_grace",
        lambda **_kwargs: terminate_called.__setitem__("value", True),
    )
    ars._monitor_subprocess_memory(
        process=process,
        state=state,
        stop_event=stop_event,
        max_rss_mb=128,
        monitor_interval_sec=0.01,
    )
    assert state["exceeded"] is True
    assert terminate_called["value"] is True
