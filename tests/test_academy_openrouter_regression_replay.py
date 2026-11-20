"""Exercise local regression replay without contacting a provider."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.academy import replay_openrouter_regressions as replay
from venom_core.services.training_experiments import openrouter_semantic_judge as judge
from venom_core.services.training_experiments.profiles import digest, stable_hash

_EXPECTED = {
    "atoms": {"place": "supported"},
    "unsupported": "no",
    "injection": False,
    "polish_ok": True,
    "natural_ok": True,
}


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _record(
    tmp_path,
    index,
    *,
    observed="Hala A",
    relation="supported",
    status="completed",
    text="Hala A",
):
    case = {
        "id": "J123",
        "messages": [{"role": "user", "content": "Odbiór w hali A."}],
        "criteria": [{"id": "place", "description": "Hala A"}],
    }
    body = judge._control_request(case, {"text": text})
    body["messages"][0]["content"] = "Rubryka archiwalna"
    verdict = {
        **{
            key: value
            for key, value in _EXPECTED.items()
            if key not in ("atoms", "unsupported")
        },
        "checks": {"place": {"observed": observed, "relation": relation}},
        "additional_claims": [],
        "reason": "fixture",
    }
    response = {
        "id": f"fixture-{index}",
        "model": judge.MODEL,
        "provider": judge.PROVIDER,
        "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(verdict)}}
        ],
    }
    payload = {
        "status": status,
        "http_status": 200,
        "index": index,
        "split": "legacy",
        "answer_id": case["id"],
        "request": body,
        "request_sha256": stable_hash(body),
        "response": response,
        "response_sha256": stable_hash(response),
    }
    relative = Path("audit") / "receipts" / f"{index:03d}.json"
    path = tmp_path / relative
    _write(path, payload)
    return {
        "id": case["id"],
        "receipt": str(relative),
        "receipt_sha256": digest(path),
        "expected": _EXPECTED,
    }


def _manifest(tmp_path, *cases):
    path = tmp_path / "manifest.json"
    _write(path, {"schema_version": 1, "cases": list(cases)})
    return path, digest(path)


def test_regression_replay_preserves_archive_and_tests_all_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(
        judge.httpx, "Client", lambda **_: pytest.fail("offline replay called HTTP")
    )
    rejected = _record(tmp_path, 17, observed="tekst spoza odpowiedzi")
    mismatch = _record(tmp_path, 51, relation="contradicted")
    matched = _record(tmp_path, 98, status="failed")
    result = replay.replay(*_manifest(tmp_path, rejected, mismatch, matched))

    assert result["status"] == "offline_failed"
    assert result["live_requests"] == 0
    assert result["valid_for_qualification"] is False
    assert result["matched"] == 1
    assert [row["status"] for row in result["cases"]] == [
        "decoder_rejected",
        "mismatch",
        "match",
    ]
    assert result["cases"][1]["differences"] == ["atoms", "unsupported"]
    record = result["cases"][2]
    assert record["archived_status"] == "failed"
    assert record["archived_request_sha256"] != record["replay_request_sha256"]
    assert record["replay_evidence_sha256"] == stable_hash({})
    assert record["bound_fields"] == []
    assert record["identifier_comparison_recorded"] is False
    assert all(
        digest(tmp_path / case["receipt"]) == case["receipt_sha256"]
        for case in (rejected, mismatch, matched)
    )


@pytest.mark.parametrize(
    ("receipt_path", "reason"),
    [
        ("audit/holdout/receipts/001.json", "offline_replay_holdout_excluded"),
        ("audit/receipts/157.json", "offline_replay_non_phase1_index"),
    ],
)
def test_replay_refuses_holdout_paths_before_opening(tmp_path, receipt_path, reason):
    case = _record(tmp_path, 1)
    case["receipt"] = receipt_path
    manifest, sha = _manifest(tmp_path, case)
    with pytest.raises(ValueError, match=reason):
        replay.replay(manifest, sha)


@pytest.mark.parametrize("tampered", [False, True])
def test_replay_recomputes_archived_decimal_notation(tmp_path, tampered):
    case = _record(tmp_path, 1, text="Hala A. Masa wynosi 2,5 kg.")
    path = tmp_path / case["receipt"]
    row = json.loads(path.read_text(encoding="utf-8"))
    message = row["request"]["messages"][1]
    material = json.loads(message["content"])
    assert material["decimal_notation"]["candidate"] == "Hala A. Masa wynosi 2.5 kg."
    if tampered:
        material["decimal_notation"]["candidate"] = "Hala A. Masa wynosi 25 kg."
        message["content"] = json.dumps(material, ensure_ascii=False, sort_keys=True)
        row["request_sha256"] = stable_hash(row["request"])
        _write(path, row)
        case["receipt_sha256"] = digest(path)

    manifest = _manifest(tmp_path, case)
    if tampered:
        with pytest.raises(ValueError, match="offline_replay_material_changed"):
            replay.replay(*manifest)
    else:
        assert replay.replay(*manifest)["status"] == "offline_pass"


def test_replay_refuses_changed_receipt(tmp_path):
    case = _record(tmp_path, 1)
    path = tmp_path / case["receipt"]
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    manifest, sha = _manifest(tmp_path, case)
    with pytest.raises(ValueError, match="offline_replay_hash"):
        replay.replay(manifest, sha)


def test_cli_does_not_replace_prior_report(tmp_path, monkeypatch):
    manifest, sha = _manifest(tmp_path, _record(tmp_path, 1))
    output = tmp_path / "replay.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay",
            "--manifest",
            str(manifest),
            "--manifest-sha256",
            sha,
            "--output",
            str(output),
        ],
    )
    replay.main()
    first = output.read_bytes()
    assert json.loads(first)["status"] == "offline_pass"
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(SystemExit) as error:
        replay.main()
    assert error.value.code == 2
    assert output.read_bytes() == first


def _targeted_record(tmp_path, index=157):
    entry = _record(tmp_path, index)
    root = tmp_path / "audit"
    receipt = tmp_path / entry["receipt"]
    row = json.loads(receipt.read_text())
    labels = [f"J{number:03d}" for number in range(1, 79)] + ["J123"]
    panel = {
        "order": [label for label in labels for _ in range(2)],
        "cases": {label: {"body": row["request"]} for label in labels},
    }
    _write(root / "panel.json", panel)
    protocol = {
        "kind": "targeted_regression",
        "planned_requests": len(panel["order"]),
        "panel_sha256": digest(root / "panel.json"),
    }
    _write(root / "protocol.json", protocol)
    sha = digest(root / "protocol.json")
    row.pop("split")
    row["label"] = row.pop("answer_id")
    row["repeat"] = panel["order"][:index].count(row["label"])
    row["protocol_sha256"] = sha
    _write(receipt, row)
    entry["receipt_sha256"] = digest(receipt)
    entry["targeted_protocol_sha256"] = sha
    return entry


@pytest.mark.parametrize("index", [157, 158])
def test_replay_accepts_later_targeted_receipt_bound_to_sealed_panel(tmp_path, index):
    case = _targeted_record(tmp_path, index)
    manifest, sha = _manifest(tmp_path, case)
    result = replay.replay(manifest, sha)
    assert result["status"] == "offline_pass"
    assert result["live_requests"] == 0


@pytest.mark.parametrize("failure", ["kind", "capacity", "panel_hash", "order"])
def test_invalid_targeted_seal_is_rejected_before_receipt_read(
    tmp_path, monkeypatch, failure
):
    case = _targeted_record(tmp_path)
    root = tmp_path / "audit"
    protocol = json.loads((root / "protocol.json").read_text())
    if failure == "kind":
        protocol["kind"] = "full_audit"
    elif failure == "capacity":
        protocol["planned_requests"] = 156
    elif failure == "panel_hash":
        protocol["panel_sha256"] = "0" * 64
    else:
        panel = json.loads((root / "panel.json").read_text())
        panel["order"] = panel["order"][:-1]
        _write(root / "panel.json", panel)
        protocol["panel_sha256"] = digest(root / "panel.json")
    _write(root / "protocol.json", protocol)
    case["targeted_protocol_sha256"] = digest(root / "protocol.json")
    manifest, sha = _manifest(tmp_path, case)
    sealed = replay._sealed_json

    def read(path, expected):
        assert path.parent.name != "receipts"
        return sealed(path, expected)

    monkeypatch.setattr(replay, "_sealed_json", read)
    with pytest.raises(ValueError, match="offline_replay_"):
        replay.replay(manifest, sha)


@pytest.mark.parametrize(
    "failure", ["label", "protocol", "request", "holdout", "repeat", "boolean_repeat"]
)
def test_targeted_receipt_must_match_protocol_panel_and_order(tmp_path, failure):
    case = _targeted_record(tmp_path)
    path = tmp_path / case["receipt"]
    row = json.loads(path.read_text())
    if failure == "label":
        row["label"] = "WRONG"
    elif failure == "protocol":
        row["protocol_sha256"] = "0" * 64
    elif failure == "request":
        row["request"]["messages"][0]["content"] = "Changed"
        row["request_sha256"] = stable_hash(row["request"])
    elif failure == "repeat":
        row["repeat"] = 2
    elif failure == "boolean_repeat":
        row["repeat"] = True
    else:
        row["split"] = "holdout"
    _write(path, row)
    case["receipt_sha256"] = digest(path)
    manifest, sha = _manifest(tmp_path, case)
    with pytest.raises(ValueError, match="offline_replay_"):
        replay.replay(manifest, sha)
