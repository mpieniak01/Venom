"""CPU command integration; no model loading, providers or execution of tools."""

import json
from pathlib import Path

import pytest

from venom_core.services.gemma4_operator import cli

PROFILE = Path(__file__).resolve().parents[1] / "config/gemma4_operator_profile.json"


@pytest.fixture(autouse=True)
def approved_material_root(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA_OPERATOR_DATA_ROOT", str(tmp_path))


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


def test_input_outside_approved_root_is_rejected(tmp_path):
    outside = tmp_path.parent / "gemma-private-document.json"
    outside.write_text('{"private": true}')
    with pytest.raises(ValueError, match="outside_approved"):
        cli.read_document(outside)


def test_output_traversal_cannot_create_file(tmp_path):
    outside = tmp_path / ".." / "gemma-escape-evidence.json"
    with pytest.raises(ValueError, match="outside_approved"):
        cli.publish(outside, {"status": "PREPARED"})
    assert not outside.exists()


def test_symlink_parent_cannot_bypass_root(tmp_path):
    outside = tmp_path.parent / "gemma-other-source"
    outside.mkdir(exist_ok=True)
    source = outside / "data.json"
    source.write_text("{}")
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        cli.read_document(linked / "data.json")


def test_profile_cannot_read_external_file(tmp_path):
    from venom_core.services.gemma4_operator.profile import GemmaProfile

    outside = tmp_path.parent / "gemma-external-profile.json"
    outside.write_text(PROFILE.read_text())
    with pytest.raises(ValueError, match="outside_approved"):
        GemmaProfile.load(outside)


def test_non_json_output_is_rejected(tmp_path):
    output = tmp_path / "arbitrary.py"
    with pytest.raises(ValueError, match="json_path"):
        cli.publish(output, {"status": "PREPARED"})


def test_operator_root_must_be_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA_OPERATOR_DATA_ROOT", "relative-root")
    source = tmp_path / "input.json"
    source.write_text("{}")
    with pytest.raises(ValueError, match="must_be_absolute"):
        cli.read_document(source)


def test_write_failure_does_not_publish_partial_evidence(tmp_path, monkeypatch):
    def no_space(fd):
        raise OSError("no space left")

    monkeypatch.setattr(cli.os, "fsync", no_space)
    output = tmp_path / "complete.json"
    with pytest.raises(OSError, match="space"):
        cli.publish(output, {"status": "PREPARED"})
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_concurrent_output_is_not_replaced(tmp_path, monkeypatch):
    def occupied(source, target):
        target.write_text("previous evidence")
        raise FileExistsError("concurrent output")

    monkeypatch.setattr(cli.os, "link", occupied)
    output = tmp_path / "race.json"
    with pytest.raises(FileExistsError):
        cli.publish(output, {"status": "PREPARED"})
    assert output.read_text() == "previous evidence"
    assert list(tmp_path.iterdir()) == [output]


def test_compare_configuration_mismatch_exits_two(tmp_path, capsys):
    common = {
        "model": "google/gemma-4-12B-it",
        "revision": "a" * 40,
        "requested_precision": "nf4",
        "effective_precision": "nf4",
        "runtime_backend": "transformers",
        "runtime_version": "1.0",
        "context": 4096,
        "max_new_tokens": 192,
        "seed": 17,
        "concurrency": 4,
        "tools_sha256": "b" * 64,
        "evaluator_sha256": "c" * 64,
        "benchmark_sha256": "d" * 64,
        "tokenizer_sha256": "e" * 64,
        "template_sha256": "f" * 64,
    }
    arms = {
        "base": common,
        "adapter": common
        | {
            "adapter_sha256": "1" * 64,
            "runtime_version": "2.0",
        },
    }
    source = tmp_path / "different.json"
    source.write_text(json.dumps({"identities": arms, "trials": []}))
    assert cli.main(["compare", "--input", str(source)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "MISMATCH"


def test_missing_optional_dependency_is_structured(monkeypatch, capsys):
    def unavailable(args):
        raise RuntimeError(
            "gemma_schema_dependency_missing: install requirements-gemma4-operator-control.txt"
        )

    monkeypatch.setattr(cli, "dispatch", unavailable)
    assert cli.main(["plan"]) == 1
    assert (
        "requirements-gemma4-operator-control.txt"
        in json.loads(capsys.readouterr().out)["error"]
    )
