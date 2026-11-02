"""Freeze a separately evaluated dialogue benchmark from audited held-out material."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path

from scripts.granite_operator.comparison_support import load_frozen
from venom_core.services.granite_operator.contract import (
    file_digest,
    inside,
    write_json,
)
from venom_core.services.remote_training.paths import operator_path


def rules(row, receipt, material):
    family = row["family"]
    finish = row["messages"][-1]["tool_calls"][0]["function"]["arguments"]
    base = {
        "status": finish["status"],
        "mutable_files": receipt["mutable_files"],
        "expected_clarifications": sum(m["role"] == "user" for m in row["messages"])
        - 1,
    }
    if family.startswith("cli_"):
        base.update(
            no_terminal=True, syntax_command_argv=shlex.split(finish["summary"])
        )
    elif family.startswith("service_"):
        base["json_files"] = [
            {
                "path": p,
                "value": json.loads(
                    inside(
                        material / "holdout/executed" / row["fixture_id"], p
                    ).read_text()
                ),
            }
            for p in receipt["mutable_files"]
        ]
    elif family == "git_inspect_changes":
        old, new, deleted, untracked = receipt["oracle"]["requirements"]
        base["summary_regexes"] = [
            rf"index\s*:\s*{re.escape(old)}\s*->\s*{re.escape(new)}\s*;\s*deletion\s*:\s*{re.escape(deleted)}\s*;\s*untracked\s*:\s*{re.escape(untracked)}"
        ]
        base["observation_regexes"] = [
            re.escape(p) for p in (old, new, deleted, untracked)
        ]
        base.update(
            verify_command="git --no-optional-locks status --porcelain=v1",
            verify_exit=0,
            verify_regexes=[re.escape(p) for p in (old, new, deleted, untracked)],
        )
    elif family == "discover_test_suites":
        base.update(
            summary_regexes=[re.escape(receipt["oracle"]["requirements"][0])],
            observation_regexes=[re.escape(receipt["oracle"]["requirements"][0])],
            command_regexes=[
                r"pytest[^\n]*\b" + re.escape(shlex.split(s["command"])[-1]) + r"\b"
                for s in receipt["steps"]
                if "pytest" in s["command"]
            ],
            exit_codes=[0, 2],
        )
    elif family == "repair_then_verify":
        base.update(
            verify_command=receipt["steps"][-1]["command"],
            verify_exit=0,
            verify_regexes=["1 passed"],
            observation_regexes=["1 passed"],
        )
    elif family == "filter_log_by_entity":
        files = list(
            (material / "holdout/fixtures" / row["fixture_id"]).rglob("*.jsonl")
        )
        events = [json.loads(line) for line in files[0].read_text().splitlines()]
        wanted = receipt["oracle"]["requirements"][0]
        event = max((e for e in events if e["job"] == wanted), key=lambda e: e["at"])
        base["summary_regexes"] = [
            re.escape(str(event[k])) for k in ("job", "at", "state")
        ]
        base["observation_regexes"] = base["summary_regexes"]
    else:
        raise ValueError("comparison_holdout_family_unsupported")
    return base


def _freeze(material: Path, output: Path):
    material, output = operator_path(material), operator_path(output)
    if output.exists():
        raise ValueError("comparison_holdout_output_exists")
    source_manifest = json.loads((material / "pilot-manifest.json").read_text())
    audit = json.loads((material / "checks/material-audit.json").read_text())
    if audit.get("status") != "PASS_DATA_AUDIT_ONLY":
        raise ValueError("comparison_holdout_material_not_audited")
    frozen = json.loads((material / "FROZEN_FILES.json").read_text())["files"]
    required = {
        "pilot-manifest.json",
        "checks/material-audit.json",
        "holdout/conversations.jsonl",
        "holdout/execution-receipts.jsonl",
    }
    if not required <= set(frozen):
        raise ValueError("comparison_holdout_source_inventory_incomplete")
    for name, metadata in frozen.items():
        if file_digest(inside(material, name)) != metadata["sha256"]:
            raise ValueError("comparison_holdout_source_changed")
    rows = [
        json.loads(line)
        for line in (material / "holdout/conversations.jsonl").read_text().splitlines()
    ]
    receipts = {
        r["fixture_id"]: r
        for r in (
            json.loads(line)
            for line in (material / "holdout/execution-receipts.jsonl")
            .read_text()
            .splitlines()
        )
    }
    cases = []
    for row in rows:
        if row.get("training_allowed") is not False or row.get("split") != "holdout":
            raise ValueError("comparison_holdout_training_record_rejected")
        receipt = receipts[row["fixture_id"]]
        if not receipt["oracle"]["passed"]:
            raise ValueError("comparison_holdout_reference_failed")
        oracle = rules(row, receipt, material)
        users = [m["content"] for m in row["messages"] if m["role"] == "user"]
        prompt = users[0]
        if row["family"] == "git_inspect_changes":
            prompt += " Summary format: index: OLD -> NEW; deletion: DELETED; untracked: NEW_FILE."
        cases.append(
            {
                "id": row["record_id"],
                "problem_group": row["problem_group"],
                "family": row["family"],
                "language": row["language"],
                "split": "heldout",
                "training_allowed": False,
                "fixture": "fixtures/" + row["fixture_id"],
                "system": row["messages"][0]["content"],
                "prompt": prompt,
                "tools": row["tools"],
                "followups": users[1:],
                "oracle": oracle,
            }
        )
    # Publish the manifest last. Partial fixture copies never qualify as a runnable set.
    output.mkdir(parents=True)
    for fid in sorted({row["fixture_id"] for row in rows}):
        if not re.fullmatch(r"[a-z0-9_-]{1,80}", fid):
            raise ValueError("comparison_holdout_fixture_invalid")
        source = operator_path(material / "holdout/fixtures" / fid)
        if not source.resolve().is_relative_to(material.resolve()):
            raise ValueError("comparison_holdout_fixture_invalid")
        if any(p.is_symlink() for p in source.rglob("*")):
            raise ValueError("comparison_holdout_fixture_symlink")
        shutil.copytree(source, output / "fixtures" / fid)
    write_json(
        output / "provenance.json",
        {
            "material_manifest_sha256": file_digest(material / "pilot-manifest.json"),
            "role": "reserved_diagnostic_templates_not_independently_confirmatory",
            "training_started": False,
            "model_loaded": False,
            "human_reply_wait": "simulated_not_measured",
        },
    )
    (output / "cases.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)
    )
    files = {
        str(p.relative_to(output)): file_digest(p)
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    manifest = {
        "cases": "cases.jsonl",
        "case_count": len(cases),
        "files": files,
        "sandbox_image": source_manifest["image"],
        "qualification": {
            "status": "PASS",
            "scope": "audited_reference_data_only_no_model_quality",
        },
        "benchmark_role": "reserved_diagnostic_after_G03_curation",
    }
    write_json(output / "manifest.json", manifest)
    load_frozen(output / "manifest.json")
    return {
        "manifest": str(output / "manifest.json"),
        "case_count": len(cases),
        "status": "REFERENCE_DATA_FROZEN",
    }


def freeze(material: Path, output: Path):
    from venom_core.services.remote_training.lifecycle import file_lock

    material, output = operator_path(material), operator_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(output.with_name(output.name + ".freeze.lock"), blocking=False):
        if output.exists():
            provenance = json.loads((output / "provenance.json").read_text())
            if provenance.get("material_manifest_sha256") != file_digest(
                material / "pilot-manifest.json"
            ):
                raise ValueError("comparison_holdout_output_exists")
            load_frozen(output / "manifest.json")
            return {
                "manifest": str(output / "manifest.json"),
                "status": "REFERENCE_DATA_FROZEN",
            }
        with tempfile.TemporaryDirectory(
            prefix=".dialogue-freeze-", dir=output.parent
        ) as directory:
            staged = Path(directory) / "benchmark"
            result = _freeze(material, staged)
            os.rename(staged, output)
        return {**result, "manifest": str(output / "manifest.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--material", type=operator_path, required=True)
    parser.add_argument("--output", type=operator_path, required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(args.material, args.output), indent=2))


if __name__ == "__main__":
    main()
