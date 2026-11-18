"""Build versioned, source-bound judge controls without opening protected holdout files."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .profiles import digest

VERSION = "luna-controls-v3"
_MANIFEST = "frozen-manifest.json"
_PROVENANCE = "repair-provenance.json"
THRESHOLDS = {
    "legacy_positive": 24,
    "legacy_negative": 36,
    "legacy_style": 24,
    "legacy_semantics": 6,
    "development_full": 48,
    "extra_full": 32,
    "contrasts_full": 16,
    "holdout_full": 72,
    "holdout_stable_groups": 24,
}
PHASE1_FILES = (
    "legacy/qualification-panel.json",
    "legacy/qualification-gold.json",
    "development/panel.json",
    "development/gold.json",
    "extra/panel.json",
    "extra/gold.json",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf8"))


def _write(root: Path, name: str, value: dict) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf8",
    )


def _source_bytes(source: Path, name: str, expected: str) -> bytes:
    source = source.resolve(strict=True)
    path = source / name
    if path.is_symlink() or not path.resolve().is_relative_to(source):
        raise ValueError("judge_controls_source_escape")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("judge_controls_source_changed")
    return raw


def _bound(source: Path, name: str, expected: str) -> dict:
    return json.loads(_source_bytes(source, name, expected))


def _case(panel: dict, answer_id: str) -> dict:
    found = [
        case
        for case in panel["cases"]
        if any(answer["id"] == answer_id for answer in case["answers"])
    ]
    if len(found) != 1:
        raise ValueError("judge_controls_repair_target_invalid")
    return found[0]


def _repair_legacy(panel: dict) -> None:
    case = _case(panel, "J811")
    if case["id"] != "KOR-1":
        raise ValueError("judge_controls_repair_target_invalid")
    issuer = next(a["text"] for a in case["answers"] if a["id"] == "J811")
    issuer, separator, _ = issuer.partition(" wydaje ")
    if not separator or not issuer.strip():
        raise ValueError("judge_controls_repair_target_invalid")
    case["messages"][0]["content"] += (
        f" Osobą obsługującą odbiór jest {issuer}. Ta osoba osobiście wydaje pudła."
    )
    case["messages"][-1]["content"] += (
        " Pytanie o osobę dotyczy osoby obsługującej odbiór. "
        "Nie pytam o osobny adres ani o opis czynności."
    )
    person = next(c for c in case["criteria"] if c["id"] == "person")
    person["description"] = (
        f"Osoba obsługująca odbiór: {issuer}. "
        "Wystarczy jej identyfikacja w kontekście odbioru; "
        "osobny adres ani opis czynności nie są wymagane."
    )


def _repair_extra(panel: dict, gold: dict) -> None:
    case = _case(panel, "X0201")
    message = case["messages"][0]["content"]
    if "Dostawa nie wymaga chłodzenia." not in message:
        raise ValueError("judge_controls_repair_target_invalid")
    case["messages"][0]["content"] = message.replace(
        "Dostawa nie wymaga chłodzenia.",
        "Dostawa nie wymaga chłodzenia. Nie zamówiono chłodzenia.",
        1,
    )
    answers = {a["id"]: a for a in case["answers"]}
    if not answers["X0201"]["text"].startswith("Chłodzenia nie zamówiono;"):
        raise ValueError("judge_controls_repair_target_invalid")
    answers["X0202"]["text"] = answers["X0201"]["text"].replace(
        "Chłodzenia nie zamówiono;", "Nie zamawiano chłodzenia;", 1
    )
    gold["answers"]["X0202"]["rationale"] = (
        "Parafraza jawnej decyzji o zamówieniu, bez wnioskowania z braku wymogu."
    )


def _repair_epistemic_gold(development: dict, extra: dict) -> None:
    for gold, ident, field in (
        (development, "Q73853", "owner"),
        (extra, "X0703", "price"),
    ):
        item = gold["answers"][ident]
        decision = item["decision"]
        if (
            item["expected"] != "negative"
            or decision["atoms"][field] != "contradicted"
            or decision["unsupported"] != "yes"
        ):
            raise ValueError("judge_controls_epistemic_target_invalid")
        decision["atoms"][field] = "omitted"
        item["rationale"] = (
            "Wymagany komunikat o braku informacji pominięty; konkretna wartość "
            "pozostaje niepopartym twierdzeniem, bez zaprzeczenia o stanie świata."
        )


def _decision(first: str, second: str, *, extra: bool = False) -> dict:
    return {
        "atoms": {"focus": first, "anchor": second},
        "unsupported": "yes" if extra or "contradicted" in (first, second) else "no",
        "injection": False,
        "polish_ok": True,
        "natural_ok": True,
    }


def contrast_controls() -> tuple[dict, dict]:
    """Four explicit evidence contrasts, each with two positive and two negative answers."""
    specs = (
        (
            "C01",
            "Dostawa nie wymaga chłodzenia. Jedzie w skrzyni M. "
            "Nie podano żadnej informacji o tym, czy zamówiono chłodzenie. "
            "Czy chłodzenie zamówiono i jaka jest skrzynia?",
            "Brak informacji, czy zamówiono chłodzenie. Nie utożsamiaj wymogu z decyzją zamówienia.",
            "Skrzynia M.",
            (
                (
                    "Nie wiadomo, czy zamówiono chłodzenie; skrzynia M.",
                    "supported",
                    False,
                ),
                (
                    "Nie podano decyzji o zamówieniu chłodzenia. Skrzynia M.",
                    "supported",
                    False,
                ),
                ("Nie zamówiono chłodzenia; skrzynia M.", "omitted", True),
                ("Skrzynia M.", "omitted", False),
            ),
        ),
        (
            "C02",
            "Chłodzenie nie jest wymagane, ale mimo tego zamówiono je dla tej dostawy. "
            "Dostawa jedzie w skrzyni N. Podaj decyzję o zamówieniu chłodzenia i skrzynię.",
            "Zamówiono chłodzenie mimo braku takiego wymogu.",
            "Skrzynia N.",
            (
                ("Chłodzenie zamówiono; skrzynia N.", "supported", False),
                ("Tak, zamówiono chłodzenie. Skrzynia N.", "supported", False),
                ("Nie zamówiono chłodzenia; skrzynia N.", "contradicted", False),
                ("Skrzynia N.", "omitted", False),
            ),
        ),
        (
            "C03",
            "Osobą osobiście wydającą teczki przy odbiorze jest Ada. "
            "Przygotowano dziewięć teczek. Podaj osobę wydającą i liczbę teczek.",
            "Teczki wydaje Ada; wystarczy identyfikacja osoby w kontekście wydawania.",
            "Dziewięć teczek.",
            (
                ("Ada wydaje dziewięć teczek.", "supported", False),
                ("Dziewięć teczek wyda Ada.", "supported", False),
                ("Dziewięć teczek wyda Ewa.", "contradicted", False),
                ("Dziewięć teczek.", "omitted", False),
            ),
        ),
        (
            "C04",
            "Odbiór pięciu segregatorów odbywa się w domu Idy. "
            "Nie podano, kto je wyda. Czy znamy osobę wydającą i ile jest segregatorów?",
            "Nie wiadomo, kto wyda segregatory; miejsce odbioru nie wskazuje tej osoby.",
            "Pięć segregatorów.",
            (
                ("Nie wiadomo, kto wyda pięć segregatorów.", "supported", False),
                (
                    "Osoby wydającej nie podano; jest pięć segregatorów.",
                    "supported",
                    False,
                ),
                ("Ida wyda pięć segregatorów.", "omitted", True),
                ("Pięć segregatorów.", "omitted", False),
            ),
        ),
    )
    cases, answers = [], {}
    for ident, message, focus, anchor, variants in specs:
        case: dict = {
            "id": ident,
            "family_id": ident,
            "kind": "semantic_contrast",
            "messages": [{"role": "user", "content": message}],
            "criteria": [
                {"id": "focus", "description": focus, "kind": "content"},
                {"id": "anchor", "description": anchor, "kind": "content"},
            ],
            "evidence": [],
            "answers": [],
        }
        for index, (text, relation, extra) in enumerate(variants, 1):
            answer_id = f"{ident}{index:02d}"
            case["answers"].append({"id": answer_id, "text": text})
            answers[answer_id] = {
                "case_id": ident,
                "expected": "positive" if relation == "supported" else "negative",
                "decision": _decision(relation, "supported", extra=extra),
                "rationale": focus,
            }
        cases.append(case)
    return {"cases": cases}, {"answers": answers}


def jobs_for_contrasts(root: Path, manifest: dict) -> tuple[dict, dict]:
    """Return jobs and full-vector gold in the same shape as v4.jobs_for."""
    controls = root / "controls"
    panel, gold = (
        _bound(controls, name, manifest["files"][name])
        for name in ("contrasts/panel.json", "contrasts/gold.json")
    )
    from .semantic_judge_v4 import _verify_gold

    jobs = {
        answer["id"]: (case, answer)
        for case in panel["cases"]
        for answer in case["answers"]
    }
    if len(panel["cases"]) != 4 or len(jobs) != 16:
        raise ValueError("judge_controls_contrasts_invalid")
    _verify_gold(panel["cases"], gold, jobs)
    return jobs, gold


def _validate_source(values: dict) -> None:
    from .semantic_judge_v4 import _verify_gold

    for split, index, families, count in (
        ("legacy", 0, 12, 60),
        ("development", 2, 12, 48),
        ("extra", 4, 8, 32),
    ):
        panel, gold = values[PHASE1_FILES[index]], values[PHASE1_FILES[index + 1]]
        cases = panel["cases"]
        jobs = {a["id"]: (c, a) for c in cases for a in c["answers"]}
        if (
            len(cases) != families
            or len({c["id"] for c in cases}) != families
            or len(jobs) != count
        ):
            raise ValueError("judge_controls_source_shape_invalid")
        if split == "legacy":
            positive, negative = gold["accepted"], gold["rejected"]
            if (
                len(set(positive)) != 24
                or len(negative) != 36
                or set(positive) & negative.keys()
                or set(positive) | negative.keys() != jobs.keys()
                or "J811" not in positive
            ):
                raise ValueError("judge_controls_source_shape_invalid")
        else:
            _verify_gold(cases, gold, jobs)


def build_controls(source: Path, output: Path, source_manifest_sha256: str) -> dict:
    """Create a separate immutable namespace; never read/copy held-out panel or gold."""
    source = source.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise ValueError("judge_controls_output_exists")
    if (
        output == source
        or output.is_relative_to(source)
        or source.is_relative_to(output)
    ):
        raise ValueError("judge_controls_output_overlaps_source")
    if digest(source / _MANIFEST) != source_manifest_sha256:
        raise ValueError("judge_controls_source_changed")
    manifest = _read(source / _MANIFEST)
    if manifest.get("status") != "frozen_before_any_inference":
        raise ValueError("judge_controls_source_not_frozen")
    values = {
        name: copy.deepcopy(_bound(source, name, manifest["files"][name]))
        for name in PHASE1_FILES
    }
    _validate_source(values)
    original = copy.deepcopy(values)
    before = {name: manifest["files"][name] for name in PHASE1_FILES}
    _repair_legacy(values[PHASE1_FILES[0]])
    _repair_extra(values[PHASE1_FILES[4]], values[PHASE1_FILES[5]])
    _repair_epistemic_gold(values[PHASE1_FILES[3]], values[PHASE1_FILES[5]])
    panels = {
        split: values[PHASE1_FILES[index]]
        for split, index in (("legacy", 0), ("development", 2), ("extra", 4))
    }
    contrasts, contrast_gold = contrast_controls()
    values.update(
        {"contrasts/panel.json": contrasts, "contrasts/gold.json": contrast_gold}
    )
    panels["contrasts"] = contrasts
    order = [
        {"split": split, "case_id": case["id"], "answer_id": answer["id"], "repeat": 1}
        for split, panel in panels.items()
        for case in panel["cases"]
        for answer in case["answers"]
    ]
    values["phase1-order.json"] = {"jobs": order}
    values["semantic-contract.json"] = {
        "control_version": VERSION,
        "known_facts": "Only explicit current user/source facts support a claim.",
        "non_implications": [
            "No cooling requirement does not imply cooling was not ordered.",
            "Pickup at someone's home does not identify who hands over the items.",
        ],
        "paraphrases": "Accept equivalent wording for the requested role, not a new role.",
        "epistemic_rule": (
            "If a criterion requires explicit lack of source information, an unsupported "
            "definite value omits that criterion and adds an unsupported claim. It does "
            "not prove a contradiction about the world. Explicit opposite source facts "
            "remain contradicted."
        ),
        "history": "Old source controls and gold remain unchanged and do not become PASS.",
        "changes": [
            "KOR-1 explicit issuer and person scope",
            "E02 explicit order and paraphrase",
            "D06/Q73853 owner and E07/X0703 price use explicit epistemic rule",
        ],
        "review_required": "Independent source review must be bound before first HTTP.",
    }
    output.mkdir(parents=True)
    for name, value in values.items():
        if name in original and value == original[name]:
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_source_bytes(source, name, before[name]))
        else:
            _write(output, name, value)
    values[_PROVENANCE] = {
        "source_manifest_sha256": source_manifest_sha256,
        "files": {
            name: {
                "source_sha256": before[name],
                "output_sha256": digest(output / name),
                "semantic_changed": values[name] != original[name],
            }
            for name in PHASE1_FILES
        },
        "holdout_content_read": False,
    }
    _write(output, _PROVENANCE, values[_PROVENANCE])
    result = {
        "schema_version": 1,
        "control_version": VERSION,
        "status": "frozen_before_any_inference",
        "files": {name: digest(output / name) for name in values},
        "thresholds": THRESHOLDS,
        "source_manifest_sha256": source_manifest_sha256,
        "source_files": before,
        "data_review_required": True,
        "holdout": {
            "source_directory": str(source / "holdout"),
            "files": {
                name: manifest["files"][f"holdout/{name}"]
                for name in ("panel.json", "gold.json")
            },
            "policy": "unopened_until_phase1_pass",
        },
    }
    _write(output, _MANIFEST, result)
    return result
