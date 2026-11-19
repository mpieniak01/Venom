"""Replay selected Academy receipts offline against a sealed expectation manifest.

A manifest contains schema_version=1 and cases, each with id, receipt (relative
to the manifest or absolute), receipt_sha256, and expected (all decision fields
except reason). IDs refer to archived case labels. Different attempts for the
same case may be listed separately. Targeted panels may additionally bind
targeted_protocol_sha256 to the protocol alongside the receipts directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import uuid
from pathlib import Path

from venom_core.services.remote_training.lifecycle import validate_run_id
from venom_core.services.remote_training.paths import data_directory, operator_path
from venom_core.services.training_experiments import openrouter_semantic_judge as judge
from venom_core.services.training_experiments.profiles import (
    MAX_JSON_BYTES,
    stable_hash,
)

_HOLDOUT_COMPONENTS = {"holdout", "heldout", "held-out", "holdout-input"}
_REPEATABLE_STATUSES = {"completed", "failed", "rejected_decision"}
_MATERIAL_FIELDS = {"candidate", "criteria", "evidence", "messages"}


def _require(condition: bool, error: str) -> None:
    if not condition:
        raise ValueError(error)


def _offline_path(path: Path) -> Path:
    path = operator_path(path)
    _require(
        not any(part.casefold() in _HOLDOUT_COMPONENTS for part in path.parts),
        "offline_replay_holdout_excluded",
    )
    return path


def _sealed_json(path: Path, expected_sha256: str) -> dict:
    _require(
        isinstance(expected_sha256, str)
        and re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is not None,
        "offline_replay_invalid_sha256",
    )
    with data_directory(path.parent) as directory_fd:
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            _require(stat.S_ISREG(metadata.st_mode), "offline_replay_not_regular_file")
            _require(
                metadata.st_size <= MAX_JSON_BYTES, "offline_replay_input_too_large"
            )
            raw = stream.read(MAX_JSON_BYTES + 1)
    _require(len(raw) <= MAX_JSON_BYTES, "offline_replay_input_too_large")
    _require(hashlib.sha256(raw).hexdigest() == expected_sha256, "offline_replay_hash")
    value = json.loads(raw)
    _require(isinstance(value, dict), "offline_replay_invalid_json")
    return value


def _targeted_selection(path: Path, index: int, protocol_sha: str) -> dict:
    root = path.parent.parent
    protocol = _sealed_json(root / "protocol.json", protocol_sha)
    _require(
        protocol.get("kind") == "targeted_regression"
        and type(protocol.get("planned_requests")) is int
        and 0 < index <= protocol["planned_requests"] <= 228,
        "offline_replay_non_targeted_index",
    )
    panel = _sealed_json(root / "panel.json", protocol["panel_sha256"])
    order, cases = panel.get("order"), panel.get("cases")
    _require(
        isinstance(order, list) and isinstance(cases, dict),
        "offline_replay_invalid_panel",
    )
    assert isinstance(order, list)
    assert isinstance(cases, dict)
    _require(
        len(order) == protocol["planned_requests"]
        and all(isinstance(label, str) for label in order)
        and set(order) == set(cases)
        and all(order.count(label) == 2 for label in cases),
        "offline_replay_invalid_panel",
    )
    label = order[index - 1]
    return {
        "protocol_sha256": protocol_sha,
        "label": label,
        "body": cases[label]["body"],
    }


def _receipt_path(path: Path, entry: dict) -> tuple[Path, int, dict | None]:
    path = _offline_path(path)
    match = re.fullmatch(r"([0-9]{3})[.]json", path.name)
    _require(
        path.parent.name == "receipts" and match is not None,
        "offline_replay_expected_receipt_path",
    )
    assert match is not None
    index = int(match[1])
    # A targeted protocol must be sealed before any receipt beyond phase one
    # is read; the full audit's holdout remains excluded at this boundary.
    protocol_sha = entry.get("targeted_protocol_sha256")
    targeted = None
    if protocol_sha is not None:
        targeted = _targeted_selection(path, index, protocol_sha)
    else:
        _require(
            0 < index <= sum(judge.PHASE1.values()), "offline_replay_non_phase1_index"
        )
    return path, index, targeted


def _receipt_identity(row: dict, index: int) -> str:
    split = row.get("split")
    _require(split is None or split in judge.PHASE1, "offline_replay_holdout_excluded")
    _require(
        type(row.get("index")) is int and row["index"] == index, "offline_replay_index"
    )
    _require(
        row.get("http_status") == 200 and row.get("status") in _REPEATABLE_STATUSES,
        "offline_replay_no_provider_response",
    )
    ident = row.get("label") if split is None else row.get("answer_id")
    if not isinstance(ident, str):
        raise ValueError("offline_replay_receipt_id")
    validate_run_id(ident)
    return ident


def _rebuild_request(request: dict, ident: str) -> tuple[dict, dict]:
    messages = request["messages"]
    _require(
        isinstance(messages, list)
        and len(messages) == 2
        and messages[0]["role"] == "system"
        and messages[1]["role"] == "user",
        "offline_replay_invalid_request",
    )
    material = json.loads(messages[1]["content"])
    _require(
        isinstance(material, dict)
        and _MATERIAL_FIELDS
        <= material.keys()
        <= (_MATERIAL_FIELDS | {"decimal_notation"}),
        "offline_replay_invalid_material",
    )
    original = {key: material[key] for key in _MATERIAL_FIELDS}
    body = judge._control_request(
        {**original, "id": ident}, {"text": material["candidate"]}
    )
    _require(
        body["messages"][1]["content"] == messages[1]["content"],
        "offline_replay_material_changed",
    )
    return material, body


def _expected_decision(expected: dict, material: dict) -> dict:
    _require(
        isinstance(expected, dict) and set(expected) == set(judge.DECISION_FIELDS),
        "offline_replay_invalid_expectation",
    )
    expect = judge.local._Decision.model_validate({**expected, "reason": ""})
    _require(
        set(expect.atoms) == {criterion["id"] for criterion in material["criteria"]},
        "offline_replay_expectation_criteria",
    )
    return expect.model_dump(exclude={"reason"})


def _replay_case(entry: dict, path: Path, index: int, targeted: dict | None) -> dict:
    row = _sealed_json(path, entry["receipt_sha256"])
    ident = _receipt_identity(row, index)
    _require(ident == entry["id"], "offline_replay_receipt_id")
    if targeted is not None:
        _require(
            row.get("split") is None
            and row.get("protocol_sha256") == targeted["protocol_sha256"]
            and ident == targeted["label"]
            and row["request"] == targeted["body"],
            "offline_replay_targeted_binding",
        )
    request, raw_response = row["request"], row["response"]
    _require(
        isinstance(request, dict) and isinstance(raw_response, dict),
        "offline_replay_invalid_receipt",
    )
    _require(
        stable_hash(request) == row.get("request_sha256")
        and stable_hash(raw_response) == row.get("response_sha256"),
        "offline_replay_receipt_payload_hash",
    )
    material, body = _rebuild_request(request, ident)
    expected = _expected_decision(entry["expected"], material)
    record = {
        "id": ident,
        "receipt": str(path),
        "receipt_sha256": entry["receipt_sha256"],
        "archived_status": row["status"],
        "archived_request_sha256": row["request_sha256"],
        "archived_response_sha256": row["response_sha256"],
        "replay_request_sha256": stable_hash(body),
        "expected": expected,
    }
    try:
        decision, evidence = judge.decode_with_evidence(
            raw_response, body, material["candidate"]
        )
    except ValueError:
        return {**record, "status": "decoder_rejected"}
    actual = decision.model_dump(exclude={"reason"})
    differences = [key for key in judge.DECISION_FIELDS if expected[key] != actual[key]]
    return {
        **record,
        "status": "mismatch" if differences else "match",
        "actual": actual,
        "differences": differences,
        "replay_evidence_sha256": stable_hash(evidence),
        "bound_fields": sorted(evidence.get("field_evidence", {})),
        "identifier_comparison_recorded": "identifier_comparison" in evidence,
    }


def replay(manifest_path: Path, manifest_sha256: str) -> dict:
    """Inspect selected archived responses without reading a qualification split."""
    manifest_path = _offline_path(manifest_path)
    manifest = _sealed_json(manifest_path, manifest_sha256)
    entries = manifest.get("cases")
    _require(
        set(manifest) == {"schema_version", "cases"}
        and type(manifest.get("schema_version")) is int
        and manifest["schema_version"] == 1
        and isinstance(entries, list)
        and bool(entries),
        "offline_replay_invalid_manifest",
    )
    assert isinstance(entries, list)
    selections = []
    seen = set()
    for entry in entries:
        _require(
            isinstance(entry, dict)
            and {"id", "receipt", "receipt_sha256", "expected"}
            <= set(entry)
            <= {
                "id",
                "receipt",
                "receipt_sha256",
                "expected",
                "targeted_protocol_sha256",
            }
            and isinstance(entry["receipt"], str)
            and bool(entry["receipt"]),
            "offline_replay_invalid_selection",
        )
        validate_run_id(entry["id"])
        path, index, targeted = _receipt_path(
            manifest_path.parent / entry["receipt"], entry
        )
        _require(path not in seen, "offline_replay_duplicate_receipt")
        seen.add(path)
        selections.append((entry, path, index, targeted))
    results = [_replay_case(*selection) for selection in selections]
    matched = sum(case["status"] == "match" for case in results)
    return {
        "schema_version": 1,
        "kind": "offline_openrouter_regression_replay",
        "status": "offline_pass" if matched == len(results) else "offline_failed",
        "manifest_sha256": manifest_sha256,
        "judge": judge.JUDGE,
        "implementation_sha256": judge.implementation_identity(),
        "request_contract_sha256": stable_hash(judge._contract()),
        "live_requests": 0,
        "valid_for_qualification": False,
        "matched": matched,
        "selected": len(results),
        "cases": results,
    }


def _publish(path: Path, result: dict) -> None:
    path = _offline_path(path)
    content = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    # Publish only a complete record and never overwrite a prior report.
    temporary = ".academy-replay-" + uuid.uuid4().hex
    with data_directory(path.parent) as directory_fd:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(
                temporary,
                path.name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        finally:
            os.unlink(temporary, dir_fd=directory_fd)
        os.fsync(directory_fd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New JSON report")
    args = parser.parse_args()
    try:
        # Resolve the destination early so that a known collision never reads inputs.
        output = _offline_path(args.output)
        _require(not output.exists(), "offline_replay_output_exists")
        result = replay(args.manifest, args.manifest_sha256)
        _publish(output, result)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {key: result[key] for key in ("status", "matched", "selected")}, indent=2
        )
    )
    if result["status"] != "offline_pass":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
