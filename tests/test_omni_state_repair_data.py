"""State repair oracle and context-only masking contracts, with no model load."""

import json

import pytest

from scripts.academy import omni_state_repair_data as data
from scripts.academy.omni_pl_chat_audit import leakage_counts


def specimen(split="train", family="repair-fixture"):
    return {
        "family": family,
        "split": split,
        "topic": "kontrola dostawy",
        "state": {
            "osoba": "Iga",
            "miejsce": "hala 7",
            "godzina": "11:20",
            "cena": "45 zł",
        },
        "new_person": "Maks",
        "new_price": "51 zł",
    }


def test_state_oracle_keeps_fields_and_accepts_only_confirmed_price():
    accepted = data.trajectory(specimen(), True)
    rejected = data.trajectory(specimen(), False)
    assert accepted[1]["answer"] == rejected[1]["answer"]
    assert "osoba: Maks" in accepted[1]["answer"]
    assert "cena: 45 zł" in accepted[1]["answer"]
    assert "cena: 51 zł" in accepted[2]["answer"]
    assert "cena: 45 zł" in rejected[2]["answer"]
    assert accepted[3]["answer"] == rejected[3]["answer"] == "Brak danych."
    assert "miejsce: brak danych" in accepted[4]["answer"]
    assert accepted[-1]["answer"] == accepted[2]["answer"]
    assert rejected[-1]["answer"] == rejected[2]["answer"]


@pytest.mark.parametrize(
    "change",
    [
        {"split": "final"},
        {"new_person": "Iga"},
        {"new_price": "45 zł"},
        {"state": {}},
        {"topic": ""},
        {"extra": True},
    ],
)
def test_rejects_invalid_or_ineffective_specimens(change):
    with pytest.raises(ValueError, match="specimen"):
        data.trajectory({**specimen(), **change}, True)


def test_training_error_is_context_only_and_targets_are_short():
    train, dev = data.compile_specs([specimen()], "a" * 64)
    assert len(train) == 9 and not dev
    for row in train:
        messages = row["messages"]
        assert row["supervision"] == [len(messages) - 1]
        assert row["context_only_assistant_indices"][0] == 2
        assert "BŁĘDNIE" in messages[2]["content"]
        assert 2 not in row["supervision"]
        assert set(row["supervision"]).isdisjoint(row["context_only_assistant_indices"])
        assert messages[-1]["content"] == row["expected_answer"]
        assert len(messages[-1]["content"]) < 100
        assert row["source_revision"] == "a" * 64


def test_dev_uses_own_history_and_families_are_not_reused():
    train, dev = data.compile_specs(
        [specimen(), specimen("dev", "new-family")], "b" * 64
    )
    assert len(dev) == 12
    assert {r["group_id"] for r in train}.isdisjoint({r["group_id"] for r in dev})
    for row in dev:
        assert row["messages"][-1]["role"] == "user"
        if row["dialogue"]["turn_index"] > 1:
            assert len(row["messages"]) == 1
        assert all(m["role"] != "assistant" for m in row["messages"])
    assert leakage_counts(train, dev) == {
        "normalization": "nfkc_casefold_whitespace_v1",
        "supervised_prefix_matches": 0,
        "final_user_matches": 0,
        "duplicate_train_records": 0,
    }
    with pytest.raises(ValueError, match="families"):
        data.compile_specs([specimen(), specimen("dev")], "b" * 64)


def write_replay(path, chosen="Poprawna odpowiedź."):
    path.write_text(
        json.dumps(
            {
                "id": "prior-1",
                "family": "prior-family",
                "task": "source",
                "messages": [{"role": "user", "content": "Odczytaj poprzedni wpis."}],
                "chosen": chosen,
            }
        )
        + "\n"
    )


def test_replay_preserves_chosen_with_exact_source_identity(tmp_path):
    path = tmp_path / "replay.jsonl"
    write_replay(path)
    row = data.import_replay(path)[0]
    assert row["messages"][-1]["content"] == "Poprawna odpowiedź."
    assert row["source_revision"] == data.sha256(path)
    assert row["sampling_pool"] == "replay"
    assert row["supervision"] == [1]
    write_replay(path, "")
    with pytest.raises(ValueError, match="chosen"):
        data.import_replay(path)


def test_build_is_reproducible_unready_and_refuses_overwrite(tmp_path):
    spec_path, replay = tmp_path / "spec.json", tmp_path / "prior.jsonl"
    spec_path.write_text(json.dumps([specimen(), specimen("dev", "new-family")]))
    write_replay(replay)
    first, second = tmp_path / "one", tmp_path / "two"
    a = data.build(spec_path, replay, first)
    b = data.build(spec_path, replay, second)
    assert a == b
    assert a["start_ready"] is False
    assert a["final_holdout_opened"] is False
    assert "parent_not_selected" in a["blocking"]
    assert a["records"] == {"fresh": 9, "replay": 1, "dev": 12}
    assert a["files"] == {name: data.sha256(second / name) for name in a["files"]}
    with pytest.raises(FileExistsError):
        data.build(spec_path, replay, first)


@pytest.mark.parametrize("specs", [[], {}, [specimen()], [specimen("dev")]])
def test_build_requires_both_splits_before_writing(tmp_path, specs):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(specs))
    with pytest.raises(ValueError):
        data.build(path, tmp_path / "unused", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_cli_builds_private_package_without_model_or_training(
    tmp_path, monkeypatch, capsys
):
    path, replay = tmp_path / "spec.json", tmp_path / "prior.jsonl"
    path.write_text(json.dumps([specimen(), specimen("dev", "new-family")]))
    write_replay(replay)
    monkeypatch.setattr(
        "sys.argv",
        [
            "prepare",
            "--specimens",
            str(path),
            "--replay",
            str(replay),
            "--output",
            str(tmp_path / "out"),
        ],
    )
    data.main()
    assert json.loads(capsys.readouterr().out)["start_ready"] is False
