"""Integrity tests for the blinded conversation-review package."""

import json
import os
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.academy.omni_pl_chat_dialogue import DialogueHistory, blind_answer
from scripts.academy.omni_pl_chat_dialogue import digest as history_digest
from scripts.academy.omni_pl_chat_evaluate import blind_mapping
from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN
from venom_core.services.training_experiments.checkpoint_evaluation import (
    seal_generation,
)
from venom_core.services.training_experiments.conversation_blind import (
    prepare_blind_package,
    publish_blind_package,
    register_blind_review,
)
from venom_core.services.training_experiments.conversation_review import payload_sha
from venom_core.services.training_experiments.profiles import (
    MODEL,
    digest,
    read_json,
    stable_hash,
)


def _write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


def _generation(path, cases, dataset_hash, identity, step, *, cutoffs=()):
    path.mkdir()
    tag = f"checkpoint-{step}"
    models = {
        "base": {"base": True},
        tag: {
            "adapter_config.json": identity["config_sha256"],
            "adapter_model.safetensors": identity["weights_sha256"],
        },
    }
    mapping = blind_mapping(cases, list(models))
    raw, blind = [], []
    histories = {model: DialogueHistory() for model in models}
    for case in cases:
        answers = {}
        for label, model in mapping[case["record_id"]].items():
            history = histories[model]
            context = history.context(case)
            row = {
                "case": case["record_id"],
                "model": model,
                "label": label,
                "response": {
                    "text": f"Answer {model}",
                    "finish": "length"
                    if model == tag and case["record_id"] in cutoffs
                    else "stop",
                    "error": None,
                },
                **context,
            }
            history.remember(case, row, context)
            raw.append(row)
            answers[label] = blind_answer(row)
        blind.append({"case": case, "answers": answers})
    for name, rows in (("raw.jsonl", raw), ("blind.jsonl", blind)):
        (path / name).write_text("".join(json.dumps(row) + "\n" for row in rows))
    _write(path / "unblind.json", mapping)
    _write(
        path / "manifest.json",
        {
            "models": models,
            "model_repo": identity["model"],
            "snapshot_manifest_sha256": identity["snapshot_sha256"],
            "data_sha256": dataset_hash,
            "evaluated_ids": [case["record_id"] for case in cases],
            "revision": "fixture",
            "max_prompt_tokens": 4096,
            "max_new_tokens": 512,
            "seed": 42,
            "engine": {"torch": "fixture"},
            "template": "vendor",
            "generation_mode": "text",
            "do_sample": False,
            "enable_thinking": False,
            "case_max_new_tokens": {case["record_id"]: 512 for case in cases},
            "dialogue_protocol": "own-history-v1",
            "outputs": {
                name: digest(path / name)
                for name in ("raw.jsonl", "blind.jsonl", "unblind.json")
            },
        },
    )
    seal_generation(path)
    return read_json(path / "generation-seal.json")


@pytest.fixture
def input_data(tmp_path):
    panel, cases = {}, []
    for i in range(96):
        conversation, group = f"C{i:03}", "SKWR"[i % 4]
        panel[conversation] = {
            "group": group,
            "turns": {f"T{j}": ["content"] for j in range(1, 5)},
        }
        for turn in range(1, 5):
            cases.append(
                {
                    "record_id": f"{conversation}-{turn}",
                    "group_id": conversation,
                    "review_group": group,
                    "task": group,
                    "split": "dev",
                    "dialogue": {"id": conversation, "turn_index": turn},
                    "messages": [{"role": "user", "content": f"Question {turn}"}],
                    "criteria": [
                        {"id": "content", "kind": "content", "description": "Answer"}
                    ],
                }
            )
    dataset = tmp_path / "data.jsonl"
    dataset.write_text("".join(json.dumps(row) + "\n" for row in cases))
    parent = {
        "model": MODEL,
        "weights_sha256": "a" * 64,
        "config_sha256": sha256(b"{}").hexdigest(),
        "snapshot_sha256": digest(SNAPSHOT_PIN),
    }
    candidate = {**parent, "weights_sha256": sha256(b"candidate").hexdigest()}
    pdir, cdir = tmp_path / "parent", tmp_path / "candidate"
    pseal = _generation(pdir, cases, digest(dataset), parent, 145)
    _generation(cdir, cases, digest(dataset), candidate, 21)
    _write(
        cdir / "result.json",
        {
            "run_id": "run",
            "checkpoint": {"step": 21, "sha256": candidate["weights_sha256"]},
            "generation_sha256": digest(cdir / "generation-seal.json"),
        },
    )
    binding = {
        "campaign_id": "campaign-01",
        "panel_sha256": payload_sha(panel),
        "development_identity": {"dataset_sha256": digest(dataset)},
        "p13_identity": parent,
        "candidate_identity": candidate,
        "p13_record_sha256": stable_hash(pseal),
        "checkpoint_result_sha256": digest(cdir / "result.json"),
        "run_id": "run",
        "step": 21,
    }
    pending = {
        "conversation_review_status": "pending",
        "conversation_review_id": "review-01",
        "conversation_review_binding": binding,
    }
    return pending, panel, dataset, pdir, cdir


def test_blind_package_binds_sealed_own_history(input_data):
    package, private = prepare_blind_package(*input_data)
    assert len(package["conversations"]) == 96
    assert set(package["conversations"]["C000"]["turns"]["T1"]["answers"]) == {"A", "B"}
    assert "p13" not in json.dumps(package)
    assert private["package_sha256"] == stable_hash(package)
    assert sorted(private["aliases"]["C000"].values()) == ["candidate", "p13"]


@pytest.mark.parametrize(
    "damage",
    [
        "panel",
        "dataset",
        "missing_turn",
        "duplicate_turn",
        "parent",
        "candidate",
        "result",
    ],
)
def test_blind_package_rejects_changed_evidence(input_data, damage):
    pending, panel, dataset, parent, candidate = input_data
    if damage == "panel":
        panel["C000"]["turns"]["T1"] = ["other"]
    elif damage == "dataset":
        dataset.write_text(dataset.read_text() + " ")
    elif damage in {"missing_turn", "duplicate_turn"}:
        rows = dataset.read_text().splitlines()
        if damage == "missing_turn":
            rows.pop()
        else:
            rows.append(rows[0])
        dataset.write_text("\n".join(rows) + "\n")
        pending["conversation_review_binding"]["development_identity"][
            "dataset_sha256"
        ] = digest(dataset)
        with pytest.raises(ValueError, match="panel_mapping_invalid"):
            prepare_blind_package(pending, panel, dataset, parent, candidate)
        return
    elif damage == "parent":
        (parent / "raw.jsonl").write_text("{}")
    elif damage == "candidate":
        (candidate / "blind.jsonl").write_text("{}")
    else:
        (candidate / "result.json").write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        prepare_blind_package(pending, panel, dataset, parent, candidate)


def test_cli_publishes_only_anonymous_review_and_private_mapping(
    input_data, tmp_path, capsys
):
    from scripts.academy.conversation_blind import main

    pending, panel, dataset, parent, candidate = input_data
    pending_path, panel_path = tmp_path / "pending.json", tmp_path / "panel.json"
    _write(pending_path, pending)
    _write(panel_path, panel)
    output = tmp_path / "package"
    args = [
        "--pending",
        str(pending_path),
        "--panel",
        str(panel_path),
        "--dataset",
        str(dataset),
        "--parent",
        str(parent),
        "--candidate",
        str(candidate),
        "--output",
        str(output),
    ]
    main(args)
    review, private = (
        read_json(output / "reviewer.json"),
        read_json(output / "private.json"),
    )
    assert private["package_sha256"] == stable_hash(review)
    assert "aliases" not in json.dumps(review)
    assert "Question 1" in json.dumps(review)
    template = read_json(output / "judgments-template.json")
    assert template["package_sha256"] == private["package_sha256"]
    assert template["judgments"]["C000"]["T1"]["A"]["critical"] is None
    turn = review["conversations"]["C000"]["turns"]["T1"]
    assert turn["criterion_descriptions"] == {"content": "Answer"}
    assert set(turn["answers"]["A"]) == {"text", "input_messages"}
    assert "candidate" not in capsys.readouterr().out
    assert (output.stat().st_mode & 0o777) == 0o700
    before = (output / "reviewer.json").read_bytes()
    with pytest.raises(SystemExit):
        main(args)
    assert (output / "reviewer.json").read_bytes() == before


def test_blind_package_rejects_different_generation_protocol(input_data):
    pending, panel, dataset, parent, candidate = input_data
    manifest_path = parent / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["seed"] = 17
    _write(manifest_path, manifest)
    seal_generation(parent)
    pending["conversation_review_binding"]["p13_record_sha256"] = stable_hash(
        read_json(parent / "generation-seal.json")
    )
    with pytest.raises(ValueError, match="generation_protocol_mismatch"):
        prepare_blind_package(pending, panel, dataset, parent, candidate)


def test_blind_package_rejects_non_object_pending(input_data):
    with pytest.raises(
        ValueError, match="conversation_review_pending_checkpoint_required"
    ):
        prepare_blind_package([], *input_data[1:])


def test_blind_package_rejects_different_history_after_resealing(input_data):
    pending, panel, dataset, parent, candidate = input_data
    raw_path = candidate / "raw.jsonl"
    rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
    row = next(
        row
        for row in rows
        if row["case"] == "C000-2" and row["model"] == "checkpoint-21"
    )
    row["input_messages"][0]["content"] = "Different history"
    row["history_sha256"] = history_digest(row["input_messages"])
    blind_path = candidate / "blind.jsonl"
    blind = [json.loads(line) for line in blind_path.read_text().splitlines()]
    matching = next(item for item in blind if item["case"]["record_id"] == row["case"])
    matching["answers"][row["label"]] = blind_answer(row)
    manifest_path = candidate / "manifest.json"
    manifest = read_json(manifest_path)
    for path, records in ((raw_path, rows), (blind_path, blind)):
        path.write_text("".join(json.dumps(record) + "\n" for record in records))
        manifest["outputs"][path.name] = digest(path)
    _write(manifest_path, manifest)
    seal_generation(candidate)
    result_path = candidate / "result.json"
    result = read_json(result_path)
    result["generation_sha256"] = digest(candidate / "generation-seal.json")
    _write(result_path, result)
    pending["conversation_review_binding"]["checkpoint_result_sha256"] = digest(
        result_path
    )
    with pytest.raises(ValueError, match="dialogue receipt history differs"):
        prepare_blind_package(pending, panel, dataset, parent, candidate)


@pytest.fixture
def issued_review(input_data, tmp_path):
    pending = input_data[0]
    package, private = prepare_blind_package(*input_data)
    output = publish_blind_package(tmp_path / "package", package, private)
    template = read_json(output / "judgments-template.json")
    template.update(reviewer_id="operator", reviewer_note="Ocena całego panelu.")
    return pending, output, template, private


def _fill_review(submission):
    for turns in submission["judgments"].values():
        for arms in turns.values():
            for verdict in arms.values():
                verdict.update(criteria={"content": True}, critical=False)


def _store_checkpoint(experiments, dataset, generation, binding):
    from scripts.academy.omni_pl_chat_p1 import CHECKPOINT_FILES
    from venom_core.services.training_experiments.checkpoint_evaluation import (
        step_directory,
    )
    from venom_core.services.training_experiments.evidence import sealed_report

    run_id, step = binding["run_id"], binding["step"]
    run = experiments.run_dir(run_id)
    folder = step_directory(run, step)
    folder.parent.mkdir(parents=True)
    generation.rename(folder)
    checkpoint = run / "training" / f"checkpoint-{step}"
    checkpoint.mkdir(parents=True)
    for name in CHECKPOINT_FILES:
        (checkpoint / name).write_bytes(
            b"candidate" if name == "adapter_model.safetensors" else b"{}"
        )
    _write(
        checkpoint / "hashes.json",
        {name: digest(checkpoint / name) for name in CHECKPOINT_FILES},
    )
    manifest = {
        "profile": {
            "model": binding["candidate_identity"]["model"],
            "label": "Offline integration",
            "dataset": "Synthetic panel",
            "snapshot": "snapshot",
            "training_venv": "training-venv",
            "train": "train.jsonl",
            "train_sha256": "e" * 64,
            "dev": dataset.name,
            "dev_sha256": digest(dataset),
        },
        "recipe": {"rank": 4},
        "calibration": None,
    }
    profile_path = experiments.root / "profiles" / "fixture.json"
    profile_path.parent.mkdir()
    _write(profile_path, manifest["profile"])
    _write(run / "manifest.json", manifest)
    _write(run / "state.json", {"status": "succeeded", "checkpoint_steps": [step]})
    mapping = read_json(folder / "unblind.json")
    grades = [
        {
            "record_id": case,
            "label": label,
            "criteria": {"content": variant != "base"},
            "natural_ok": True,
            "polish_ok": True,
            "critical_error": False,
            "reason": "Synthetic offline verdict.",
        }
        for case, variants in mapping.items()
        for label, variant in variants.items()
    ]
    _write(folder / "judgments.json", grades)
    report = read_json(folder / "result.json")
    report.update(
        sealed_report(folder, dataset, grades, report["checkpoint"]),
        artifacts=[report["checkpoint"]],
        dev_sha256=digest(dataset),
        manifest_sha256=stable_hash(manifest),
        judgment_sha256=digest(folder / "judgments.json"),
    )
    _write(folder / "result.json", report)
    _write(
        folder / "result-seal.json", {"result_sha256": digest(folder / "result.json")}
    )
    return folder


@pytest.mark.parametrize(
    ("scenario", "remote", "extension"),
    [
        (scenario, remote, False)
        for scenario in ("gain", "regression", "tie")
        for remote in (False, True)
    ]
    + [
        (scenario, remote, True)
        for scenario in ("expired", "stopped")
        for remote in (False, True)
    ]
    + [(scenario, False, True) for scenario in ("gain", "regression")],
)
def test_blind_review_controls_restarted_campaign(
    input_data, tmp_path, capsys, monkeypatch, scenario, remote, extension
):
    from scripts.academy import campaigns as campaign_cli
    from scripts.academy.quality import main as quality_cli
    from venom_core.services.training_experiments import quality_guard, quality_native
    from venom_core.services.training_experiments.campaign import CampaignService, _rank
    from venom_core.services.training_experiments.campaign_schema import (
        CampaignQualityPolicy,
    )
    from venom_core.services.training_experiments.local_campaign_final import transition
    from venom_core.services.training_experiments.quality import QualityStore
    from venom_core.services.training_experiments.service import ExperimentService

    fixture, panel, dataset, parent, source = input_data
    binding = fixture["conversation_review_binding"]
    campaign_id, run_id, step = (
        binding[key] for key in ("campaign_id", "run_id", "step")
    )
    experiments = ExperimentService(tmp_path)
    generation = _store_checkpoint(experiments, dataset, source, binding)
    record = quality_native.native_record(experiments, run_id, step)
    parent_id = "history:parent"
    parent_failed = set(list(panel)[-8:]) if scenario != "tie" else set()
    parent_record = {
        "record_id": "parent",
        "split": "dev",
        "identity": record["identity"],
        "source": {"identity": "parent-145", "sha256": binding["p13_record_sha256"]},
        "candidate_sha256": binding["p13_identity"]["weights_sha256"],
        "candidate_config_sha256": binding["p13_identity"]["config_sha256"],
        "cases": {
            key: {
                **case,
                "candidate": {
                    "usable": key.split("-", 1)[0] not in parent_failed,
                    "passed": key.split("-", 1)[0] not in parent_failed,
                    "critical": False,
                },
            }
            for key, case in record["cases"].items()
        },
    }
    QualityStore(tmp_path).import_record(parent_record)
    context = quality_native.profile_context(experiments, "fixture", "automatic")
    context["initial_adapter_sha256"] = parent_record["candidate_sha256"]
    settings = CampaignQualityPolicy(
        reference_record_ids=[parent_id],
        parent_reference_record_id=parent_id,
        protect_parent_full_pass=True,
    )
    policy = quality_guard.freeze_policy(
        settings.model_dump(mode="json"),
        context,
        lambda key: quality_native.get_record(experiments, key),
    )
    plan = {
        "campaign_id": campaign_id,
        "plan_sha256": "3" * 64,
        "profile_identity": "4" * 64,
        "profile_id": "fixture",
        "review_mode": "automatic",
        "checkpoint_evaluation_identity": record["identity"],
        "checkpoint_steps": [step],
        "selection": {
            "min_usable_delta": 0.05,
            "max_critical_delta": 0,
            "protect_parent_full_pass": True,
        },
        "quality_policy": policy,
        "final_qualification": {"inputs_id": "final", "reserve_seconds": 30},
        "conversation_review": {
            "panel_sha256": payload_sha(panel),
            "receipt_id_prefix": "review-0a",
        },
        "variants": [{"run_id": run_id, "initial_adapter": binding["p13_identity"]}],
    }
    trial = {"run_id": run_id, "status": "succeeded"}
    state = {
        "campaign_id": campaign_id,
        "plan": plan,
        "status": "succeeded",
        "phase": "trials",
        "started_at": None,
        "elapsed_seconds": 0,
        "worker": None,
        "termination": None,
        "trials": [trial],
    }
    now = [1000.0]
    service = CampaignService(experiments, clock=lambda: now[0])
    plan["budget"] = {"max_seconds": 600, "trial_seconds": 120}
    state.update(started_at=900.0, deadline_at=1400.0, trial_index=1)
    repeat_id = f"{run_id}-repeat"
    if extension:
        state["status"] = "running"
        state["trials"].append({"run_id": repeat_id, "status": "pending"})
        plan["extension"] = {
            "initial_trials": 1,
            "min_usable_delta": 0.05,
            "repeat_best_recipe": True,
            "repeat_variants": {run_id: repeat_id},
        }
    if remote:
        from venom_core.services.remote_training.lifecycle import process_identity
        from venom_core.services.training_experiments.profiles import load_profile

        plan["conversation_review"]["final_mode"] = "remote"
        plan["profile_identity"] = load_profile(tmp_path, "fixture")[1]
        plan.pop("final_qualification")
        state.update(
            started_at=900.0, cutoff_at=1400.0, worker=process_identity(os.getpid())
        )
        state.pop("phase")
        state.pop("deadline_at")
    service._record_checkpoint_results(state, trial, policy)
    (pending,) = trial["checkpoint_evaluations"]
    assert pending["conversation_review_status"] == "pending"
    assert pending["conversation_review_binding"]["run_id"] == run_id
    assert pending["conversation_review_binding"]["step"] == step
    _rank(state)
    if not extension:
        if remote:
            assert service._pause_conversation_review(state)
        else:
            transition(state)
    directory = service.directory(campaign_id)
    directory.mkdir(parents=True)
    service._save(directory, state)
    if extension:
        paused = service.advance(campaign_id)
        assert paused["status"] == "awaiting_review"
        assert paused["training_status"] == "running"
        assert "extension_decision" not in paused
        assert paused["trials"][1]["status"] == "pending"

    pending_file, judgments = tmp_path / "pending.json", tmp_path / "submission.json"
    if remote:
        panel_file = tmp_path / "panel.json"
        _write(panel_file, panel)
        from venom_core.services.training_experiments.remote_conversation_review import (
            prepare,
        )

        issued = prepare(service, campaign_id, run_id, step, panel_file, parent)
        assert issued == prepare(service, campaign_id, run_id, step, panel_file, parent)
        output = Path(issued["reviewer"]).parent
        if scenario == "stopped":
            template_path = output / "judgments-template.json"
            template = template_path.read_bytes()
            template_path.unlink()
            with pytest.raises(
                ValueError, match="conversation_review_judgments_template_missing"
            ):
                prepare(service, campaign_id, run_id, step, panel_file, parent)
            template_path.write_bytes(template)
        private = read_json(output / "private.json")
        monkeypatch.setattr(campaign_cli, "CampaignService", lambda _: service)
        main = campaign_cli.main
        args = [
            "--root",
            str(tmp_path),
            "submit-remote-review",
            campaign_id,
            run_id,
            str(step),
            str(judgments),
        ]
    else:
        package, private = prepare_blind_package(
            pending, panel, dataset, parent, generation
        )
        output = publish_blind_package(tmp_path / "package", package, private)
        _write(pending_file, pending)
        main = quality_cli
        args = [
            "--root",
            str(tmp_path),
            "register-blind-review",
            str(pending_file),
            str(output),
            str(judgments),
        ]
    submitted = read_json(output / "judgments-template.json")
    submitted.update(reviewer_id="operator", reviewer_note="Synthetic offline review.")

    _write(judgments, submitted)
    with pytest.raises(SystemExit, match="1"):
        main(args)
    assert service.advance(campaign_id)["status"] == "awaiting_review"
    if scenario in {"expired", "stopped"}:
        if scenario == "expired":
            now[0] = 1400.0 if remote else 1370.0
        else:
            state = service._state(directory)
            state.update(status="stopping", termination="stopped")
            service._save(directory, state)
        closed = service.advance(campaign_id)
        assert closed["status"] == ("timed_out" if scenario == "expired" else "stopped")
        assert closed["selected_run_id"] is None
        _fill_review(submitted)
        _write(judgments, submitted)
        if remote:
            capsys.readouterr()
            with pytest.raises(SystemExit, match="1"):
                main(args)
            assert "campaign_remote_review_unavailable" in capsys.readouterr().err
            assert not (directory / "conversation-reviews").exists()
        else:
            assert closed["qualification_status"] == "incomplete"
            assert closed["phase"] == "complete"
            main(args)
            assert service.status(campaign_id)["selected_run_id"] is None
        return
    _fill_review(submitted)
    for name in parent_failed:
        alias = next(
            alias for alias, role in private["aliases"][name].items() if role == "p13"
        )
        for turn in submitted["judgments"][name].values():
            turn[alias]["criteria"]["content"] = False
    if scenario == "regression":
        aliases = private["aliases"]["C000"]
        alias = next(alias for alias, role in aliases.items() if role == "candidate")
        submitted["judgments"]["C000"]["T1"][alias]["criteria"]["content"] = False
    _write(judgments, submitted)
    main(args)
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == ("STOP" if scenario == "regression" else "PASS")
    reviews = directory / "conversation-reviews"
    receipt_path = reviews / receipt["review_id"] / "receipt.json"
    before = receipt_path.stat().st_mtime_ns
    main(args)
    assert json.loads(capsys.readouterr().out) == receipt
    assert list(reviews.glob("*/receipt.json")) == [receipt_path]
    assert receipt_path.stat().st_mtime_ns == before

    restarted = CampaignService(ExperimentService(tmp_path), clock=lambda: now[0])
    resumed = restarted.advance(campaign_id)
    (outcome,) = resumed["trials"][0]["checkpoint_evaluations"]
    assert outcome["conversation_review_sha256"] == stable_hash(receipt)
    if extension:
        assert resumed["status"] == "running"
        assert resumed["qualification_status"] == "pending"
        assert "extension_decision" not in resumed
        prepared = []
        monkeypatch.setattr(restarted, "_run", lambda *_: None)
        monkeypatch.setattr(
            restarted,
            "_prepare_trial",
            lambda _directory, _state, trial: prepared.append(trial["run_id"]),
        )
        decided = restarted.advance(campaign_id)
        assert decided.get("error") is None, decided.get("error")
        assert prepared == ([repeat_id] if scenario == "gain" else [])
        assert decided["extension_decision"]["status"] == (
            "approved" if scenario == "gain" else "skipped"
        )
        if scenario == "regression":
            assert decided["qualification_status"] == "failed_quality"
            assert decided["selected_run_id"] is None
        return

    if scenario != "gain":
        assert resumed["selected_run_id"] is None
        if remote:
            assert resumed["status"] == "succeeded"
        else:
            assert resumed["qualification_status"] == "failed_quality"
        assert restarted.advance(campaign_id) == resumed
        if scenario == "regression":
            assert receipt["passed"] > receipt["p13_passed"]
            assert receipt["failures"] == ["parent_conversation_lost"]
        else:
            assert outcome["quality_guard"]["parent_delta"]["usable_delta"] == 0
        return

    assert resumed["selected_run_id"] == run_id
    assert resumed["selected_checkpoint_step"] == step
    if remote:
        assert resumed["status"] == "succeeded"
        assert resumed.get("phase") is None
    else:
        assert resumed["phase"] == "qualification"
    assert receipt["passed"] > receipt["p13_passed"]
    _write(receipt_path, {**receipt, "reviewer_note": "Changed after PASS."})
    blocked = (
        restarted.status(campaign_id) if remote else restarted.advance(campaign_id)
    )
    assert blocked["status"] == "blocked"
    assert blocked["selected_run_id"] is None
    assert blocked["error"] == "campaign_quality_conversation_review_changed"
    assert blocked.get("qualification_attempts", 0) == 0
    assert not (tmp_path / "local-text-qualification").exists()


@pytest.mark.parametrize("critical", [False, True])
def test_cli_registers_blind_verdict_with_original_aliases(
    issued_review, tmp_path, capsys, critical
):
    from scripts.academy.quality import main

    pending, output, submitted, private = issued_review
    _fill_review(submitted)
    alias = next(
        alias for alias, arm in private["aliases"]["C000"].items() if arm == "candidate"
    )
    submitted["judgments"]["C000"]["T2"][alias]["critical"] = critical
    pending_file, judgments_file = (
        tmp_path / "pending.json",
        tmp_path / "judgments.json",
    )
    _write(pending_file, pending)
    _write(judgments_file, submitted)
    root = tmp_path / "experiments"
    args = [
        "--root",
        str(root),
        "register-blind-review",
        str(pending_file),
        str(output),
        str(judgments_file),
    ]
    main(args)
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == ("STOP" if critical else "PASS")
    assert receipt["critical"] == (["C000/T2"] if critical else [])
    assert receipt["lost"] == (["C000"] if critical else [])
    assert len(receipt["blind_review_sha256"]) == 64
    main(args)
    assert json.loads(capsys.readouterr().out) == receipt
    submitted["reviewer_note"] = "Inna ocena."
    with pytest.raises(ValueError, match="immutable_conflict"):
        register_blind_review(root, pending, output, submitted)


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("blank", "verdict_invalid"),
        ("missing", "blind_coverage_invalid"),
        ("other_package", "blind_submission_invalid"),
        ("alias_swap", "blind_package_mismatch"),
        ("reviewer_edit", "blind_package_mismatch"),
        ("other_checkpoint", "blind_package_mismatch"),
    ],
)
def test_blind_import_rejects_incomplete_or_unbound_review(
    issued_review, tmp_path, change, error
):
    pending, output, submitted, private = issued_review
    if change != "blank":
        _fill_review(submitted)
    if change == "missing":
        del submitted["judgments"]["C000"]["T3"]["B"]
    elif change == "other_package":
        submitted["package_sha256"] = "0" * 64
    elif change == "alias_swap":
        arms = private["aliases"]["C000"]
        arms["A"], arms["B"] = arms["B"], arms["A"]
        _write(output / "private.json", private)
    elif change == "reviewer_edit":
        package = read_json(output / "reviewer.json")
        package["conversations"]["C000"]["turns"]["T2"]["answers"]["A"]["text"] = (
            "changed"
        )
        _write(output / "reviewer.json", package)
    elif change == "other_checkpoint":
        pending["conversation_review_binding"]["step"] = 22
    root = tmp_path / "experiments"
    with pytest.raises(ValueError, match=error):
        register_blind_review(root, pending, output, submitted)
    assert not root.exists()


@pytest.mark.parametrize("cutoffs", [False, True])
def test_blind_diagnostic_scores_without_campaign_receipt(
    input_data, tmp_path, capsys, cutoffs
):
    from scripts.academy.conversation_diagnostic import main

    pending, panel, dataset, parent, candidate = input_data
    run = tmp_path / "diagnostic"
    pair_dir = run / "checkpoint-evaluations"
    pair_dir.mkdir(parents=True)
    entries = {}
    binding = pending["conversation_review_binding"]
    if cutoffs:
        from scripts.academy.omni_pl_chat_data import read_jsonl

        candidate = tmp_path / "cutoff-source"
        _generation(
            candidate,
            read_jsonl(dataset),
            digest(dataset),
            binding["candidate_identity"],
            21,
            cutoffs={f"C{number:03}-1" for number in range(2, 35, 4)} | {"C002-2"},
        )
    for name, step, source, identity in (
        ("parent", 145, parent, binding["p13_identity"]),
        ("candidate", 21, candidate, binding["candidate_identity"]),
    ):
        target = pair_dir / str(step)
        source.rename(target)
        entries[name] = {
            "step": step,
            "path": f"checkpoint-evaluations/{step}",
            "identity": identity,
            "generation_seal_sha256": digest(target / "generation-seal.json"),
        }
    manifest = {
        "schema_version": 1,
        "status": "complete",
        "panel_sha256": payload_sha(panel),
        "dataset_sha256": digest(dataset),
        "conversations": 96,
        "turns": 384,
        **entries,
    }
    _write(run / "generation-acceptance.json", manifest)
    panel_path = tmp_path / "panel.json"
    _write(panel_path, panel)
    ceiling_args = ["cutoff-ceiling", str(run), str(panel_path), str(dataset)]
    main(ceiling_args)
    ceiling = json.loads(capsys.readouterr().out)
    assert ceiling["status"] == ("STOP" if cutoffs else "REVIEW")
    assert ceiling["failed_groups"] == (["W"] if cutoffs else [])
    assert ceiling["fails_total"] is False
    assert ceiling["arms"]["candidate"]["maximum_full_conversations"] == (
        87 if cutoffs else 96
    )
    assert ceiling["arms"]["candidate"]["cutoff_turns"] == (10 if cutoffs else 0)
    assert ceiling["arms"]["p13"]["maximum_full_conversations"] == 96
    assert ceiling["parent_retention_assessed"] is False
    assert not list(tmp_path.rglob("receipt.json"))

    if cutoffs:
        (pair_dir / "21" / "raw.jsonl").write_text("{}")
        with pytest.raises(SystemExit):
            main(ceiling_args)
        assert "experiment_evidence_changed" in capsys.readouterr().err
        return

    output = tmp_path / "diagnostic-package"
    main(["prepare", str(run), str(panel_path), str(dataset), str(output)])
    capsys.readouterr()
    submitted = read_json(output / "judgments-template.json")
    submitted.update(reviewer_id="operator", reviewer_note="Diagnostic review")
    _fill_review(submitted)
    submitted_path = tmp_path / "judgments.json"
    _write(submitted_path, submitted)
    args = ["score", str(run), str(output), str(submitted_path)]
    main(args)
    result = json.loads(capsys.readouterr().out)
    assert result["scope"] == "diagnostic_only"
    assert result["status"] == "PASS"
    assert result["conversations"] == 96
    assert not list(tmp_path.rglob("receipt.json"))

    (pair_dir / "21" / "raw.jsonl").write_text("{}")
    with pytest.raises(SystemExit):
        main(args)
    assert "experiment_evidence_changed" in capsys.readouterr().err


def test_generation_runner_records_full_dev_and_reuses_sealed_evidence(
    input_data, tmp_path
):
    from argparse import Namespace
    from pathlib import Path

    from scripts.academy.conversation_generate import generate_panel
    from scripts.academy.omni_pl_chat_data import read_jsonl, write_jsonl
    from scripts.academy.omni_pl_chat_masks import SNAPSHOT_PIN

    _, panel, old_dataset, _, _ = input_data
    panel_path = tmp_path / "panel.json"
    _write(panel_path, panel)
    cases = read_jsonl(old_dataset)
    for case in cases:
        case.update(split="dev", language="pl", task="coverage")
    dataset = tmp_path / "dev.jsonl"
    write_jsonl(dataset, cases)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin/python").touch()

    def adapter(name):
        path = tmp_path / name
        path.mkdir()
        (path / "adapter_config.json").write_text("{}")
        (path / "adapter_model.safetensors").write_text(name)
        hashes = {file.name: digest(file) for file in path.iterdir()}
        _write(path / "hashes.json", hashes)
        return path, hashes

    parent, parent_hashes = adapter("p13")
    candidate, candidate_hashes = adapter("candidate-weights")
    output = tmp_path / "output"
    args = Namespace(
        panel=panel_path,
        dataset=dataset,
        snapshot=snapshot,
        venv=venv,
        parent=parent,
        parent_step=145,
        candidate=candidate,
        candidate_step=21,
        output=output,
        max_seconds=144,
        dedicated_runtime=True,
    )
    attempts = []

    def fake_evaluator(command, log, timeout, run_id, model, *, shared_runtime):
        stage = Path(command[8])
        assert command[10:12] == ["--resume-partial", "base"]
        assert log.parent == output
        assert timeout == 144
        assert not shared_runtime
        attempts.append((run_id, stage))
        stage.mkdir()
        if len(attempts) == 1:
            raise TimeoutError("fixture interruption")

        models = {
            "base": {"base": True},
            "checkpoint-145": parent_hashes,
            "checkpoint-21": candidate_hashes,
        }
        mapping = blind_mapping(cases, list(models))
        raw, blind = [], []
        histories = {tag: DialogueHistory() for tag in models}
        for case in cases:
            answers = {}
            record_id = case["record_id"]
            for label, tag in mapping[record_id].items():
                finish = "stop"
                text = "Odpowiedź"
                if record_id == "C000-1":
                    if tag == "checkpoint-21":
                        finish = "length"
                    elif tag == "base":
                        finish, text = "error", ""
                history = histories[tag]
                context = history.context(case)
                row = {
                    "case": record_id,
                    "model": tag,
                    "label": label,
                    "response": {"text": text, "finish": finish, "error": None},
                    **context,
                }
                history.remember(case, row, context)
                raw.append(row)
                answers[label] = blind_answer(row)
            blind.append({"case": case, "answers": answers})

        write_jsonl(stage / "raw.jsonl", raw)
        write_jsonl(stage / "blind.jsonl", blind)
        _write(stage / "unblind.json", mapping)
        _write(
            stage / "manifest.json",
            {
                "models": models,
                "model_repo": model,
                "snapshot_manifest_sha256": digest(SNAPSHOT_PIN),
                "data_sha256": digest(dataset),
                "evaluated_ids": [case["record_id"] for case in cases],
                "max_new_tokens": 512,
                "case_max_new_tokens": {case["record_id"]: 512 for case in cases},
                "dialogue_protocol": "own-history-v1",
                "resumed_generations": 1,
                "generation_identity_sha256": "0" * 64,
                "outputs": {
                    name: digest(stage / name)
                    for name in ("raw.jsonl", "blind.jsonl", "unblind.json")
                },
            },
        )

    with pytest.raises(TimeoutError, match="fixture interruption"):
        generate_panel(args, evaluator=fake_evaluator)
    assert not (output / "generation-acceptance.json").exists()
    report = generate_panel(args, evaluator=fake_evaluator)
    assert attempts[0][0] == attempts[1][0]
    assert attempts[0][1] != attempts[1][1]
    assert report["status"] == "complete"
    assert report["conversations"] == 96
    assert report["resumed_generations"] == 1
    assert report["generation_counts"] == {
        "base": {"turns": 384, "stop": 383, "error": 1, "length": 0, "nonempty": 383},
        "parent": {"turns": 384, "stop": 384, "error": 0, "length": 0, "nonempty": 384},
        "candidate": {
            "turns": 384,
            "stop": 383,
            "error": 0,
            "length": 1,
            "nonempty": 384,
        },
    }
    for arm in ("parent", "candidate"):
        pair_seal = output / report[arm]["path"] / "generation-seal.json"
        assert report[arm]["generation_seal_sha256"] == digest(pair_seal)
    assert generate_panel(args, evaluator=fake_evaluator) == report
    assert len(attempts) == 2
    cases[0]["messages"][0]["content"] += " Dopisek."
    args.dataset = tmp_path / "changed.jsonl"
    write_jsonl(args.dataset, cases)
    with pytest.raises(ValueError, match="generation_intent_changed"):
        generate_panel(args, evaluator=fake_evaluator)
