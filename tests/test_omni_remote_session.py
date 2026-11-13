"""Portable Omni remote qualification inputs stay bounded and tamper evident."""

import json
from pathlib import Path

import pytest

from scripts.academy.omni_remote_session import digest, prepare, run_stage, verify


def _record(split: str) -> dict:
    row = {
        "record_id": split + "-1",
        "group_id": split + "-family",
        "split": split,
        "language": "pl",
        "messages": [
            {
                "role": "user",
                "content": "Wyjaśnij kwadrat po polsku."
                if split == "train"
                else "Ile boków ma kwadrat?",
            }
        ],
    }
    if split == "train":
        row.update(
            messages=[
                *row["messages"],
                {"role": "assistant", "content": "Kwadrat ma cztery równe boki."},
            ],
            supervision=[1],
            quality_status="accepted",
            source_repo="test/source",
            source_revision="test-revision",
            source_record_id="source-1",
            license="test-license",
            review_note="reviewed fixture",
        )
    return row


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    code = tmp_path / "code"
    pin = code / "scripts/llm/omni_native_snapshot.json"
    pin.parent.mkdir(parents=True)
    pin.write_text(json.dumps({"repo": "LiquidAI/LFM3-Omni-2B", "revision": "a" * 40}))
    train = tmp_path / "train.jsonl"
    dev = tmp_path / "dev.jsonl"
    for path, split in ((train, "train"), (dev, "dev")):
        path.write_text(json.dumps(_record(split), ensure_ascii=False) + "\n")
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "train": str(train),
                "dev": str(dev),
                "train_sha256": digest(train),
                "dev_sha256": digest(dev),
                "model": "LiquidAI/LFM3-Omni-2B",
                "recipe": {"steps": 128, "save_every": 32},
            }
        )
    )
    return profile, code


def test_prepare_and_verify_freeze_only_train_dev_and_smoke(tmp_path, monkeypatch):
    profile, code = _fixture(tmp_path)
    monkeypatch.setattr(
        "scripts.academy.omni_remote_session._commit", lambda _: "b" * 40
    )
    bundle = tmp_path / "bundle"
    prepared = prepare(profile, bundle, code)
    assert prepared == verify(bundle)
    assert prepared["train_records"] == prepared["dev_records"] == 1
    assert prepared["excluded"] == [
        "model_weights",
        "credentials",
        "holdout",
        "historical_set_B",
    ]
    assert json.loads((bundle / "smoke-recipe.json").read_text())["steps"] == 16


def test_verify_rejects_tampering_and_extra_files(tmp_path, monkeypatch):
    profile, code = _fixture(tmp_path)
    monkeypatch.setattr(
        "scripts.academy.omni_remote_session._commit", lambda _: "b" * 40
    )
    bundle = tmp_path / "bundle"
    prepare(profile, bundle, code)
    (bundle / "holdout.jsonl").write_text("forbidden")
    with pytest.raises(ValueError, match="structure"):
        verify(bundle)
    (bundle / "holdout.jsonl").unlink()
    (bundle / "train.jsonl").write_text("altered")
    with pytest.raises(ValueError, match="differs"):
        verify(bundle)


def test_prepare_rejects_reserved_source_and_wrong_hash(tmp_path, monkeypatch):
    profile, code = _fixture(tmp_path)
    monkeypatch.setattr(
        "scripts.academy.omni_remote_session._commit", lambda _: "b" * 40
    )
    value = json.loads(profile.read_text())
    value["train_sha256"] = "0" * 64
    profile.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="hashes"):
        prepare(profile, tmp_path / "bundle", code)
    assert not (tmp_path / "bundle").exists()
    value["train_sha256"] = digest(Path(value["train"]))
    reserved = tmp_path / "holdout"
    reserved.mkdir()
    new_train = reserved / "train.jsonl"
    new_train.write_bytes(Path(value["train"]).read_bytes())
    value["train"] = str(new_train)
    profile.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="reserved evaluation"):
        prepare(profile, tmp_path / "bundle", code)


def test_remote_stage_requires_matching_checkout_and_preflight(tmp_path, monkeypatch):
    profile, code = _fixture(tmp_path)
    monkeypatch.setattr(
        "scripts.academy.omni_remote_session._commit", lambda _: "b" * 40
    )
    monkeypatch.setattr(
        "scripts.academy.omni_remote_session._clean_checkout", lambda _: None
    )
    bundle = tmp_path / "bundle"
    prepare(profile, bundle, code)
    assert verify(bundle, code)["source_commit"] == "b" * 40
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin/python").write_text("")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="preflight"):
        run_stage(bundle, code, snapshot, venv, output, "smoke")
    calls = []
    monkeypatch.setattr(
        "scripts.academy.omni_remote_session.subprocess.run",
        lambda argv, **kwargs: calls.append(argv),
    )
    run_stage(bundle, code, snapshot, venv, output, "preflight")
    assert calls[0][-2:] == ["preflight", str(bundle / "smoke-recipe.json")]
    monkeypatch.setattr(
        "scripts.academy.omni_remote_session._commit", lambda _: "c" * 40
    )
    with pytest.raises(ValueError, match="reviewed checkout"):
        verify(bundle, code)
