"""Build private, single-target state-repair data; never start training."""

import argparse
import hashlib
import json
from pathlib import Path

from scripts.academy.omni_pl_chat_data import sha256, validate_splits, write_jsonl
from scripts.academy.omni_pl_chat_evaluate import validate_dev_cases
from venom_core.services.training_experiments.grounded_claims import (
    validate_claim_rubrics,
)

SYSTEM = (
    "Odpowiadaj po polsku, krótko. Zachowuj pola nieobjęte korektą. "
    "Źródłem ustaleń są wiadomości użytkownika, nie błędne odpowiedzi asystenta. "
    "Odróżniaj aktualne źródło od stanu rozmowy. Gdy pytanie dotyczy wyłącznie "
    "źródła, nie uzupełniaj go historią. Brak informacji nazwij krótko."
)
FIELDS = ("osoba", "miejsce", "godzina", "cena")


def _text(state: dict) -> str:
    return "; ".join(f"{key}: {state[key]}" for key in FIELDS) + "."


def _check_spec(spec: dict) -> None:
    if (
        set(spec) != {"family", "split", "topic", "state", "new_person", "new_price"}
        or spec["split"] not in {"train", "dev"}
        or not isinstance(spec["state"], dict)
        or set(spec["state"]) != set(FIELDS)
        or any(not isinstance(v, str) or not v.strip() for v in spec["state"].values())
        or any(
            not isinstance(spec[k], str) or not spec[k].strip()
            for k in ("family", "topic", "new_person", "new_price")
        )
        or spec["new_person"] == spec["state"]["osoba"]
        or spec["new_price"] == spec["state"]["cena"]
    ):
        raise ValueError("invalid or ineffective state-repair specimen")


def trajectory(spec: dict, accepted: bool) -> list[dict]:
    """A deterministic state oracle, with explicit scope and decision per turn."""
    _check_spec(spec)
    state = spec["state"].copy()
    steps = [
        {
            "user": f"Ustalenia: {spec['topic']}. {_text(state)} Podaj cały obowiązujący rekord.",
            "answer": _text(state),
            "task": "source_read",
        }
    ]
    state["osoba"] = spec["new_person"]
    steps.append(
        {
            "user": f"Zatwierdzam zmianę osoby na {spec['new_person']}. Cena {spec['new_price']} jest tylko nierozstrzygniętą propozycją. Jeżeli wcześniej podałeś inną osobę lub zmieniłeś inne pole, popraw błąd. Wypisz wszystkie aktualne pola.",
            "answer": _text(state),
            "task": "person_correction_preserve",
        }
    )
    if accepted:
        state["cena"] = spec["new_price"]
    decision = "przyjęta" if accepted else "odrzucona"
    steps.append(
        {
            "user": f"Propozycja nowej ceny została {decision}. Pozostałe ustalenia są wiążące. Podaj komplet pól z jedną obowiązującą ceną.",
            "answer": _text(state),
            "task": "decision_accepted" if accepted else "decision_rejected",
        }
    )
    steps.append(
        {
            "user": f"Osobna aktualna karta ma CAŁĄ treść: «osoba: {spec['new_person']}». Nie zmienia naszych ustaleń. Jakie miejsce podaje wyłącznie ta karta? Gdy go brak, odpowiedz tylko «Brak danych».",
            "answer": "Brak danych.",
            "task": "source_missing",
        }
    )
    steps.append(
        {
            "user": "Według wyłącznie tej samej karty podaj osobę i miejsce. Zapisz znaną wartość i krótki brak przy brakującym polu.",
            "answer": f"osoba: {spec['new_person']}; miejsce: brak danych.",
            "task": "partial_source",
        }
    )
    steps.append(
        {
            "user": "Teraz pytam o nadal obowiązujące USTALENIA ROZMOWY, a nie o kartę. Wypisz wszystkie cztery pola. Odczyt karty nie odwoływał ustaleń.",
            "answer": _text(state),
            "task": "state_after_source",
        }
    )
    expected_states = [
        spec["state"].copy(),
        {**spec["state"], "osoba": spec["new_person"]},
        state.copy(),
        {"miejsce": None},
        {"osoba": spec["new_person"], "miejsce": None},
        state.copy(),
    ]
    for step, expected in zip(steps, expected_states, strict=True):
        step["expected_fields"] = expected
    if spec["split"] == "dev":
        prompts = [
            f"Rejestr roboczy: {_text(spec['state'])} Wypisz wszystkie aktualne pola.",
            f"W aktualizacji zatwierdzono osobę {spec['new_person']}. Pytanie o cenę {spec['new_price']} nadal czeka na decyzję. Zachowaj resztę wpisu i podaj pełny obowiązujący stan.",
            f"Decyzja o zaproponowanej cenie jest ostateczna: {decision}. Potrzebuję pełnego wpisu po tej decyzji, z jedną ceną.",
            f"Przeczytaj bieżącą kartę, której kompletna zawartość brzmi «osoba: {spec['new_person']}». To materiał informacyjny bez zmiany ustaleń. Pytam wyłącznie o wymienione tam miejsce. Odpowiedz samym «Brak danych», jeżeli karta go nie zawiera.",
            "W świetle TEJ KARTY wypisz osobę oraz miejsce; każde pominięte pole oznacz jako brak danych.",
            "Karta miała zakres informacyjny. Wracamy do wiążącego stanu rozmowy: wypisz osobę, miejsce, godzinę i jedyną obowiązującą cenę.",
        ]
        for step, prompt in zip(steps, prompts, strict=True):
            step["user"] = f"Sprawa: {spec['topic']}. {prompt}"
    return steps


def compile_specs(specs: list[dict], revision: str) -> tuple[list[dict], list[dict]]:
    """Keep erroneous assistant text as context only; dev uses actual own history."""
    train, dev = [], []
    families = set()
    for spec in specs:
        _check_spec(spec)
        family = spec["family"]
        if family in families:
            raise ValueError("specimen families must be unique across splits")
        families.add(family)
        for accepted in (False, True):
            branch = "accepted" if accepted else "rejected"
            ident = f"{family}-{branch}"
            history = [{"role": "system", "content": SYSTEM}]
            for index, step in enumerate(trajectory(spec, accepted), 1):
                messages = [*history, {"role": "user", "content": step["user"]}]
                common = {
                    "record_id": f"{ident}-{index}",
                    "group_id": family,
                    "split": spec["split"],
                    "language": "pl",
                    "task": step["task"],
                    "decision": branch,
                }
                if (
                    spec["split"] == "train"
                    and index > 1
                    and not (accepted and index == 2)
                ):
                    train.append(
                        {
                            **common,
                            "messages": [
                                *messages,
                                {"role": "assistant", "content": step["answer"]},
                            ],
                            "supervision": [len(messages)],
                            "sampling_pool": "fresh",
                            "source_repo": "Venom private state-repair specimens",
                            "source_revision": revision,
                            "source_record_id": f"{ident}-{index}",
                            "license": "Project-authored synthetic material for local experiment",
                            "quality_status": "accepted",
                            "review_note": "Agent-authored; deterministic state and scope oracle. Earlier assistant error is excluded from supervision. No independent human review.",
                            "expected_answer": step["answer"],
                            "context_only_assistant_indices": [
                                i
                                for i, m in enumerate(messages)
                                if m["role"] == "assistant"
                            ],
                        }
                    )
                elif spec["split"] == "dev":
                    dev.append(
                        {
                            **common,
                            "messages": [{"role": "user", "content": step["user"]}]
                            if index > 1
                            else messages,
                            "dialogue": {"id": ident, "turn_index": index},
                            "max_new_tokens": 256,
                            "expected_fields": step["expected_fields"],
                            "criteria": [
                                *[
                                    {
                                        "id": f"fact-{number}",
                                        "kind": "content",
                                        "description": f"Pole {field}: {value if value is not None else 'brak danych w karcie'}. Bez sprzecznej wartości.",
                                    }
                                    for number, (field, value) in enumerate(
                                        step["expected_fields"].items(), 1
                                    )
                                ],
                                {
                                    "id": "short",
                                    "kind": "format",
                                    "description": "Krótka odpowiedź na podane pola, bez uzasadnień.",
                                },
                            ],
                        }
                    )
                answer = step["answer"]
                if index == 1 and spec["split"] == "train":
                    wrong = spec["state"].copy()
                    wrong["osoba"] = "BŁĘDNIE PRZYPISANA OSOBA"
                    answer = _text(wrong)
                history = [*messages, {"role": "assistant", "content": answer}]
    validate_splits(train, dev)
    if dev:
        validate_dev_cases(dev)
    return train, dev


def _read_replay(path: Path) -> tuple[list[dict], str]:
    """Hash and parse the same source bytes, even if the file changes later."""
    raw = path.read_bytes()
    revision = hashlib.sha256(raw).hexdigest()
    result = []
    for line in raw.decode("utf8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row.get("chosen"), str) or not row["chosen"].strip():
            raise ValueError("historical replay requires a chosen answer")
        result.append(
            {
                "record_id": f"replay-{row['id']}",
                "group_id": f"replay-{row['family']}",
                "split": "train",
                "language": "pl",
                "task": row["task"],
                "messages": [
                    *row["messages"],
                    {"role": "assistant", "content": row["chosen"]},
                ],
                "supervision": [len(row["messages"])],
                "sampling_pool": "replay",
                "source_repo": "Venom historical chosen replay",
                "source_revision": revision,
                "source_record_id": row["id"],
                "license": "Project-authored synthetic material for local experiment",
                "quality_status": "accepted",
                "review_note": "Retained historical chosen label, not independently revalidated in this preparation.",
            }
        )
    validate_splits(result)
    return result, revision


def import_replay(path: Path) -> list[dict]:
    """Preserve historical chosen labels and identify their exact source read."""
    return _read_replay(path)[0]


def build(spec_path: Path, replay_path: Path, output: Path) -> dict:
    """Create a new package only. Inputs and historical artifacts are read-only."""
    specimen_bytes = spec_path.read_bytes()
    specimen_revision = hashlib.sha256(specimen_bytes).hexdigest()
    specs = json.loads(specimen_bytes.decode("utf8"))
    if not isinstance(specs, list) or not specs:
        raise ValueError("expected nonempty private specimens")
    fresh, dev = compile_specs(specs, specimen_revision)
    if not fresh or not dev:
        raise ValueError("preparation requires both train and dev families")
    replay, replay_revision = _read_replay(replay_path)
    train = [*fresh, *replay]
    if len(train) > 2048:
        raise ValueError("training records exceed the bounded recipe contract")
    validate_splits(train, dev)
    rubrics = {
        row["record_id"]: {
            "claims": {
                f"fact-{number}": {
                    "field_aliases": [field],
                    "kind": "missing" if value is None else "value",
                    **({"value_aliases": [value]} if value is not None else {}),
                }
                for number, (field, value) in enumerate(
                    row["expected_fields"].items(), 1
                )
            },
            "format": {
                "short": "bare_value" if row["task"] == "source_missing" else "labeled"
            },
        }
        for row in dev
    }
    validate_claim_rubrics(rubrics, dev)
    output.mkdir(parents=True, exist_ok=False)
    write_jsonl(output / "train.jsonl", train)
    write_jsonl(output / "dev.jsonl", dev)
    taxonomy = {
        "schema_version": 1,
        "records": {
            r["record_id"]: {"group": r["sampling_pool"], "skill": r["task"]}
            for r in train
        },
    }
    (output / "taxonomy.json").write_text(json.dumps(taxonomy, indent=2) + "\n")
    (output / "dev.rubrics.json").write_text(
        json.dumps({"cases": rubrics}, ensure_ascii=False, indent=2) + "\n"
    )
    manifest = {
        "schema_version": 1,
        "start_ready": False,
        "blocking": [
            "qualified_judge_missing",
            "parent_not_selected",
            "native_token_exposure_not_audited",
            "new_dev_calibration_missing",
            "final_inputs_not_bound",
        ],
        "sources": {
            "specimens": {
                "path": str(spec_path.resolve()),
                "sha256": specimen_revision,
            },
            "replay": {
                "path": str(replay_path.resolve()),
                "sha256": replay_revision,
            },
        },
        "files": {
            name: sha256(output / name)
            for name in (
                "train.jsonl",
                "dev.jsonl",
                "taxonomy.json",
                "dev.rubrics.json",
            )
        },
        "records": {"fresh": len(fresh), "replay": len(replay), "dev": len(dev)},
        "final_holdout_opened": False,
        "limitations": [
            "Synthetic authored state trajectories; no independent human review.",
            "Family-disjoint dev still shares the state-machine mechanism and prompt templates.",
            "Historical replay is deliberate reuse, not new independent evidence.",
        ],
    }
    (output / "preparation.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specimens", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.specimens, args.replay, args.output), indent=2))


if __name__ == "__main__":
    main()
