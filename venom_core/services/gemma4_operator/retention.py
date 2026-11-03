"""Freeze capability reserve into existing comparison cases with lexical oracles.

This converts authored diagnostic expectations, not independent semantic review.
It never runs inference, training, a judge, or a provider.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from .material import digest
from .paths import checked_directory, checked_file

Json = dict[str, Any]
MANIFEST_FILE = "manifest.json"
FAMILIES = {"summarization", "translation", "vision_retention"}
CONTRACTS = {
    "summarization": "semantic_fact_preservation_and_no_unsupported_claims_v1",
    "translation": "translation_meaning_negation_and_identifiers_v1",
    "vision_retention": "shape_color_count_from_grounded_pixels_v1",
}
SHAPES = {
    "square": r"(?:kwadrat\w*|square\w*)",
    "circle": r"(?:koł\w*|okrąg\w*|circle\w*)",
    "triangle": r"(?:trójkąt\w*|triangle\w*)",
    "rectangle": r"(?:prostokąt\w*|rectangle\w*)",
}
COLORS = {"red": r"(?:czerw\w*|red)", "blue": r"(?:niebies\w*|blue)"}
NUMERIC_LABELS = {
    "pending": r"(?:oczek\w*|pending)",
    "running": r"(?:aktyw\w*|running)",
    "completed": r"(?:ukończ\w*|zakończ\w*|completed|finished)",
}
SPECIAL_FACTS = {
    "action": ("DNS record restored", r"(?=.*\bDNS\b)(?=.*(?:przywró\w*|restor\w*))"),
    "root_cause_confirmed": (
        False,
        r"(?:nie.{0,25}potwierdz|not.{0,25}confirm|unconfirmed)",
    ),
    "budget_approved": (False, r"(?:nie.{0,25}zatwierdz|not.{0,25}approv|unapproved)"),
    "open_days": (
        "Tuesday-Sunday",
        r"(?:wtork\w*.{0,30}niedziel\w*|Tuesday.{0,30}Sunday)",
    ),
    "closed_day": ("Monday", r"(?:poniedział\w*|Monday)"),
}
FINISH = {
    "type": "function",
    "function": {
        "name": "Finish",
        "description": "Return the answer and finish the task",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["success", "needs_input", "failed"],
                },
                "summary": {"type": "string", "minLength": 1},
            },
            "required": ["status", "summary"],
            "additionalProperties": False,
        },
    },
}


def _need(value: Any, code: str) -> None:
    if not value:
        raise ValueError("gemma_retention_" + code)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _literal(value: Any) -> str:
    _need(isinstance(value, str) and 0 < len(value) <= 200, "fact_invalid")
    return r"(?<!\w)" + re.escape(value) + r"(?!\w)"


def _numeric(key: str, value: Any) -> str:
    _need(type(value) is int and 0 <= value <= 1000, "fact_invalid")
    number = r"\b" + str(value) + r"\b"
    label = NUMERIC_LABELS[key]
    return label + r"\D{0,30}" + number + "|" + number + r"\D{0,30}" + label


def _date(value: Any) -> str:
    match = (
        re.fullmatch(r"November (\d{1,2})", value) if isinstance(value, str) else None
    )
    if match is None:
        raise ValueError("gemma_retention_date_unsupported")
    day = str(int(match.group(1)))
    return r"(?:" + day + r"\s+listopad\w*|November\s+" + day + r"\b)"


def _summary_fact(key: str, value: Any) -> str:
    if key in {"service", "report_owner", "outage_start", "outage_end"}:
        return _literal(value)
    if key in NUMERIC_LABELS:
        return _numeric(key, value)
    if key in {"pilot_date", "report_date"}:
        return _date(value)
    if key in SPECIAL_FACTS:
        expected, pattern = SPECIAL_FACTS[key]
        _need(type(value) is type(expected) and value == expected, "fact_unsupported")
        return pattern
    return _other_summary_fact(key, value)


def _other_summary_fact(key: str, value: Any) -> str:
    if key == "cancelled":
        _need(type(value) is int and value == 0, "fact_unsupported")
        return r"(?:nie.{0,25}anul|no.{0,25}cancel|cancel\w*\D{0,10}0|anul\w*\D{0,10}0)"
    if key in {"opens", "closes"}:
        match = re.fullmatch(r"(\d{2}):00", value) if isinstance(value, str) else None
        if match is None:
            raise ValueError("gemma_retention_time_unsupported")
        return r"\b" + str(int(match.group(1))) + r"(?::00)?\b"
    if key == "adult_ticket_pln":
        _need(type(value) is int and value > 0, "fact_unsupported")
        return r"\b" + str(value) + r"\s*(?:zł|PLN)\b|\bPLN\s*" + str(value) + r"\b"
    raise ValueError("gemma_retention_fact_unsupported")


def _vision_patterns(facts: Json) -> list[str]:
    _need(set(facts) == {"shape", "color", "count"}, "vision_facts_invalid")
    shape, color, count = facts["shape"], facts["color"], facts["count"]
    _need(
        isinstance(shape, str)
        and shape in SHAPES
        and isinstance(color, str)
        and color in COLORS,
        "vision_facts_invalid",
    )
    _need(type(count) is int and count in (1, 2), "vision_facts_invalid")
    count_pattern = (
        r"\b(?:1|one|jeden|jedn\w*)\b"
        if count == 1
        else r"\b(?:2|two|dwa|dwie|dwóch)\b"
    )
    return [SHAPES[shape], COLORS[color], count_pattern]


def _translation_patterns(row: Json) -> list[str]:
    preserved = row.get("expected_preserved_strings")
    if not isinstance(preserved, list) or not 0 < len(preserved) <= 12:
        raise ValueError("gemma_retention_translation_facts_invalid")
    target = row.get("target_language")
    _need(
        isinstance(target, str) and target in {"pl", "en"},
        "translation_language_invalid",
    )
    patterns = [_literal(value) for value in preserved]
    reference = row.get("reference_translation")
    _need(
        isinstance(reference, str) and bool(reference), "translation_reference_required"
    )
    if "job-17" in preserved:
        patterns.extend(
            [
                r"(?:działa|running|operating|working)",
                r"(?:czeka|oczeku\w*|waiting|pending)",
            ]
        )
    if "config/runtime.json" in preserved:
        patterns.extend(
            [
                r"(?:nie.{0,25}(?:usuw|kasuj)|(?:do not|don't|never).{0,25}(?:delete|remove))",
                r"(?:zgod\w*|pozwolen\w*|permission|consent|approval)",
            ]
        )
    if any("false" in value for value in preserved):
        patterns.append(r"(?:nie.{0,25}potwierdz|not.{0,25}confirm|unconfirmed)")
    if "QX-204" in preserved:
        patterns.extend([r"(?:odjeżdż\w*|odjazd|leaves|departs)", r"(?:ważn\w*|valid)"])
    return patterns


def _patterns(row: Json) -> list[str]:
    family = row["family"]
    if family == "translation":
        return _translation_patterns(row)
    facts = row.get("expected_facts")
    if not isinstance(facts, dict) or not 0 < len(facts) <= 12:
        raise ValueError("gemma_retention_facts_required")
    if family == "vision_retention":
        return _vision_patterns(facts)
    return [_summary_fact(key, value) for key, value in facts.items()]


def _source_file(root: Path, name: Any) -> Path:
    _need(isinstance(name, str), "source_path_invalid")
    relative = PurePosixPath(name)
    _need(
        not relative.is_absolute() and ".." not in relative.parts, "source_path_invalid"
    )
    path = checked_directory(root / relative.parent) / relative.name
    _need(
        not path.is_symlink() and path.is_file() and path.stat().st_size <= 2 * 1024**2,
        "source_file_invalid",
    )
    return path


def _source(root: Path) -> tuple[list[Json], Json, Json]:
    manifest_path = checked_file(root / MANIFEST_FILE)
    _need(manifest_path.stat().st_size <= 8 * 1024**2, "source_manifest_too_large")
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest)
    _need(isinstance(manifest, dict), "source_manifest_invalid")
    reserve = manifest.get("capability_reserve")
    _need(
        isinstance(reserve, dict) and reserve.get("included_in_training") is False,
        "reserve_required",
    )
    _need(isinstance(reserve.get("assets"), dict), "assets_required")
    path = _source_file(root, reserve.get("path"))
    raw = path.read_bytes()
    _need(_hash(raw) == reserve.get("sha256"), "source_hash_mismatch")
    rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    _need(
        0 < len(rows) <= 512 and all(isinstance(row, dict) for row in rows),
        "source_count_mismatch",
    )
    _need(all(isinstance(row.get("id"), str) for row in rows), "case_id_invalid")
    _need(
        len(rows) == reserve.get("rows")
        and [row.get("id") for row in rows] == reserve.get("case_ids"),
        "source_count_mismatch",
    )
    _need(
        len({row.get("id") for row in rows}) == len(rows) and bool(rows),
        "source_count_mismatch",
    )
    identity = {
        "corpus_manifest_sha256": _hash(raw_manifest),
        "capability_sha256": _hash(raw),
        "source_manifest": str(manifest_path),
    }
    return rows, reserve, identity


def _case_identity(row: Json) -> tuple[str, str, str]:
    _need(isinstance(row, dict), "case_invalid")
    ident, family, language = (row.get(key) for key in ("id", "family", "language"))
    if not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9_-]{1,80}", ident):
        raise ValueError("gemma_retention_case_id_invalid")
    if (
        not isinstance(family, str)
        or family not in FAMILIES
        or not isinstance(language, str)
        or language not in {"pl", "en"}
    ):
        raise ValueError("gemma_retention_case_family_invalid")
    _need(
        isinstance(row.get("problem_group"), str) and bool(row["problem_group"]),
        "problem_group_required",
    )
    _need(
        row.get("training_allowed") is False
        and row.get("split") == "capability_holdout"
        and row.get("model_evaluated") is False,
        "reserve_policy_invalid",
    )
    _need(
        row.get("verifier_contract") == CONTRACTS[family], "source_contract_unsupported"
    )
    return ident, family, language


def _case(row: Json) -> Json:
    ident, family, language = _case_identity(row)
    prompt = row.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        raise ValueError("gemma_retention_prompt_required")
    if family != "vision_retention":
        _need(
            isinstance(row.get("input"), str) and bool(row["input"]), "input_required"
        )
        prompt += "\n\n" + row["input"]
    patterns = _patterns(row)
    for pattern in patterns:
        re.compile(pattern, re.IGNORECASE)
    return {
        "id": ident,
        "problem_group": row["problem_group"],
        "family": family,
        "language": language,
        "system": "Answer in "
        + ("Polish" if language == "pl" else "English")
        + ". Use Finish once; put the answer in summary. Use only the supplied input or attached image.",
        "prompt": prompt,
        "fixture": "fixtures/" + ident,
        "tools": [FINISH],
        "mutable_files": [],
        "oracle": {
            "status": "success",
            "no_terminal": True,
            "summary_regexes": patterns,
            "mutable_files": [],
        },
        "source_record_sha256": digest(row),
        "verifier_contract": "bounded_lexical_capability_checks_v1",
    }


def _image(row: Json, case: Json, source: Path, reserve: Json, target: Path) -> None:
    if row["family"] != "vision_retention":
        return
    _need(row.get("requires_multimodal_processor") is True, "image_processor_required")
    name, checksum = row.get("image"), row.get("image_sha256")
    _need(
        isinstance(name, str)
        and PurePosixPath(name).name == name
        and reserve.get("assets", {}).get(name) == checksum,
        "image_not_frozen",
    )
    image = _source_file(source / "capability-reserve", name)
    raw = image.read_bytes()
    _need(
        _hash(raw) == checksum and raw.startswith(b"\x89PNG\r\n\x1a\n"),
        "image_hash_mismatch",
    )
    destination = case["fixture"] + "/image.png"
    (target / destination).write_bytes(raw)
    case["images"] = [{"path": destination, "sha256": checksum}]


def prepare_retention_cases(
    corpus_root: Path, output: Path, *, sandbox_image: str
) -> Path:
    """Atomically freeze existing authored reserve for the shared GPU comparison flow."""
    _need(
        isinstance(sandbox_image, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", sandbox_image),
        "sandbox_image_unpinned",
    )
    root = checked_directory(corpus_root)
    destination = checked_file(output / MANIFEST_FILE, output=True).parent
    if destination.exists():
        raise FileExistsError("gemma_retention_output_exists")
    rows, reserve, identity = _source(root)
    cases = [_case(row) for row in rows]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".retention-stage-", dir=destination.parent
    ) as temporary:
        stage = Path(temporary) / "ready"
        stage.mkdir()
        for row, case in zip(rows, cases, strict=True):
            folder = stage / case["fixture"]
            folder.mkdir(parents=True)
            (folder / ".keep").write_text("", encoding="utf-8")
            _image(row, case, root, reserve, stage)
        (stage / "cases.jsonl").write_text(
            "".join(
                json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n"
                for case in cases
            ),
            encoding="utf-8",
        )
        files = {
            p.relative_to(stage).as_posix(): _hash(p.read_bytes())
            for p in sorted(stage.rglob("*"))
            if p.is_file()
        }
        manifest = {
            "schema_version": 1,
            "cases": "cases.jsonl",
            "case_count": len(cases),
            "files": files,
            "sandbox_image": sandbox_image,
            "source": identity,
            "training_allowed": False,
            "model_evaluated": False,
            "model_neutral": True,
            "shared_preprocessed_tensors": False,
            "independent_final_benchmark": False,
            "diagnostic_requires_serial_comparison": True,
            "verifier_contract": "bounded_lexical_capability_checks_v1",
            "limitations": [
                "Lexical patterns do not establish full semantic equivalence, fluency or absence of unsupported claims",
                "Authored reserve is diagnostic and has no independent human review",
                "No audio qualification",
            ],
            "qualification": {
                "status": "PASS",
                "scope": "oracle_contract_only_cpu",
                "model_qualified": False,
            },
        }
        (stage / MANIFEST_FILE).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        from scripts.granite_operator.comparison_support import load_frozen

        load_frozen(stage / MANIFEST_FILE)
        stage.rename(destination)
    return destination / MANIFEST_FILE
