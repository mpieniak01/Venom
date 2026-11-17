"""Bind independent audit calls to one runtime, session, and pre-holdout gate."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .profiles import stable_hash

if TYPE_CHECKING:
    from .local_semantic_judge import QualificationV4, QualificationV5


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("experiment_judge_v4_provenance_invalid")


def verify_legacy(
    root: Path, manifest: dict, pin: QualificationV4 | QualificationV5
) -> None:
    from . import local_semantic_judge as judge

    directory = root / "controls"
    hashes = manifest["files"]
    receipt = judge.Qualification.model_validate(
        judge._bound_json(
            directory,
            "legacy/judge-qualification-receipt.json",
            hashes["legacy/judge-qualification-receipt.json"],
        )
    )
    require(receipt.model == pin.model and receipt.model_sha256 == pin.model_sha256)
    require(receipt.ollama_version == pin.ollama_version)
    require(
        receipt.prompt_sha256 == judge.PROMPT_SHA256 and receipt.true_positives == 24
    )
    require(receipt.protocol_sha256 == hashes["legacy/judge-protocol.json"])
    require(receipt.result_sha256 == hashes["legacy/judge-result.json"])
    require(
        receipt.gold_sha256
        == pin.gold_sha256
        == hashes["legacy/qualification-gold.json"]
    )
    protocol = judge._bound_json(
        directory, "legacy/judge-protocol.json", receipt.protocol_sha256
    )
    result = judge._bound_json(
        directory, "legacy/judge-result.json", receipt.result_sha256
    )
    require(protocol["system"] == judge.PROMPT and protocol["options"] == judge.OPTIONS)
    require(
        protocol["model"] == receipt.model
        and protocol["model_sha256"] == receipt.model_sha256
    )
    require(protocol["ollama"] == {"version": receipt.ollama_version})
    require(protocol["gold_sha256"] == receipt.gold_sha256)
    require(protocol["panel_sha256"] == hashes["legacy/qualification-panel.json"])
    require(protocol["manifest_sha256"] == hashes["legacy/qualification-manifest.json"])
    require(result["protocol_sha256"] == receipt.protocol_sha256)


def _scope(value: dict, protocol: dict, protocol_sha: str) -> None:
    require(value["run_id"] == protocol["run_id"])
    require(value["protocol_sha256"] == protocol_sha)
    require(value["intent_sha256"] == protocol["intent_sha256"])


def verify_call(
    call: dict,
    protocol: dict,
    protocol_sha: str,
    seen: dict[str, set[str]],
    previous_end: int,
) -> int:
    _scope(call, protocol, protocol_sha)
    ident = call["call_id"]
    require(isinstance(ident, str) and re.fullmatch(r"[a-f0-9]{32}", ident) is not None)
    keys = (
        "started_at_ns",
        "finished_at_ns",
        "started_monotonic_ns",
        "finished_monotonic_ns",
    )
    require(all(type(call[key]) is int and call[key] > 0 for key in keys))
    require(call["started_at_ns"] <= call["finished_at_ns"])
    require(
        previous_end <= call["started_monotonic_ns"] <= call["finished_monotonic_ns"]
    )
    created = call["response"]["created_at"]
    require(isinstance(created, str))
    stamp = datetime.fromisoformat(created.replace("Z", "+00:00"))
    require(stamp.tzinfo is not None)
    server_ns = stamp.timestamp() * 1_000_000_000
    # The local Ollama clock may differ by a few seconds; replay still fails uniqueness.
    tolerance = 5_000_000_000
    require(
        call["started_at_ns"] - tolerance
        <= server_ns
        <= call["finished_at_ns"] + tolerance
    )
    identities = {
        "call_id": ident,
        "server_time": stamp.astimezone(timezone.utc).isoformat(
            timespec="microseconds"
        ),
        "raw_response": stable_hash(call["response"]),
    }
    for kind, value in identities.items():
        require(value not in seen[kind])
        seen[kind].add(value)
    return int(call["finished_monotonic_ns"])


def verify_session(
    root: Path, protocol: dict, pin: QualificationV4 | QualificationV5, result: dict
) -> None:
    from . import local_semantic_judge as judge

    intent = judge._bound_json(root, "intent.json", protocol["intent_sha256"])
    started = judge._bound_json(root, "started.json", result["started_sha256"])
    gate = judge._bound_json(root, "phase1-pass.json", result["phase1_marker_sha256"])
    require(intent["run_id"] == protocol["run_id"])
    require(intent["manifest_sha256"] == pin.accuracy_manifest_sha256)
    require(intent["implementation_sha256"] == protocol["implementation_sha256"])
    require(type(intent["seconds"]) is int and 120 < intent["seconds"] <= 1500)
    require(intent["cleanup_seconds"] == 120)
    for value in (started, gate, result):
        _scope(value, protocol, pin.protocol_sha256)
    require(result["holdout_opened"] is True and result["completed_calls"] == 180)
    require(gate["completed_calls"] == 108)
    require(gate["phase1_rows_sha256"] == stable_hash(result["rows"][:108]))
    boundary = {}
    for index in (1, 108, 109, 180):
        row = result["rows"][index - 1]
        boundary[index] = judge._bound_json(
            root / "judge-calls", f"{index:03d}.json", row["call_sha256"]
        )
    times = (
        started["started_monotonic_ns"],
        gate["closed_monotonic_ns"],
        result["finished_monotonic_ns"],
    )
    require(all(type(value) is int and value > 0 for value in times))
    require(times[0] <= boundary[1]["started_monotonic_ns"])
    require(
        boundary[108]["finished_monotonic_ns"]
        <= times[1]
        <= boundary[109]["started_monotonic_ns"]
    )
    require(boundary[180]["finished_monotonic_ns"] <= times[2])
    require(0 <= times[2] - times[0] <= intent["seconds"] * 1_000_000_000)
