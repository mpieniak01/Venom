"""Offline acceptance of revised reviewer-control data and preservation boundaries."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from venom_core.services.training_experiments import semantic_judge_controls as controls
from venom_core.services.training_experiments.profiles import digest


def write(root: Path, name: str, value: dict) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf8")


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "old" / "controls"
    cases, accepted, rejected = [], [], {}
    for i in range(12):
        answers = [{"id": f"L{i:02}{j:02}", "text": f"wariant {j}"} for j in range(5)]
        if i == 0:
            answers[0] = {"id": "J811", "text": "Ada wydaje osiem pudeł."}
        cases.append(
            {
                "id": "KOR-1" if i == 0 else f"L{i:02}",
                "messages": [
                    {"role": "user", "content": "Odbiór u Ady."},
                    {"role": "user", "content": "Podaj osobę."},
                ],
                "criteria": [{"id": "person", "description": "Odbiór u Ady."}],
                "answers": answers,
            }
        )
        accepted.extend(a["id"] for a in answers[:2])
        rejected.update({a["id"]: "negative" for a in answers[2:]})
    write(root, controls.PHASE1_FILES[0], {"cases": cases})
    write(root, controls.PHASE1_FILES[1], {"accepted": accepted, "rejected": rejected})
    template, gold_template = controls.contrast_controls()
    for split, families in (("development", 12), ("extra", 8)):
        panel, gold = {"cases": []}, {"answers": {}}
        for i in range(families):
            case = copy.deepcopy(template["cases"][0])
            ident = f"{split}{i:02}"
            case["id"] = case["family_id"] = ident
            if split == "extra" and i == 1:
                case["messages"][0]["content"] = (
                    "Dostawa nie wymaga chłodzenia. Jedzie w skrzyni D."
                )
            for j, answer in enumerate(case["answers"]):
                old = answer["id"]
                answer["id"] = (
                    f"X{i + 1:02}{j + 1:02}" if split == "extra" else f"D{i:02}{j:02}"
                )
                item = copy.deepcopy(gold_template["answers"][old])
                item["case_id"] = ident
                if (split, i) in {("development", 5), ("extra", 6)}:
                    field = "owner" if split == "development" else "price"
                    case["criteria"][0]["id"] = field
                    item["decision"]["atoms"][field] = item["decision"]["atoms"].pop(
                        "focus"
                    )
                    if j == 2:
                        answer["id"] = "Q73853" if split == "development" else "X0703"
                        item["decision"]["atoms"][field] = "contradicted"
                gold["answers"][answer["id"]] = item
                if split == "extra" and i == 1 and j == 0:
                    answer["text"] = "Chłodzenia nie zamówiono; skrzynia D."
            panel["cases"].append(case)
        write(root, f"{split}/panel.json", panel)
        write(root, f"{split}/gold.json", gold)
    files = {name: digest(root / name) for name in controls.PHASE1_FILES}
    # Deliberately no holdout files: even binary reads would fail.
    files.update({"holdout/panel.json": "a" * 64, "holdout/gold.json": "b" * 64})
    write(
        root,
        "frozen-manifest.json",
        {
            "status": "frozen_before_any_inference",
            "files": files,
        },
    )
    return root


def build(source: Path, tmp_path: Path):
    output = tmp_path / "new" / "controls"
    return output, controls.build_controls(
        source, output, digest(source / "frozen-manifest.json")
    )


def test_build_repairs_explicit_facts_and_preserves_old_files(source, tmp_path):
    before = {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    output, manifest = build(source, tmp_path)
    assert before == {name: (source / name).read_bytes() for name in before}
    assert not (output / "holdout").exists()
    legacy = json.loads((output / controls.PHASE1_FILES[0]).read_text())
    assert legacy["cases"][0]["answers"][0]["text"] == "Ada wydaje osiem pudeł."
    assert "osobiście wydaje" in legacy["cases"][0]["messages"][0]["content"]
    assert "osobny adres" in legacy["cases"][0]["criteria"][0]["description"]
    extra = json.loads((output / "extra/panel.json").read_text())
    assert "Nie zamówiono chłodzenia." in extra["cases"][1]["messages"][0]["content"]
    assert (
        extra["cases"][1]["answers"][1]["text"]
        == "Nie zamawiano chłodzenia; skrzynia D."
    )
    assert manifest["source_files"] == {
        n: digest(source / n) for n in controls.PHASE1_FILES
    }
    assert manifest["thresholds"] == controls.THRESHOLDS
    assert manifest["data_review_required"] is True
    for name in (
        "legacy/qualification-gold.json",
        "development/panel.json",
    ):
        assert (output / name).read_bytes() == (source / name).read_bytes()
    provenance = json.loads((output / "repair-provenance.json").read_text())
    assert provenance["files"]["development/panel.json"]["semantic_changed"] is False
    for name, ident, field in (
        ("development/gold.json", "Q73853", "owner"),
        ("extra/gold.json", "X0703", "price"),
    ):
        before = json.loads((source / name).read_text())["answers"][ident]
        after = json.loads((output / name).read_text())["answers"][ident]
        assert before["decision"]["atoms"][field] == "contradicted"
        assert after["decision"]["atoms"][field] == "omitted"
        assert after["decision"]["unsupported"] == "yes"
        assert after["expected"] == "negative"
    assert (
        provenance["files"]["legacy/qualification-panel.json"]["semantic_changed"]
        is True
    )
    assert manifest["holdout"]["files"]["panel.json"] == "a" * 64
    order = json.loads((output / "phase1-order.json").read_text())["jobs"]
    assert len(order) == len({(r["split"], r["answer_id"]) for r in order}) == 156
    assert all(r["repeat"] == 1 and r["split"] != "holdout" for r in order)


def test_new_contrasts_separate_requirements_orders_roles_and_places(source, tmp_path):
    output, manifest = build(source, tmp_path)
    jobs, gold = controls.jobs_for_contrasts(output.parent, manifest)
    assert len(jobs) == 16
    assert sum(r["expected"] == "positive" for r in gold["answers"].values()) == 8
    assert "nie wymaga" in jobs["C0101"][0]["messages"][0]["content"]
    assert "zamówiono je" in jobs["C0201"][0]["messages"][0]["content"]
    assert "osobiście wydającą" in jobs["C0301"][0]["messages"][0]["content"]
    assert "Nie podano, kto je wyda" in jobs["C0401"][0]["messages"][0]["content"]
    assert gold["answers"]["C0103"]["decision"]["unsupported"] == "yes"
    assert gold["answers"]["C0103"]["decision"]["atoms"]["focus"] == "omitted"
    assert gold["answers"]["C0403"]["decision"]["unsupported"] == "yes"
    assert gold["answers"]["C0403"]["decision"]["atoms"]["focus"] == "omitted"
    assert gold["answers"]["C0404"]["decision"]["atoms"]["focus"] == "omitted"


@pytest.mark.parametrize(
    "damage",
    [
        "manifest",
        "panel",
        "source_shape",
        "repair_person",
        "repair_cooling",
        "repair_answer",
    ],
)
def test_bad_or_unexpected_source_cannot_publish(source, tmp_path, damage):
    if damage == "manifest":
        expected = "0" * 64
    else:
        name = (
            controls.PHASE1_FILES[0]
            if damage in {"source_shape", "repair_person"}
            else controls.PHASE1_FILES[4]
        )
        value = json.loads((source / name).read_text())
        if damage == "panel":
            value["cases"][0]["messages"][0]["content"] = "tampered"
        elif damage == "source_shape":
            value["cases"].pop()
        elif damage == "repair_person":
            value["cases"][0]["answers"][0]["text"] = "Ada."
        elif damage == "repair_cooling":
            value["cases"][1]["messages"][0]["content"] = "Nie ma tego źródła."
        elif damage == "repair_answer":
            value["cases"][1]["answers"][0]["text"] = "Inna odpowiedź."
        write(source, name, value)
        if damage != "panel":
            manifest = json.loads((source / "frozen-manifest.json").read_text())
            manifest["files"][name] = digest(source / name)
            write(source, "frozen-manifest.json", manifest)
        expected = digest(source / "frozen-manifest.json")
    with pytest.raises(ValueError):
        controls.build_controls(source, tmp_path / "bad", expected)
    assert not (tmp_path / "bad").exists()


def test_source_symlink_escape_refused(source, tmp_path):
    original = source / controls.PHASE1_FILES[0]
    external = tmp_path / "external.json"
    external.write_bytes(original.read_bytes())
    original.unlink()
    original.symlink_to(external)
    with pytest.raises(ValueError, match="source_escape"):
        controls.build_controls(
            source, tmp_path / "bad", digest(source / "frozen-manifest.json")
        )


@pytest.mark.parametrize("kind", ["existing", "inside", "ancestor"])
def test_output_cannot_overwrite_or_overlap_source(source, tmp_path, kind):
    output = {"existing": source, "inside": source / "new", "ancestor": source.parent}[
        kind
    ]
    with pytest.raises(ValueError):
        controls.build_controls(source, output, digest(source / "frozen-manifest.json"))


def test_tampered_contrasts_refused(source, tmp_path):
    output, manifest = build(source, tmp_path)
    (output / "contrasts/gold.json").write_text("{}")
    with pytest.raises(ValueError, match="source_changed"):
        controls.jobs_for_contrasts(output.parent, manifest)


def test_contrast_reader_accepts_relative_audit_root(source, tmp_path, monkeypatch):
    output, manifest = build(source, tmp_path)
    monkeypatch.chdir(tmp_path)
    jobs, _ = controls.jobs_for_contrasts(Path("new"), manifest)
    assert len(jobs) == 16
