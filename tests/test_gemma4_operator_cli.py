"""CPU command integration; no model loading, providers or execution of tools."""

import json
from pathlib import Path

import pytest

from venom_core.services.gemma4_operator import cli

PROFILE = Path(__file__).resolve().parents[1] / "config/gemma4_operator_profile.json"


def test_plan_declares_remote_gates_and_does_not_import_gpu(capsys):
    assert cli.main(["plan", "--profile", str(PROFILE)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["profile"]["model"] == "google/gemma-4-12B-it"
    assert result["training_started"] is False
    assert result["model_loaded"] is False
    assert result["activation_authorized"] is False
    assert all(s["status"] == "DEFERRED_REMOTE" for s in result["remote_gates"])


def test_published_plan_is_immutable(tmp_path, capsys):
    output = tmp_path / "plan.json"
    args = ["plan", "--profile", str(PROFILE), "--output", str(output)]
    assert cli.main(args) == 0
    before = output.read_bytes()
    capsys.readouterr()
    assert cli.main(args) == 1
    assert output.read_bytes() == before
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_invalid_material_never_creates_output(tmp_path, capsys):
    source = tmp_path / "splits.json"
    source.write_text("{broken")
    output = tmp_path / "material.json"
    assert (
        cli.main(["prepare-material", "--input", str(source), "--output", str(output)])
        == 1
    )
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["ok"] is False


@pytest.mark.parametrize("data", [[], {}, {"trials": []}])
def test_comparison_requires_trials_and_identities(tmp_path, capsys, data):
    source = tmp_path / "trials.json"
    source.write_text(json.dumps(data))
    assert cli.main(["compare", "--input", str(source)]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_input_is_bounded_before_parsing(tmp_path, monkeypatch):
    source = tmp_path / "large.json"
    source.write_text("{}")
    monkeypatch.setattr(cli, "MAX_INPUT_BYTES", 1)
    with pytest.raises(ValueError, match="too_large"):
        cli.read_document(source)


def test_missing_snapshot_fails_without_claiming_qualification(tmp_path, capsys):
    assert (
        cli.main(
            ["verify-snapshot", "--profile", str(PROFILE), "--snapshot", str(tmp_path)]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_readiness_mismatch_is_a_nonzero_result(tmp_path, capsys):
    from venom_core.services.gemma4_operator.profile import GemmaProfile
    from venom_core.services.gemma4_operator.runtime import expected_identity

    profile = GemmaProfile.load(PROFILE)
    request = {
        "precision": "nf4",
        "backend": "transformers",
        "backend_version": "test-1",
        "artifact_sha256": "a" * 64,
    }
    identity = expected_identity(profile, request)
    identity["precision"] = "bf16"
    source, observed = tmp_path / "request.json", tmp_path / "observed.json"
    source.write_text(json.dumps(request))
    observed.write_text(json.dumps({"identity": identity}))
    assert (
        cli.main(
            [
                "readiness",
                "--profile",
                str(PROFILE),
                "--request",
                str(source),
                "--observed",
                str(observed),
            ]
        )
        == 2
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "MISMATCH"
    assert result["activation_ready"] is False


def test_failed_evidence_output_never_reports_ok(tmp_path, capsys):
    output = tmp_path / "mismatch.json"
    cli.publish(output, {"status": "MISMATCH", "activation_ready": False})
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["ok"] is False
    assert receipt["exit_code"] == 2
    assert json.loads(output.read_text())["status"] == "MISMATCH"


def test_incomplete_comparison_retains_evidence_and_exits_nonzero(
    tmp_path, capsys, monkeypatch
):
    output = tmp_path / "incomplete.json"
    monkeypatch.setattr(cli, "dispatch", lambda args: {"comparison_complete": False})
    assert cli.main(["plan", "--output", str(output)]) == 3
    assert json.loads(output.read_text())["comparison_complete"] is False
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_deep_json_is_a_structured_error(tmp_path, capsys):
    source = tmp_path / "deep.json"
    source.write_text("[" * 5000 + "0" + "]" * 5000)
    assert cli.main(["compare", "--input", str(source)]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_recursion_during_validation_is_a_structured_error(monkeypatch, capsys):
    def exhausted(args):
        raise RecursionError("validator depth exceeded")

    monkeypatch.setattr(cli, "dispatch", exhausted)
    assert cli.main(["plan"]) == 1
    assert (
        json.loads(capsys.readouterr().out)["error"] == "gemma_input_nesting_exceeded"
    )
