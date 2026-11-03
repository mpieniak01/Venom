"""Offline fixture qualification, bounded I/O and independent result verification."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from venom_core.services.gemma4_operator import benchmark
from venom_core.services.gemma4_operator.paths import DATA_ROOT_ENV

SAMPLE = Path(__file__).resolve().parents[1] / "config/gemma4_operator_benchmark"


def checksum(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))
    target = tmp_path / "benchmark"
    shutil.copytree(SAMPLE, target)
    return target


def seal(bundle):
    path = bundle / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"] = {
        p.relative_to(bundle).as_posix(): checksum(p.read_bytes())
        for p in bundle.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    path.write_text(json.dumps(manifest))
    return path


def cases(bundle):
    return [
        json.loads(line) for line in (bundle / "cases.jsonl").read_text().splitlines()
    ]


def rewrite_cases(bundle, rows):
    (bundle / "cases.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return seal(bundle)


def test_bundled_sample_is_explicitly_reference_only_and_preserves_sources():
    before = {p: checksum(p.read_bytes()) for p in SAMPLE.rglob("*") if p.is_file()}
    result = benchmark.qualify_cases(SAMPLE / "manifest.json")
    assert result["status"] == "REFERENCE_PASS"
    assert result["case_count"] == 2
    assert result["qualification"] == "synthetic_sample_not_final_benchmark"
    assert result["executor_kind"] == "builtin_inprocess"
    assert result["model_evaluated"] is False
    assert result["activation_authorized"] is False
    assert all(row["arm"] == "reference" for row in result["trials"])
    assert all(row["reference_observations"] for row in result["trials"])
    assert before == {p: checksum(p.read_bytes()) for p in before}


def test_source_tampering_fails_before_executor(bundle):
    target = bundle / "fixtures/router/config/route.json"
    target.write_text("{}")
    called = []

    def execute(case, workspace):
        called.append(case)
        return {"status": "success"}

    with pytest.raises(ValueError, match="source_hash_mismatch"):
        benchmark.qualify_cases(bundle / "manifest.json", executor=execute)
    assert called == []


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("case_count", True, "case_count_invalid"),
        ("case_count", 99, "case_count_invalid"),
        ("qualification", "independent_final_benchmark", "qualification_invalid"),
        ("schema_version", True, "schema_version_invalid"),
    ],
)
def test_manifest_rejects_unqualified_or_malformed_claims(bundle, field, value, error):
    path = bundle / "manifest.json"
    value_doc = json.loads(path.read_text())
    value_doc[field] = value
    path.write_text(json.dumps(value_doc))
    with pytest.raises(ValueError, match=error):
        benchmark.qualify_cases(path)


def test_untracked_file_fails_strict_inventory(bundle):
    (bundle / "extra.txt").write_text("not declared")
    with pytest.raises(ValueError, match="inventory_mismatch"):
        benchmark.load_cases(bundle / "manifest.json")


def test_source_symlink_is_never_followed(bundle, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    target = bundle / "fixtures/router/protected.txt"
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(ValueError, match="special_file"):
        benchmark.load_cases(bundle / "manifest.json")


@pytest.mark.parametrize(
    "path", ["../outside", "/tmp/outside", "a/../b", "a//b", ".", "C:/file", "a\\b"]
)
def test_case_paths_cannot_escape_workspace(bundle, path):
    rows = cases(bundle)
    rows[0]["reference_actions"][0] = {"name": "ReadFile", "arguments": {"path": path}}
    manifest = rewrite_cases(bundle, rows)
    with pytest.raises(ValueError, match="relative_path_invalid"):
        benchmark.load_cases(manifest)


def test_arbitrary_commands_are_rejected_before_execution(bundle):
    rows = cases(bundle)
    rows[0]["reference_actions"][0] = {
        "name": "Terminal",
        "arguments": {"command": "touch outside"},
    }
    manifest = rewrite_cases(bundle, rows)
    with pytest.raises(ValueError, match="operation_not_allowed"):
        benchmark.qualify_cases(manifest)


def test_reference_write_must_be_within_declared_mutability(bundle):
    rows = cases(bundle)
    rows[0]["reference_actions"][-1]["arguments"]["path"] = "protected.txt"
    manifest = rewrite_cases(bundle, rows)
    with pytest.raises(ValueError, match="reference_scope_violation"):
        benchmark.qualify_cases(manifest)


def test_expected_state_cannot_authorize_changes_to_protected_files(bundle):
    rows = cases(bundle)
    rows[0]["expected_files"]["protected.txt"] = "a" * 64
    manifest = rewrite_cases(bundle, rows)
    with pytest.raises(ValueError, match="expected_protected_mutation"):
        benchmark.qualify_cases(manifest)


def test_claimed_success_without_repair_is_a_model_error(bundle):
    def no_repair(case, workspace):
        assert "expected_files" not in case
        assert "reference_actions" not in case
        return {"status": "success"}

    report = benchmark.qualify_cases(bundle / "manifest.json", executor=no_repair)
    assert report["status"] == "REFERENCE_FAIL"
    for row in report["trials"]:
        assert row["failure_kind"] == "model"
        assert row["oracle"]["success_without_oracle_confirmation"]
        assert row["oracle"]["success"] is False


def test_injected_executor_cannot_modify_verifier_inputs(bundle):
    def alter_labels(case, workspace):
        case["expected_files"] = {}
        case["mutable_files"].append("protected.txt")
        (workspace / "protected.txt").write_text("changed")
        return {"status": "success"}

    report = benchmark.qualify_cases(bundle / "manifest.json", executor=alter_labels)
    assert report["status"] == "REFERENCE_FAIL"
    assert "protected.txt" in report["trials"][0]["oracle"]["scope_violations"]


def test_injected_workspace_symlink_is_a_scope_violation(bundle, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("do not expose")

    def symlink(case, workspace):
        (workspace / "link").symlink_to(outside)
        return {"status": "success"}

    report = benchmark.qualify_cases(bundle / "manifest.json", executor=symlink)
    assert report["trials"][0]["oracle"]["errors"] == ["unsafe_workspace"]
    assert outside.read_text() == "do not expose"


def test_unexpected_executor_errors_remain_infrastructure_errors(bundle):
    workspaces = []

    def unavailable(case, workspace):
        workspaces.append(workspace)
        raise RuntimeError("private failure detail")

    report = benchmark.qualify_cases(bundle / "manifest.json", executor=unavailable)
    assert report["status"] == "REFERENCE_FAIL"
    assert all(row["failure_kind"] == "infrastructure" for row in report["trials"])
    assert all(row["executor_error_type"] == "RuntimeError" for row in report["trials"])
    assert "private failure detail" not in json.dumps(report)
    assert all(not p.exists() for p in workspaces)


@pytest.mark.parametrize(
    "outcome",
    [
        None,
        {"status": True},
        {"status": "success", "timed_out": "no"},
        {"status": "success", "failure_kind": "unknown"},
    ],
)
def test_invalid_executor_result_cannot_become_success(bundle, outcome):
    def invalid(case, workspace):
        return outcome

    report = benchmark.qualify_cases(bundle / "manifest.json", executor=invalid)
    assert report["status"] == "REFERENCE_FAIL"
    assert report["trials"][0]["failure_kind"] == "infrastructure"


def test_explicit_infrastructure_failure_is_not_classified_as_model_error(bundle):
    def unavailable(case, workspace):
        return {"status": "failed", "failure_kind": "infrastructure"}

    report = benchmark.qualify_cases(bundle / "manifest.json", executor=unavailable)
    assert report["trials"][0]["failure_kind"] == "infrastructure"


@pytest.mark.parametrize("timed_out", [False, True])
def test_valid_trusted_adapter_repairs_state_without_receiving_expected_answers(
    bundle, timed_out
):
    data = cases(bundle)
    repairs = {
        case["id"]: (
            case["reference_actions"][-1]["arguments"]["path"],
            case["reference_actions"][-1]["arguments"]["content"],
        )
        for case in data
    }

    def repair(case, workspace):
        assert "expected_files" not in case
        name, content = repairs[case["id"]]
        (workspace / name).write_text(content)
        return {"status": "success", "timed_out": timed_out}

    report = benchmark.qualify_cases(bundle / "manifest.json", executor=repair)
    assert report["status"] == ("REFERENCE_FAIL" if timed_out else "REFERENCE_PASS")
    if timed_out:
        assert all(row["oracle"]["errors"] == ["timed_out"] for row in report["trials"])
        assert all(row["failure_kind"] == "model" for row in report["trials"])
    assert report["executor_kind"] == "trusted_injected_adapter"
    assert report["model_evaluated"] is False


def test_timed_out_repair_remains_unsuccessful(bundle):
    def timed_out(case, workspace):
        return {"status": "success", "timed_out": True}

    report = benchmark.qualify_cases(bundle / "manifest.json", executor=timed_out)
    assert report["trials"][0]["timed_out"] is True
    assert report["trials"][0]["oracle"]["success"] is False


def test_case_groups_cannot_cross_splits(bundle):
    rows = cases(bundle)
    rows[1]["problem_group"] = rows[0]["problem_group"]
    rows[1]["split"] = "holdout"
    manifest = rewrite_cases(bundle, rows)
    with pytest.raises(ValueError, match="group_leakage"):
        benchmark.load_cases(manifest)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("id", "../bad", "case_id_invalid"),
        ("split", "train", "split_invalid"),
        ("reference_actions", [], "steps_invalid"),
        (
            "mutable_files",
            ["config/route.json", "config/route.json"],
            "mutable_files_invalid",
        ),
        ("fixture", "fixtures/missing", "fixture_missing"),
    ],
)
def test_case_header_and_reference_steps_are_strict(bundle, field, value, error):
    rows = cases(bundle)
    rows[0][field] = value
    manifest = rewrite_cases(bundle, rows)
    with pytest.raises(ValueError, match=error):
        benchmark.load_cases(manifest)


def test_files_declared_but_unused_by_cases_are_rejected(bundle):
    (bundle / "unused.txt").write_text("unused")
    manifest = seal(bundle)
    with pytest.raises(ValueError, match="unused_inventory"):
        benchmark.load_cases(manifest)


def test_per_file_quota_is_checked_before_hashing(bundle):
    (bundle / "fixtures/router/protected.txt").write_bytes(
        b"a" * (benchmark.MAX_FILE_BYTES + 1)
    )
    with pytest.raises(ValueError, match="file_limit"):
        benchmark.load_cases(bundle / "manifest.json")


def test_workspace_read_error_is_a_per_case_infrastructure_result(bundle, monkeypatch):
    original_snapshot = benchmark._snapshot
    executed = set()

    def snapshot(workspace):
        if workspace in executed:
            raise PermissionError("simulated unreadable result")
        return original_snapshot(workspace)

    def unreadable(case, workspace):
        executed.add(workspace)
        return {"status": "success"}

    monkeypatch.setattr(benchmark, "_snapshot", snapshot)
    report = benchmark.qualify_cases(bundle / "manifest.json", executor=unreadable)
    assert report["status"] == "REFERENCE_FAIL"
    assert len(report["trials"]) == 2
    assert all(row["failure_kind"] == "infrastructure" for row in report["trials"])
    assert all(
        row["executor_error_type"] == "PermissionError" for row in report["trials"]
    )
    assert all(
        "workspace_io_error" in row["oracle"]["errors"] for row in report["trials"]
    )


def test_success_claim_with_explicit_failure_has_consistent_oracle_flags(bundle):
    repairs = {
        case["id"]: case["reference_actions"][-1]["arguments"] for case in cases(bundle)
    }

    def contradictory(case, workspace):
        repair = repairs[case["id"]]
        (workspace / repair["path"]).write_text(repair["content"])
        return {"status": "success", "failure_kind": "infrastructure"}

    report = benchmark.qualify_cases(bundle / "manifest.json", executor=contradictory)
    for row in report["trials"]:
        assert row["oracle"]["success"] is False
        assert row["oracle"]["incorrect_success_status"] is True
        assert row["oracle"]["success_without_oracle_confirmation"] is True


def test_symlinked_temporary_parent_preserves_qualification_and_sources(
    bundle, tmp_path, monkeypatch
):
    real_parent = tmp_path / "real-temp"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-temp"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    monkeypatch.setattr(benchmark.tempfile, "tempdir", str(linked_parent))
    before = {
        path.relative_to(bundle).as_posix(): checksum(path.read_bytes())
        for path in bundle.rglob("*")
        if path.is_file()
    }

    report = benchmark.qualify_cases(bundle / "manifest.json")

    assert report["status"] == "REFERENCE_PASS"
    assert all(row["oracle"]["success"] for row in report["trials"])
    assert list(real_parent.iterdir()) == []
    after = {
        path.relative_to(bundle).as_posix(): checksum(path.read_bytes())
        for path in bundle.rglob("*")
        if path.is_file()
    }
    assert after == before
