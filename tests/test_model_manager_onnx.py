from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

from venom_core.core import model_manager_onnx as onnx_mod


class _Logger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self.messages.append(msg % args if args else msg)


def test_build_onnx_llm_model_validates_inputs(tmp_path: Path) -> None:
    logger = _Logger()
    invalid_name = onnx_mod.build_onnx_llm_model(
        model_name="bad name!",
        output_dir=None,
        execution_provider="cuda",
        precision="int4",
        builder_script=None,
        normalize_slug_fn=lambda s: s,
        logger=logger,
    )
    assert invalid_name["success"] is False

    invalid_provider = onnx_mod.build_onnx_llm_model(
        model_name="good/model",
        output_dir=None,
        execution_provider="xpu",
        precision="int4",
        builder_script=None,
        normalize_slug_fn=lambda s: s,
        logger=logger,
    )
    assert invalid_provider["success"] is False

    invalid_precision = onnx_mod.build_onnx_llm_model(
        model_name="good/model",
        output_dir=None,
        execution_provider="cuda",
        precision="int8",
        builder_script=None,
        normalize_slug_fn=lambda s: s,
        logger=logger,
    )
    assert invalid_precision["success"] is False

    missing_builder = onnx_mod.build_onnx_llm_model(
        model_name="good/model",
        output_dir=None,
        execution_provider="cuda",
        precision="int4",
        builder_script=str(tmp_path / "missing.py"),
        normalize_slug_fn=lambda s: s,
        logger=logger,
    )
    assert missing_builder["success"] is False
    assert "builder.py" in missing_builder["message"]


def test_build_onnx_llm_model_subprocess_errors(tmp_path: Path) -> None:
    logger = _Logger()
    builder = tmp_path / "builder.py"
    builder.write_text("print('ok')", encoding="utf-8")

    with patch("venom_core.core.model_manager_onnx.subprocess.run") as mocked_run:
        mocked_run.side_effect = subprocess.TimeoutExpired("cmd", timeout=1)
        timeout = onnx_mod.build_onnx_llm_model(
            model_name="good/model",
            output_dir=str(tmp_path / "out-timeout"),
            execution_provider="cuda",
            precision="int4",
            builder_script=str(builder),
            normalize_slug_fn=lambda s: s,
            logger=logger,
        )
        assert timeout["success"] is False

    with patch("venom_core.core.model_manager_onnx.subprocess.run") as mocked_run:
        mocked_run.side_effect = RuntimeError("boom")
        generic = onnx_mod.build_onnx_llm_model(
            model_name="good/model",
            output_dir=str(tmp_path / "out-generic"),
            execution_provider="cuda",
            precision="int4",
            builder_script=str(builder),
            normalize_slug_fn=lambda s: s,
            logger=logger,
        )
        assert generic["success"] is False

    with patch("venom_core.core.model_manager_onnx.subprocess.run") as mocked_run:
        mocked_run.return_value = subprocess.CompletedProcess(
            args=["python"],
            returncode=1,
            stdout="out",
            stderr="err",
        )
        failed = onnx_mod.build_onnx_llm_model(
            model_name="good/model",
            output_dir=str(tmp_path / "out-failed"),
            execution_provider="cuda",
            precision="int4",
            builder_script=str(builder),
            normalize_slug_fn=lambda s: s,
            logger=logger,
        )
        assert failed["success"] is False
        assert failed["stderr"] == "err"


def test_build_onnx_llm_model_success_writes_metadata(tmp_path: Path) -> None:
    logger = _Logger()
    builder = tmp_path / "builder.py"
    builder.write_text("print('ok')", encoding="utf-8")
    output_dir = tmp_path / "onnx-out"

    with patch("venom_core.core.model_manager_onnx.subprocess.run") as mocked_run:
        mocked_run.return_value = subprocess.CompletedProcess(
            args=["python"],
            returncode=0,
            stdout="ok",
            stderr="",
        )
        result = onnx_mod.build_onnx_llm_model(
            model_name="good/model",
            output_dir=str(output_dir),
            execution_provider="cuda",
            precision="int4",
            builder_script=str(builder),
            normalize_slug_fn=lambda s: s.replace("/", "--"),
            logger=logger,
        )

    assert result["success"] is True
    metadata_path = output_dir / onnx_mod.ONNX_METADATA_FILENAME
    assert metadata_path.exists()


def test_build_onnx_llm_model_uses_env_builder_and_default_output(
    tmp_path: Path, monkeypatch
) -> None:
    logger = _Logger()
    builder = tmp_path / "builder-env.py"
    builder.write_text("print('ok')", encoding="utf-8")
    monkeypatch.setenv("ONNX_GENAI_BUILDER_SCRIPT", str(builder))

    with patch("venom_core.core.model_manager_onnx.subprocess.run") as mocked_run:
        mocked_run.return_value = subprocess.CompletedProcess(
            args=["python"],
            returncode=0,
            stdout="ok",
            stderr="",
        )
        result = onnx_mod.build_onnx_llm_model(
            model_name="good/model",
            output_dir=None,
            execution_provider="cpu",
            precision="fp16",
            builder_script=None,
            normalize_slug_fn=lambda s: s.replace("/", "--"),
            logger=logger,
        )

    assert result["success"] is True
    assert "good--model-onnx" in result["output_dir"]
