"""202D: Unit tests for direct LoRA adapter deploy to ONNX runtime.

Validates the P0 gap closure:
  - _build_onnx_runtime_model_from_adapter() merges LoRA and exports to ONNX genai format
  - _deploy_adapter_to_onnx_runtime() configures settings after successful export
  - _handle_non_ollama_runtime_deploy() dispatches to ONNX path instead of blocking
  - _rollback_onnx_adapter_deploy() restores previous ONNX model path
  - resolve_runtime_compatibility() now includes onnx=True for HF/unsloth providers
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter_dir(
    tmp_path: Path, *, base_model: str = "google/gemma-3-4b-it"
) -> Path:
    adapter_dir = tmp_path / "test-adapter-001"
    adapter_path = adapter_dir / "adapter"
    adapter_path.mkdir(parents=True)
    (adapter_dir / "metadata.json").write_text(
        json.dumps(
            {
                "adapter_id": "test-adapter-001",
                "base_model": base_model,
                "parameters": {"training_base_model": base_model},
                "signature": None,
            }
        ),
        encoding="utf-8",
    )
    return adapter_dir


def _make_fake_merged_dir(adapter_dir: Path) -> Path:
    merged = adapter_dir / "runtime_vllm"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "config.json").write_text("{}", encoding="utf-8")
    (merged / "model.safetensors").write_bytes(b"\x00")
    (merged / "venom_runtime_vllm.json").write_text("{}", encoding="utf-8")
    return merged


def _make_fake_onnx_dir(adapter_dir: Path) -> Path:
    onnx_dir = adapter_dir / "runtime_onnx"
    onnx_dir.mkdir(parents=True, exist_ok=True)
    (onnx_dir / "genai_config.json").write_text("{}", encoding="utf-8")
    (onnx_dir / "model.onnx").write_bytes(b"\x00")
    (onnx_dir / "venom_runtime_onnx.json").write_text(
        json.dumps({"runtime": "onnx"}), encoding="utf-8"
    )
    return onnx_dir


# ---------------------------------------------------------------------------
# _resolve_onnx_builder_script
# ---------------------------------------------------------------------------


class TestResolveOnnxBuilderScript:
    def test_returns_path_from_env(self, tmp_path: Path) -> None:
        script = tmp_path / "builder.py"
        script.write_text("# mock builder")
        from venom_core.services.academy.adapter_runtime_service import (
            _resolve_onnx_builder_script,
        )

        with patch.dict("os.environ", {"ONNX_GENAI_BUILDER_SCRIPT": str(script)}):
            result = _resolve_onnx_builder_script()
        assert result == script.resolve()

    def test_raises_when_not_found(self, tmp_path: Path) -> None:
        from venom_core.services.academy.adapter_runtime_service import (
            _resolve_onnx_builder_script,
        )

        with (
            patch.dict("os.environ", {"ONNX_GENAI_BUILDER_SCRIPT": ""}),
            patch(
                "venom_core.services.academy.adapter_runtime_service._resolve_repo_root",
                return_value=tmp_path,
            ),
            patch(
                "venom_core.services.academy.adapter_runtime_service.importlib.import_module",
                side_effect=ImportError("missing onnxruntime_genai"),
            ),
        ):
            with pytest.raises(FileNotFoundError, match="ONNX genai builder"):
                _resolve_onnx_builder_script()


# ---------------------------------------------------------------------------
# _build_onnx_runtime_model_from_adapter
# ---------------------------------------------------------------------------


class TestBuildOnnxRuntimeModelFromAdapter:
    def test_returns_existing_onnx_dir_without_rebuilding(self, tmp_path: Path) -> None:
        adapter_dir = _make_adapter_dir(tmp_path)
        onnx_dir = _make_fake_onnx_dir(adapter_dir)
        from venom_core.services.academy.adapter_runtime_service import (
            _build_onnx_runtime_model_from_adapter,
        )

        mock_merge_fn = MagicMock(return_value=onnx_dir)  # should NOT be called
        result = _build_onnx_runtime_model_from_adapter(
            adapter_dir=adapter_dir,
            base_model="google/gemma-3-4b-it",
            build_vllm_runtime_model_from_adapter_fn=mock_merge_fn,
        )
        assert result == onnx_dir
        mock_merge_fn.assert_not_called()

    def test_runs_merge_then_onnx_export(self, tmp_path: Path) -> None:
        adapter_dir = _make_adapter_dir(tmp_path)
        merged_dir = _make_fake_merged_dir(adapter_dir)
        captured_cmd: list[str] = []

        def _fake_builder_subprocess(**kwargs):
            # Simulate builder creating genai_config.json in output dir
            cmd = kwargs["cmd"]
            captured_cmd[:] = cmd
            output_idx = cmd.index("-o") + 1
            out_dir = Path(cmd[output_idx])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "genai_config.json").write_text("{}")
            (out_dir / "model.onnx").write_bytes(b"\x00")
            result = MagicMock()
            result.returncode = 0
            return result

        from venom_core.services.academy.adapter_runtime_service import (
            _build_onnx_runtime_model_from_adapter,
        )

        fake_script = tmp_path / "builder.py"
        fake_script.write_text("")

        with (
            patch(
                "venom_core.services.academy.adapter_runtime_service._resolve_onnx_builder_script",
                return_value=fake_script,
            ),
            patch(
                "venom_core.services.academy.adapter_runtime_service._run_subprocess_with_memory_guard",
                side_effect=_fake_builder_subprocess,
            ),
        ):
            result = _build_onnx_runtime_model_from_adapter(
                adapter_dir=adapter_dir,
                base_model="google/gemma-3-4b-it",
                build_vllm_runtime_model_from_adapter_fn=lambda **_: merged_dir,
            )

        assert result == adapter_dir / "runtime_onnx"
        assert (result / "genai_config.json").exists()
        assert (result / "venom_runtime_onnx.json").exists()
        meta = json.loads((result / "venom_runtime_onnx.json").read_text())
        assert meta["runtime"] == "onnx"
        assert meta["base_model"] == "google/gemma-3-4b-it"
        assert "-i" in captured_cmd
        assert "-m" not in captured_cmd

    def test_normalizes_gemma3_model_type_in_genai_config(self, tmp_path: Path) -> None:
        adapter_dir = _make_adapter_dir(tmp_path)
        merged_dir = _make_fake_merged_dir(adapter_dir)

        def _fake_builder_subprocess(**kwargs):
            cmd = kwargs["cmd"]
            output_idx = cmd.index("-o") + 1
            out_dir = Path(cmd[output_idx])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "genai_config.json").write_text(
                json.dumps({"model": {"type": "gemma3"}}),
                encoding="utf-8",
            )
            (out_dir / "model.onnx").write_bytes(b"\x00")
            result = MagicMock()
            result.returncode = 0
            return result

        from venom_core.services.academy.adapter_runtime_service import (
            _build_onnx_runtime_model_from_adapter,
        )

        fake_script = tmp_path / "builder.py"
        fake_script.write_text("")

        with (
            patch(
                "venom_core.services.academy.adapter_runtime_service._resolve_onnx_builder_script",
                return_value=fake_script,
            ),
            patch(
                "venom_core.services.academy.adapter_runtime_service._run_subprocess_with_memory_guard",
                side_effect=_fake_builder_subprocess,
            ),
        ):
            result = _build_onnx_runtime_model_from_adapter(
                adapter_dir=adapter_dir,
                base_model="google/gemma-3-4b-it",
                build_vllm_runtime_model_from_adapter_fn=lambda **_: merged_dir,
            )

        genai_config = json.loads((result / "genai_config.json").read_text())
        assert genai_config["model"]["type"] == "gemma3_text"

    def test_prepares_text_only_export_input_for_gemma3(self, tmp_path: Path) -> None:
        adapter_dir = _make_adapter_dir(tmp_path)
        merged_dir = _make_fake_merged_dir(adapter_dir)
        (merged_dir / "config.json").write_text(
            json.dumps(
                {
                    "model_type": "gemma3",
                    "architectures": ["Gemma3ForConditionalGeneration"],
                    "text_config": {
                        "model_type": "gemma3_text",
                        "hidden_size": 2560,
                        "vocab_size": 262208,
                    },
                    "eos_token_id": [1, 106],
                    "pad_token_id": 0,
                }
            ),
            encoding="utf-8",
        )
        (merged_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        captured_input_path: Path | None = None

        def _fake_builder_subprocess(**kwargs):
            nonlocal captured_input_path
            cmd = kwargs["cmd"]
            input_idx = cmd.index("-i") + 1
            captured_input_path = Path(cmd[input_idx])
            cfg = json.loads((captured_input_path / "config.json").read_text())
            assert cfg["model_type"] == "gemma3_text"
            assert cfg["architectures"] == ["Gemma3ForCausalLM"]
            assert cfg["eos_token_id"] == [1, 106]
            output_idx = cmd.index("-o") + 1
            out_dir = Path(cmd[output_idx])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "genai_config.json").write_text("{}")
            (out_dir / "model.onnx").write_bytes(b"\x00")
            result = MagicMock()
            result.returncode = 0
            return result

        from venom_core.services.academy.adapter_runtime_service import (
            _build_onnx_runtime_model_from_adapter,
        )

        fake_script = tmp_path / "builder.py"
        fake_script.write_text("")

        with (
            patch(
                "venom_core.services.academy.adapter_runtime_service._resolve_onnx_builder_script",
                return_value=fake_script,
            ),
            patch(
                "venom_core.services.academy.adapter_runtime_service._run_subprocess_with_memory_guard",
                side_effect=_fake_builder_subprocess,
            ),
        ):
            _build_onnx_runtime_model_from_adapter(
                adapter_dir=adapter_dir,
                base_model="google/gemma-3-4b-it",
                build_vllm_runtime_model_from_adapter_fn=lambda **_: merged_dir,
            )

        assert captured_input_path is not None
        assert captured_input_path.name.startswith("runtime_onnx_export_input_tmp_")
        assert not list(adapter_dir.glob("runtime_onnx_export_input_tmp*"))

    def test_raises_on_missing_adapter_path(self, tmp_path: Path) -> None:
        adapter_dir = tmp_path / "no-adapter"
        adapter_dir.mkdir()
        from venom_core.services.academy.adapter_runtime_service import (
            _build_onnx_runtime_model_from_adapter,
        )

        with pytest.raises(FileNotFoundError, match="Adapter path not found"):
            _build_onnx_runtime_model_from_adapter(
                adapter_dir=adapter_dir,
                base_model="google/gemma-3-4b-it",
            )

    def test_cleans_up_tmp_on_export_failure(self, tmp_path: Path) -> None:
        adapter_dir = _make_adapter_dir(tmp_path)
        merged_dir = _make_fake_merged_dir(adapter_dir)
        fake_script = tmp_path / "builder.py"
        fake_script.write_text("")

        def _fail_subprocess(**kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stderr = "mock export error"
            result.stdout = ""
            return result

        from venom_core.services.academy.adapter_runtime_service import (
            _build_onnx_runtime_model_from_adapter,
        )

        with (
            patch(
                "venom_core.services.academy.adapter_runtime_service._resolve_onnx_builder_script",
                return_value=fake_script,
            ),
            patch(
                "venom_core.services.academy.adapter_runtime_service._run_subprocess_with_memory_guard",
                side_effect=_fail_subprocess,
            ),
        ):
            with pytest.raises(RuntimeError, match="ONNX genai export failed"):
                _build_onnx_runtime_model_from_adapter(
                    adapter_dir=adapter_dir,
                    base_model="google/gemma-3-4b-it",
                    build_vllm_runtime_model_from_adapter_fn=lambda **_: merged_dir,
                )
        # tmp dir should be cleaned up
        assert not (adapter_dir / "runtime_onnx_tmp").exists()


# ---------------------------------------------------------------------------
# _deploy_adapter_to_onnx_runtime
# ---------------------------------------------------------------------------


class TestDeployAdapterToOnnxRuntime:
    def test_deploy_success_updates_settings(self, tmp_path: Path) -> None:
        adapter_dir = _make_adapter_dir(tmp_path)
        onnx_dir = _make_fake_onnx_dir(adapter_dir)

        settings = MagicMock()
        settings.ONNX_LLM_MODEL_PATH = "models/old-onnx-model"
        settings.ACTIVE_LLM_SERVER = "ollama"
        settings.LLM_MODEL_NAME = "gemma3:4b"

        config_mgr = MagicMock()
        active_runtime = MagicMock()
        active_runtime.provider = "ollama"

        import venom_core.services.academy.adapter_runtime_service as _svc
        from venom_core.services.academy.adapter_runtime_service import (
            _deploy_adapter_to_onnx_runtime,
        )

        with (
            patch.object(_svc, "_resolve_academy_models_dir", return_value=tmp_path),
            patch.object(
                _svc,
                "_require_trusted_adapter_base_model",
                return_value="google/gemma-3-4b-it",
            ),
            patch.object(
                _svc,
                "_resolve_hf_cache_snapshot_for_repo_id",
                return_value=str((tmp_path / "hf-snapshot").resolve()),
            ),
        ):
            result = _deploy_adapter_to_onnx_runtime(
                adapter_id="test-adapter-001",
                settings_obj=settings,
                config_manager_obj=config_mgr,
                compute_llm_config_hash_fn=lambda *a: "hash-onnx-001",
                runtime_endpoint_for_hash_fn=lambda *a, **kw: None,
                build_onnx_runtime_model_from_adapter_fn=lambda **_: onnx_dir,
                get_active_llm_runtime_fn=lambda: active_runtime,
            )

        assert result["deployed"] is True
        assert result["runtime_id"] == "onnx"
        assert result["chat_model"] == "venom-adapter-test-adapter-001"
        assert result["config_hash"] == "hash-onnx-001"
        assert result["runtime_model_path"] == str(onnx_dir)

        config_mgr.update_config.assert_called_once()
        call_kwargs = config_mgr.update_config.call_args[0][0]
        assert call_kwargs["ACTIVE_LLM_SERVER"] == "onnx"
        assert call_kwargs["ONNX_LLM_ENABLED"] is True
        assert call_kwargs["ONNX_LLM_MODEL_PATH"] == str(onnx_dir)
        assert call_kwargs["PREVIOUS_ONNX_LLM_MODEL_PATH"] == "models/old-onnx-model"

    def test_deploy_raises_when_genai_config_missing(self, tmp_path: Path) -> None:
        adapter_dir = _make_adapter_dir(tmp_path)
        bad_onnx_dir = adapter_dir / "runtime_onnx"
        bad_onnx_dir.mkdir()
        # no genai_config.json

        from venom_core.services.academy.adapter_runtime_service import (
            _deploy_adapter_to_onnx_runtime,
        )

        with pytest.raises(RuntimeError, match="genai_config.json missing"):
            import venom_core.services.academy.adapter_runtime_service as _svc2

            with (
                patch.object(
                    _svc2, "_resolve_academy_models_dir", return_value=tmp_path
                ),
                patch.object(
                    _svc2,
                    "_require_trusted_adapter_base_model",
                    return_value="google/gemma-3-4b-it",
                ),
                patch.object(
                    _svc2,
                    "_resolve_hf_cache_snapshot_for_repo_id",
                    return_value=str((tmp_path / "hf-snapshot").resolve()),
                ),
            ):
                _deploy_adapter_to_onnx_runtime(
                    adapter_id="test-adapter-001",
                    settings_obj=MagicMock(ONNX_LLM_MODEL_PATH=""),
                    config_manager_obj=MagicMock(),
                    compute_llm_config_hash_fn=lambda *a: "h",
                    runtime_endpoint_for_hash_fn=lambda *a, **kw: None,
                    build_onnx_runtime_model_from_adapter_fn=lambda **_: bad_onnx_dir,
                    get_active_llm_runtime_fn=lambda: MagicMock(provider="ollama"),
                )

    def test_deploy_raises_when_adapter_dir_missing(self, tmp_path: Path) -> None:
        adapter_dir = _make_adapter_dir(tmp_path)
        # remove the "adapter" subdirectory to simulate missing artifacts
        import shutil

        shutil.rmtree(adapter_dir / "adapter")

        import venom_core.services.academy.adapter_runtime_service as _svc3
        from venom_core.services.academy.adapter_runtime_service import (
            _deploy_adapter_to_onnx_runtime,
        )

        with (
            patch.object(_svc3, "_resolve_academy_models_dir", return_value=tmp_path),
            pytest.raises(FileNotFoundError, match="Adapter not found"),
        ):
            _deploy_adapter_to_onnx_runtime(
                adapter_id="test-adapter-001",
                settings_obj=MagicMock(ONNX_LLM_MODEL_PATH=""),
                config_manager_obj=MagicMock(),
                compute_llm_config_hash_fn=lambda *a: "h",
                runtime_endpoint_for_hash_fn=lambda *a, **kw: None,
                build_onnx_runtime_model_from_adapter_fn=MagicMock(),
                get_active_llm_runtime_fn=lambda: MagicMock(provider="ollama"),
            )

    def test_deploy_prefers_local_training_base_model_for_merge(
        self, tmp_path: Path
    ) -> None:
        adapter_dir = _make_adapter_dir(tmp_path)
        local_base = tmp_path / "local-gemma-base"
        local_base.mkdir(parents=True, exist_ok=True)
        (local_base / "config.json").write_text("{}", encoding="utf-8")
        metadata = json.loads(
            (adapter_dir / "metadata.json").read_text(encoding="utf-8")
        )
        metadata["parameters"] = {"training_base_model": str(local_base)}
        (adapter_dir / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        onnx_dir = _make_fake_onnx_dir(adapter_dir)
        received_base_model: dict[str, str] = {}

        def _fake_build_fn(**kwargs):
            received_base_model["value"] = str(kwargs.get("base_model") or "")
            return onnx_dir

        import venom_core.services.academy.adapter_runtime_service as _svc4
        from venom_core.services.academy.adapter_runtime_service import (
            _deploy_adapter_to_onnx_runtime,
        )

        with (
            patch.object(_svc4, "_resolve_academy_models_dir", return_value=tmp_path),
            patch.object(
                _svc4,
                "_require_trusted_adapter_base_model",
                return_value="google/gemma-3-4b-it",
            ),
        ):
            _deploy_adapter_to_onnx_runtime(
                adapter_id="test-adapter-001",
                settings_obj=MagicMock(ONNX_LLM_MODEL_PATH=""),
                config_manager_obj=MagicMock(),
                compute_llm_config_hash_fn=lambda *a: "h",
                runtime_endpoint_for_hash_fn=lambda *a, **kw: None,
                build_onnx_runtime_model_from_adapter_fn=_fake_build_fn,
                get_active_llm_runtime_fn=lambda: MagicMock(provider="ollama"),
            )

        assert received_base_model.get("value") == str(local_base.resolve())


# ---------------------------------------------------------------------------
# _handle_non_ollama_runtime_deploy  — ONNX now dispatches instead of blocking
# ---------------------------------------------------------------------------


class TestHandleNonOllamaRuntimeDeployOnnx:
    def test_onnx_dispatches_to_deploy_fn(self) -> None:
        from venom_core.services.academy.adapter_runtime_service import (
            _handle_non_ollama_runtime_deploy,
        )

        mock_deploy = MagicMock(
            return_value={
                "deployed": True,
                "runtime_id": "onnx",
                "chat_model": "venom-adapter-x",
                "config_hash": "h",
            }
        )
        result = _handle_non_ollama_runtime_deploy(
            runtime_local_id="onnx",
            adapter_id="x",
            deploy_adapter_to_onnx_runtime_fn=mock_deploy,
        )
        assert result["deployed"] is True
        assert result["runtime_id"] == "onnx"
        mock_deploy.assert_called_once_with(adapter_id="x")

    def test_onnx_does_not_return_runtime_not_supported(self, tmp_path: Path) -> None:
        """Regression: old code returned runtime_not_supported:onnx — 202D removes this."""
        _make_fake_onnx_dir(_make_adapter_dir(tmp_path))

        from venom_core.services.academy.adapter_runtime_service import (
            _handle_non_ollama_runtime_deploy,
        )

        result = _handle_non_ollama_runtime_deploy(
            runtime_local_id="onnx",
            adapter_id="test-adapter-001",
            deploy_adapter_to_onnx_runtime_fn=lambda **_: {
                "deployed": True,
                "runtime_id": "onnx",
                "chat_model": "venom-adapter-test-adapter-001",
                "config_hash": "h",
            },
        )
        # Must NOT be the old blocking response
        assert result.get("reason") != "runtime_not_supported:onnx"
        assert result.get("deployed") is True


# ---------------------------------------------------------------------------
# _rollback_onnx_adapter_deploy
# ---------------------------------------------------------------------------


class TestRollbackOnnxAdapterDeploy:
    def test_rollback_restores_previous_onnx_path(self) -> None:
        from venom_core.services.academy.adapter_runtime_service import (
            _rollback_onnx_adapter_deploy,
        )

        config = {
            "PREVIOUS_ONNX_LLM_MODEL_PATH": "models/phi3.5-mini-instruct-onnx",
            "PREVIOUS_MODEL_ONNX": "phi3.5-mini",
        }
        settings = MagicMock()
        settings.LAST_MODEL_ONNX = ""
        config_mgr = MagicMock()

        result = _rollback_onnx_adapter_deploy(
            config=config,
            settings_obj=settings,
            config_manager_obj=config_mgr,
            compute_llm_config_hash_fn=lambda *a: "hash-rollback",
            runtime_endpoint_for_hash_fn=lambda *a, **kw: None,
        )

        assert result["rolled_back"] is True
        assert result["runtime_id"] == "onnx"
        assert result["chat_model"] == "phi3.5-mini"

        update_call = config_mgr.update_config.call_args[0][0]
        assert update_call["ONNX_LLM_MODEL_PATH"] == "models/phi3.5-mini-instruct-onnx"
        assert update_call["ONNX_LLM_ENABLED"] is True
        assert update_call["PREVIOUS_ONNX_LLM_MODEL_PATH"] == ""
        assert update_call["PREVIOUS_MODEL_ONNX"] == ""

    def test_rollback_fails_when_previous_path_missing(self) -> None:
        from venom_core.services.academy.adapter_runtime_service import (
            _rollback_onnx_adapter_deploy,
        )

        config = {
            "PREVIOUS_ONNX_LLM_MODEL_PATH": "",
            "PREVIOUS_MODEL_ONNX": "phi3.5-mini",
        }
        settings = MagicMock()
        settings.LAST_MODEL_ONNX = ""
        config_mgr = MagicMock()

        result = _rollback_onnx_adapter_deploy(
            config=config,
            settings_obj=settings,
            config_manager_obj=config_mgr,
            compute_llm_config_hash_fn=lambda *a: "hash-r",
            runtime_endpoint_for_hash_fn=lambda *a, **kw: None,
        )

        assert result["rolled_back"] is False
        assert result["reason"] == "previous_path_missing"
        config_mgr.update_config.assert_not_called()

    def test_rollback_fails_gracefully_when_no_previous_info(self) -> None:
        from venom_core.services.academy.adapter_runtime_service import (
            _rollback_onnx_adapter_deploy,
        )

        config: dict = {}
        settings = MagicMock()
        settings.LAST_MODEL_ONNX = ""
        config_mgr = MagicMock()

        result = _rollback_onnx_adapter_deploy(
            config=config,
            settings_obj=settings,
            config_manager_obj=config_mgr,
            compute_llm_config_hash_fn=lambda *a: "h",
            runtime_endpoint_for_hash_fn=lambda *a, **kw: None,
        )

        assert result["rolled_back"] is False
        assert result["reason"] == "previous_model_missing"


# ---------------------------------------------------------------------------
# resolve_runtime_compatibility — ONNX now True for HF/unsloth providers
# ---------------------------------------------------------------------------


class TestRuntimeCompatibilityOnnx202D:
    def test_onnx_is_compatible_for_hf_provider(self) -> None:
        from venom_core.services.academy.trainable_catalog_service import (
            resolve_runtime_compatibility,
        )

        compat = resolve_runtime_compatibility(
            provider="huggingface",
            available_runtime_ids=["vllm", "ollama", "onnx"],
            model_id="google/gemma-3-4b-it",
        )
        assert compat.get("onnx") is True, (
            "202D: ONNX must be compatible for HuggingFace models (direct deploy supported)"
        )

    def test_onnx_is_compatible_for_unsloth_provider(self) -> None:
        from venom_core.services.academy.trainable_catalog_service import (
            resolve_runtime_compatibility,
        )

        compat = resolve_runtime_compatibility(
            provider="unsloth",
            available_runtime_ids=["vllm", "ollama", "onnx"],
            model_id="unsloth/Phi-3-mini-4k-instruct",
        )
        assert compat.get("onnx") is True, (
            "202D: ONNX must be compatible for unsloth provider models"
        )

    def test_onnx_artifact_stays_incompatible_with_ollama(self) -> None:
        """ONNX artifacts themselves are still inference-only, not LoRA-trainable."""
        from venom_core.services.academy.trainable_catalog_service import (
            resolve_runtime_compatibility,
        )

        compat = resolve_runtime_compatibility(
            provider="onnx",  # model IS an ONNX artifact
            available_runtime_ids=["vllm", "ollama", "onnx"],
            model_id="phi3.5-mini-instruct-onnx",
        )
        assert compat.get("ollama") is False


# ---------------------------------------------------------------------------
# Integration: onnx_runtime_compatibility_flag satisfies 202D P0 criteria
# ---------------------------------------------------------------------------


class TestP0CriteriaSatisfied:
    def test_direct_adapter_deploy_to_onnx_flag(self, tmp_path: Path) -> None:
        """Verify _handle_non_ollama_runtime_deploy returns deployed=True for ONNX (P0 gate)."""
        from venom_core.services.academy.adapter_runtime_service import (
            _handle_non_ollama_runtime_deploy,
        )

        adapter_dir = _make_adapter_dir(tmp_path)
        onnx_dir = _make_fake_onnx_dir(adapter_dir)

        result = _handle_non_ollama_runtime_deploy(
            runtime_local_id="onnx",
            adapter_id="test-adapter-001",
            deploy_adapter_to_onnx_runtime_fn=lambda **kw: {
                "deployed": True,
                "runtime_id": "onnx",
                "chat_model": f"venom-adapter-{kw['adapter_id']}",
                "config_hash": "h",
                "runtime_model_path": str(onnx_dir),
            },
        )
        assert result.get("deployed") is True, (
            "P0: direct_adapter_deploy_to_onnx must be True"
        )
        assert result.get("runtime_id") == "onnx"

    def test_onnx_runtime_compatibility_flag(self) -> None:
        """Verify onnx_runtime_compatibility_flag=True for Gemma-3 (P0 gate)."""
        from venom_core.services.academy.trainable_catalog_service import (
            assess_runtime_base_model_compatibility,
        )

        assessment = assess_runtime_base_model_compatibility(
            base_model="google/gemma-3-4b-it",
            runtime_id="onnx",
            available_runtime_ids=["vllm", "ollama", "onnx"],
        )
        assert assessment["is_compatible"] is True, (
            "P0: onnx_runtime_compatibility_flag must be True for gemma-3-4b-it"
        )
