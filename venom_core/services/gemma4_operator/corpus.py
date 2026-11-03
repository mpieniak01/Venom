"""Versioned G05 material from immutable G04 and real isolated Venom tool calls.

The extra demonstrations are authored CPU fixtures, not model generations or
human-reviewed production incidents. Native token masks and model qualification
remain separate. Network access is blocked in the fixture subprocess.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from typing import Any

from .material import SHA256, digest, prepare_material
from .paths import checked_directory, checked_file
from .profile import GemmaProfile

Json = dict[str, Any]
G04_FILES = {
    "train": (
        "domain/train.jsonl",
        "f7d8ddc26512b041d8af018f4997286a46bfbb93732a19b59833a7528ff4e9e9",
    ),
    "validation": (
        "domain/validation.jsonl",
        "03be3686d20df60c1c9b7312cc606aa07e17aadb522d1124dd350fc8aaa4dd8c",
    ),
    "holdout": (
        "holdout/conversations.jsonl",
        "59938ec2ca0b0941ff1fd081eb9cf2f92765752989ca7132a3a05489357dbc76",
    ),
}
FAMILIES = (
    "service_binding",
    "log_diagnosis",
    "clarify_then_apply",
    "direct_apply",
    "recover_missing_file",
    "bounded_plan_verify",
)
DEFAULT_GROUPS = {"train": 16, "validation": 4, "holdout": 4}
SPLIT_WORDS = {"train": "cedar", "validation": "maple", "holdout": "birch"}
CORPUS_RECIPE_VERSION = 2
EXPERIMENT_MODELS = frozenset({"google/gemma-4-E4B-it", "google/gemma-4-12B-it"})
TOOL_NAMES = (
    "FileSkill-read_file",
    "FileSkill-write_file",
    "FileSkill-list_files",
    "FileSkill-file_exists",
)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n"


def _bytes_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _groups(value: Json) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(DEFAULT_GROUPS):
        raise ValueError("gemma_corpus_groups_invalid")
    if any(
        type(number) is not int or not 1 <= number <= 64 for number in value.values()
    ):
        raise ValueError("gemma_corpus_group_budget_invalid")
    return value


def _parent(source: Path) -> tuple[dict[str, list[Json]], Json]:
    root = checked_directory(source)
    manifest_path = root / "pilot-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("gemma_corpus_parent_manifest_required")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("material_version") != 4:
        raise ValueError("gemma_corpus_parent_version_invalid")
    rows, hashes = {}, {}
    for split, (name, expected) in G04_FILES.items():
        path = root / name
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("gemma_corpus_parent_symlink")
        raw = path.read_bytes()
        declared = (
            manifest["holdout"] if split == "holdout" else manifest["datasets"][name]
        )
        if _bytes_hash(raw) != expected or declared.get("sha256") != expected:
            raise ValueError("gemma_corpus_parent_hash_mismatch")
        data = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
        if len(data) != declared.get("rows"):
            raise ValueError("gemma_corpus_parent_count_mismatch")
        rows[split], hashes[name] = data, expected
    prepare_material(rows)
    return rows, {
        "material_version": 4,
        "manifest_sha256": _bytes_hash(manifest_path.read_bytes()),
        "files": hashes,
        "included_once": True,
        "hf_mixed": False,
    }


def _snapshot(root: Path) -> dict[str, str]:
    files = [path for path in root.rglob("*") if path.is_file()]
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("gemma_corpus_fixture_symlink")
    return {
        path.relative_to(root).as_posix(): _bytes_hash(path.read_bytes())
        for path in files
    }


def _fixture(root: Path, service: str, index: int) -> tuple[str, str, Json]:
    target = f"services/{service}/settings.json"
    report = f"reports/{service}.json"
    truth = {"enabled": True, "route": f"/v2/{service}", "service": service}
    files = {
        target: _json(
            {"enabled": False, "route": f"/old/{service}", "service": service}
        ),
        "catalog/services.json": _json({service: truth}),
        f"observations/{service}.txt": "\n".join(
            [f"service={service} status=error event=connection"] * (index % 3 + 1)
            + [
                f"service={service} status=ok event=recovered",
                "service=unrelated status=error",
            ]
        )
        + "\n",
        "protected/policy.txt": "Only the named service settings and report may change.\n",
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return target, report, truth


def _prompt(family: str, service: str, target: str, language: str) -> str:
    batch = _bytes_hash(("batch:" + service).encode())[:16]
    prompts = {
        "service_binding": (
            f"Sprawdź mapę serwisów i napraw konfigurację {service}; zweryfikuj zapis.",
            f"Inspect the service map and repair {service} configuration; verify the saved state.",
        ),
        "log_diagnosis": (
            f"Policz błędy wyłącznie serwisu {service} i zapisz raport JSON, bez zmiany konfiguracji.",
            f"Count errors for service {service} only and save a JSON report without changing configuration.",
        ),
        "clarify_then_apply": (
            f"Chcę uzgodnić konfigurację serwisu z mapą, ale nie podałem nazwy; identyfikator partii {batch}.",
            f"I want service configuration aligned with the map but have not named the service; batch identifier {batch}.",
        ),
        "direct_apply": (
            f"Dla {service} uzgodnij plik {target} z catalog/services.json i sprawdź wynik.",
            f"For {service}, align {target} with catalog/services.json and check the result.",
        ),
        "recover_missing_file": (
            f"Status {service} był pod legacy/{service}.json; znajdź aktualny plik i zapisz raport.",
            f"The {service} status used to be under legacy/{service}.json; find the current file and save a report.",
        ),
        "bounded_plan_verify": (
            f"Zaplanuj krótką diagnostykę {service}, popraw tylko wskazany serwis i sprawdź brak innych zmian.",
            f"Plan a short diagnosis of {service}, fix only that service and verify no other changes.",
        ),
    }
    return prompts[family][language == "en"]


class _Transcript:
    def __init__(self, tools: dict[str, Any], specs: list[Json], prompt: str):
        self.tools = tools
        self.specs = specs
        self.messages: list[Json] = [{"role": "user", "content": prompt}]
        self.targets: list[int] = []
        self.context: list[int] = []
        self.receipts: list[Json] = []

    def assistant(self, text: str) -> None:
        self.targets.append(len(self.messages))
        self.messages.append({"role": "assistant", "content": text})

    async def call(
        self, name: str, arguments: Json, *, failed_context: bool = False
    ) -> str:
        ident = f"call-{len(self.receipts)}"
        index = len(self.messages)
        self.messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": ident,
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                ],
            }
        )
        outcome = self.tools[name].func(**arguments)
        result = await outcome if inspect.isawaitable(outcome) else outcome
        if not isinstance(result, str):
            raise ValueError("gemma_corpus_actual_tool_result_not_text")
        is_error = result.startswith(("❌", "⛔"))
        if is_error != failed_context:
            raise ValueError("gemma_corpus_unexpected_tool_outcome")
        self.messages.append(
            {"role": "tool", "tool_call_id": ident, "name": name, "content": result}
        )
        (self.context if failed_context else self.targets).append(index)
        self.receipts.append(
            {
                "call_id": ident,
                "name": name,
                "arguments_sha256": digest(arguments),
                "result_sha256": digest(result),
                "observed_error": is_error,
            }
        )
        return result


def _actual_tools(workspace: Path) -> tuple[dict[str, Any], list[Json]]:
    from venom_core.execution.maf_runtime import AgentRuntime
    from venom_core.execution.skills.file_skill import FileSkill

    runtime = AgentRuntime(
        permission_checker=lambda name: name in {"FileSkill", "FileReadSkill"}
    )
    runtime.add_plugin(FileSkill(str(workspace)), "FileSkill")
    tools = {
        tool.name: tool
        for tool in runtime.native_tools({"included_functions": list(TOOL_NAMES)})
    }
    if set(tools) != set(TOOL_NAMES):
        raise ValueError("gemma_corpus_actual_catalog_mismatch")
    specs = [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters(),
            },
        }
        for tool in tools.values()
    ]
    return tools, specs


async def _scenario(
    family: str, split: str, index: int, language: str, root: Path
) -> tuple[Json, Json]:
    service = f"{SPLIT_WORDS[split]}-{family.replace('_', '-')}-{index:02d}"
    workspace = root / f"{service}-{language}"
    workspace.mkdir()
    target, report, truth = _fixture(workspace, service, index)
    before = _snapshot(workspace)
    tools, specs = _actual_tools(workspace)
    transcript = _Transcript(tools, specs, _prompt(family, service, target, language))
    if family == "clarify_then_apply":
        transcript.assistant(
            "Który serwis mam uzgodnić?"
            if language == "pl"
            else "Which service should I align?"
        )
        transcript.messages.append({"role": "user", "content": f"{service}; {target}"})
    if family == "bounded_plan_verify":
        transcript.assistant(
            "Odczytam mapę, zmienię jeden plik i sprawdzę wynik."
            if language == "pl"
            else "I will read the map, change one file, and verify the result."
        )
    if family == "recover_missing_file":
        await transcript.call(
            "FileSkill-read_file",
            {"file_path": f"legacy/{service}.json"},
            failed_context=True,
        )
    await transcript.call(
        "FileSkill-list_files",
        {"directory": "services", "recursive": True, "max_depth": 3},
    )
    await transcript.call("FileSkill-file_exists", {"file_path": target})
    observed = json.loads(
        await transcript.call("FileSkill-read_file", {"file_path": target})
    )
    expected = before.copy()
    if family in {"log_diagnosis", "recover_missing_file"}:
        log = await transcript.call(
            "FileSkill-read_file", {"file_path": f"observations/{service}.txt"}
        )
        result = {
            "service": service,
            "error_count": sum(
                line.startswith(f"service={service} ") and "status=error" in line
                for line in log.splitlines()
            ),
            "enabled": observed["enabled"],
        }
        await transcript.call(
            "FileSkill-write_file", {"file_path": report, "content": _json(result)}
        )
        expected[report] = _bytes_hash(
            _json(
                {"service": service, "error_count": index % 3 + 1, "enabled": False}
            ).encode()
        )
        written = await transcript.call("FileSkill-read_file", {"file_path": report})
        if json.loads(written) != result:
            raise ValueError("gemma_corpus_tool_readback_mismatch")
    else:
        catalog = json.loads(
            await transcript.call(
                "FileSkill-read_file", {"file_path": "catalog/services.json"}
            )
        )
        await transcript.call(
            "FileSkill-write_file",
            {"file_path": target, "content": _json(catalog[service])},
        )
        expected[target] = _bytes_hash(_json(truth).encode())
        await transcript.call("FileSkill-read_file", {"file_path": target})
    after = _snapshot(workspace)
    if after != expected:
        raise ValueError("gemma_corpus_independent_state_check_failed")
    transcript.assistant(
        "Gotowe; wynik zapisany i sprawdzony, pozostałe pliki bez zmian."
        if language == "pl"
        else "Done; the saved result was verified and all other files are unchanged."
    )
    ident = f"g05-{split}-{family}-{index:02d}-{language}"
    record = {
        "record_id": ident,
        "problem_group": f"g05:{split}:{family}:{index}",
        "language": language,
        "split": split,
        "training_allowed": split == "train",
        "source_kind": "synthetic",
        "messages": transcript.messages,
        "tools": specs,
        "supervised_assistant_indices": transcript.targets,
        "context_only_assistant_indices": transcript.context,
        "lineage": {
            "recipe": "venom-g05-cpu-v2",
            "fixture_kind": "authored_not_model_generated",
            "independent_human_review": False,
        },
    }
    receipt = {
        "record_id": ident,
        "trajectory_sha256": digest({"messages": record["messages"], "tools": specs}),
        "tools_sha256": digest(specs),
        "actual_tool_calls": transcript.receipts,
        "fixture_before_sha256": digest(before),
        "fixture_after_sha256": digest(after),
        "expected_state_sha256": digest(expected),
        "independent_state_check": "passed",
        "policy_scope": "isolated_subprocess_fixture_only",
        "network_blocked": True,
        "independent_human_review": False,
        "model_evaluated": False,
    }
    return record, receipt


def _deny_network(*args: Any, **kwargs: Any) -> Any:
    raise PermissionError("gemma_corpus_fixture_network_disabled")


async def _generate(root: Path, groups: dict[str, int]) -> Json:
    # Imports happen after the worker's private memory root is installed.
    from venom_core.core.permission_guard import permission_guard

    if permission_guard._state_manager is not None:
        raise ValueError("gemma_corpus_fixture_must_not_have_live_state")
    if not permission_guard.set_level(30):
        raise ValueError("gemma_corpus_fixture_write_permission_unavailable")
    splits: dict[str, list[Json]] = {split: [] for split in groups}
    receipts = []
    for split, count in groups.items():
        for family in FAMILIES:
            for index in range(count):
                for language in ("pl", "en"):
                    row, receipt = await _scenario(family, split, index, language, root)
                    splits[split].append(row)
                    receipts.append(receipt)
    prepare_material(splits)
    return {"splits": splits, "receipts": receipts}


def _worker(root: Path, groups: dict[str, int]) -> None:
    os.environ["MEMORY_ROOT"] = str(root / "memory")
    os.environ["VENOM_LOG_DIR"] = str(root / "logs")
    os.environ["VENOM_RUNTIME_STATE_ROOT"] = str(root / "runtime")
    setattr(socket.socket, "connect", _deny_network)
    setattr(socket.socket, "connect_ex", _deny_network)
    setattr(socket, "create_connection", _deny_network)
    setattr(socket, "getaddrinfo", _deny_network)
    result = asyncio.run(_generate(root, groups))
    with (root / "generated.json").open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False)


def _supplement(groups: dict[str, int]) -> Json:
    with tempfile.TemporaryDirectory(prefix="gemma-g05-") as directory:
        root = Path(directory).resolve(strict=True)
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[3])
        result = subprocess.run(
            [sys.executable, "-m", __name__, "--worker", str(root), json.dumps(groups)],
            cwd=Path(__file__).resolve().parents[3],
            env=environment,
            capture_output=True,
            timeout=300,
            check=False,
        )
        if result.returncode:
            raise ValueError("gemma_corpus_fixture_subprocess_failed")
        return json.loads((root / "generated.json").read_text())


def _execution_sources() -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    names = (
        "venom_core/services/gemma4_operator/corpus.py",
        "venom_core/execution/skills/file_skill.py",
        "venom_core/execution/skills/base_skill.py",
        "venom_core/execution/maf_runtime.py",
        "venom_core/core/permission_guard.py",
        "venom_core/core/autonomy_enforcement.py",
        "venom_core/execution/agent_contracts.py",
        "config/autonomy_matrix.yaml",
        "config/skill_permissions.yaml",
    )
    return {name: _bytes_hash((root / name).read_bytes()) for name in names}


def prepare_corpus(source_root: Path, *, groups: Json | None = None) -> Json:
    """Execute new fixture demonstrations and retain the frozen G04 exactly once."""
    budget = _groups(DEFAULT_GROUPS.copy() if groups is None else groups)
    parent, lineage = _parent(source_root)
    recipe_hash = _bytes_hash(Path(__file__).read_bytes())
    execution_sources = _execution_sources()
    supplement = _supplement(budget)
    if _bytes_hash(Path(__file__).read_bytes()) != recipe_hash:
        raise ValueError("gemma_corpus_recipe_changed_during_execution")
    if _execution_sources() != execution_sources:
        raise ValueError("gemma_corpus_execution_sources_changed")
    root = checked_directory(source_root)
    if (
        _bytes_hash((root / "pilot-manifest.json").read_bytes())
        != lineage["manifest_sha256"]
    ):
        raise ValueError("gemma_corpus_parent_changed_during_execution")
    for name, checksum in lineage["files"].items():
        if _bytes_hash((root / name).read_bytes()) != checksum:
            raise ValueError("gemma_corpus_parent_changed_during_execution")
    lineage["recipe_sha256"] = recipe_hash
    lineage["source_files_unchanged"] = True
    lineage["execution_sources"] = execution_sources
    splits = {
        split: copy.deepcopy(parent[split]) + supplement["splits"][split]
        for split in parent
    }
    prepared = prepare_material(splits)
    return {
        "prepared": prepared,
        "execution_receipts": supplement["receipts"],
        "lineage": lineage,
        "supplement": {
            "groups_per_family": budget,
            "families": list(FAMILIES),
            "records": {split: len(supplement["splits"][split]) for split in parent},
            "kind": "authored_bilingual_cpu_fixtures",
            "independent_final_benchmark": False,
            "independent_human_review": False,
        },
    }


def _write_lines(path: Path, rows: list[Json]) -> None:
    with path.open("x") as stream:
        for row in rows:
            stream.write(_json(row))


def _inside_shape(shape: str, x: int, y: int) -> bool:
    if shape == "circle":
        return x * x + y * y <= 9 * 9
    if shape == "triangle":
        return -9 <= y < 10 and abs(x) <= (y + 9) // 2
    if shape == "rectangle":
        return abs(x) < 12 and abs(y) < 7
    return abs(x) < 10 and abs(y) < 10


def _png_fixture(shape: str, rgb: tuple[int, int, int], count: int) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))
        )

    centers = (24,) if count == 1 else (15, 48)
    width = 48 if count == 1 else 64
    rows = []
    for y in range(48):
        pixels = bytearray()
        for x in range(width):
            colored = any(
                _inside_shape(shape, x - center, y - 24) for center in centers
            )
            pixels.extend(rgb if colored else (255, 255, 255))
        rows.append(b"\x00" + bytes(pixels))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, 48, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


def _png_rectangle(red: int, green: int, blue: int) -> bytes:
    return _png_fixture("square", (red, green, blue), 1)


def _reserve_case(ident: str, family: str, language: str) -> Json:
    return {
        "id": ident,
        "problem_group": "capability-v2:" + ident.rsplit("-", 1)[0],
        "family": family,
        "language": language,
        "split": "capability_holdout",
        "training_allowed": False,
        "model_evaluated": False,
        "reference_kind": "authored_not_independently_human_reviewed",
    }


def _summary_cases() -> list[Json]:
    sources = (
        (
            "Serwis atlas: oczekujące=3, aktywne=2, ukończone=7. Nie anulowano żadnego zadania.",
            "Service atlas: pending=3, running=2, completed=7. No tasks were cancelled.",
            {
                "service": "atlas",
                "pending": 3,
                "running": 2,
                "completed": 7,
                "cancelled": 0,
            },
        ),
        (
            "API nie odpowiadało od 09:15 do 09:22. Przywrócono rekord DNS. Przyczyny nie potwierdzono.",
            "The API was unavailable from 09:15 to 09:22. A DNS record was restored. The cause was not confirmed.",
            {
                "outage_start": "09:15",
                "outage_end": "09:22",
                "action": "DNS record restored",
                "root_cause_confirmed": False,
            },
        ),
        (
            "Na spotkaniu ustalono próbę pilotażową 14 listopada. Anna dostarczy raport 12 listopada. Budżetu jeszcze nie zatwierdzono.",
            "The meeting agreed on a pilot on November 14. Anna will deliver the report on November 12. The budget has not been approved.",
            {
                "pilot_date": "November 14",
                "report_owner": "Anna",
                "report_date": "November 12",
                "budget_approved": False,
            },
        ),
        (
            "Muzeum jest otwarte od wtorku do niedzieli w godzinach 10–18. W poniedziałki jest zamknięte. Bilet dla dorosłych kosztuje 20 zł.",
            "The museum opens Tuesday through Sunday, 10:00–18:00. It is closed on Mondays. An adult ticket costs PLN 20.",
            {
                "open_days": "Tuesday-Sunday",
                "opens": "10:00",
                "closes": "18:00",
                "closed_day": "Monday",
                "adult_ticket_pln": 20,
            },
        ),
    )
    rows = []
    for language in ("pl", "en"):
        for index, (polish, english, facts) in enumerate(sources):
            row = _reserve_case(
                f"summary-{index}-{language}", "summarization", language
            )
            row.update(
                input=polish if language == "pl" else english,
                prompt="Podsumuj kluczowe fakty bez dodawania przypuszczeń."
                if language == "pl"
                else "Summarize the key facts without adding assumptions.",
                expected_facts=facts,
                verifier_contract="semantic_fact_preservation_and_no_unsupported_claims_v1",
            )
            rows.append(row)
    return rows


def _translation_cases() -> list[Json]:
    sources = (
        (
            "Serwis atlas działa, ale zadanie job-17 czeka na dane.",
            "The atlas service is running, but job-17 is waiting for input.",
            ["atlas", "job-17"],
        ),
        (
            "Nie usuwaj pliku config/runtime.json bez zgody operatora.",
            "Do not delete config/runtime.json without the operator's permission.",
            ["config/runtime.json"],
        ),
        (
            'Odpowiedź zawiera {"ready": false}; nie potwierdzono gotowości.',
            'The response contains {"ready": false}; readiness has not been confirmed.',
            ['{"ready": false}'],
        ),
        (
            "Pociąg odjeżdża o 08:45 z peronu 3; rezerwacja QX-204 pozostaje ważna.",
            "The train leaves at 08:45 from platform 3; reservation QX-204 remains valid.",
            ["08:45", "3", "QX-204"],
        ),
    )
    rows = []
    for language in ("pl", "en"):
        for index, (polish, english, preserve) in enumerate(sources):
            row = _reserve_case(
                f"translation-{index}-{language}", "translation", language
            )
            row.update(
                input=polish if language == "pl" else english,
                prompt="Przetłumacz na angielski, zachowując identyfikatory i znaczenie."
                if language == "pl"
                else "Translate into Polish and preserve identifiers and meaning.",
                reference_translation=english if language == "pl" else polish,
                expected_preserved_strings=preserve,
                target_language="en" if language == "pl" else "pl",
                verifier_contract="translation_meaning_negation_and_identifiers_v1",
            )
            rows.append(row)
    return rows


def _vision_cases(root: Path) -> list[Json]:
    rows = []
    for shape in ("square", "circle", "triangle", "rectangle"):
        for language, color, rgb, count in (
            ("pl", "red", (255, 0, 0), 1),
            ("en", "blue", (0, 0, 255), 2),
        ):
            ident = f"vision-{shape}-{color}-{language}"
            image = root / (ident + ".png")
            image.write_bytes(_png_fixture(shape, rgb, count))
            row = _reserve_case(ident, "vision_retention", language)
            row.update(
                prompt="Opisz kształt, kolor i liczbę figur na białym tle."
                if language == "pl"
                else "Describe the shape, color and number of figures on the white background.",
                image=image.name,
                image_sha256=_bytes_hash(image.read_bytes()),
                expected_facts={"shape": shape, "color": color, "count": count},
                reference_kind="deterministic_pixel_fixture",
                verifier_contract="shape_color_count_from_grounded_pixels_v1",
                requires_multimodal_processor=True,
            )
            rows.append(row)
    return rows


def _capability_reserve(target: Path) -> Json:
    root = target / "capability-reserve"
    root.mkdir()
    rows = _summary_cases() + _translation_cases() + _vision_cases(root)
    path = root / "cases.jsonl"
    _write_lines(path, rows)
    return {
        "schema_version": 2,
        "path": "capability-reserve/cases.jsonl",
        "rows": len(rows),
        "case_ids": [row["id"] for row in rows],
        "sha256": _bytes_hash(path.read_bytes()),
        "assets": {
            path.name: _bytes_hash(path.read_bytes())
            for path in sorted(root.glob("*.png"))
        },
        "families": {"summarization": 8, "translation": 8, "vision_retention": 8},
        "included_in_training": False,
        "kind": "authored_capability_regression_samples",
        "model_neutral": True,
        "shared_preprocessed_tensors": False,
        "independent_final_benchmark": False,
        "model_evaluated": False,
        "audio_qualified": False,
        "audio_status": "unqualified_no_reviewed_licensed_asset",
        "vision_training_performed": False,
    }


def _previous_release(path: Path, lineage: Json) -> Json:
    target = checked_file(path)
    previous = json.loads(target.read_text())
    if (
        previous.get("material_version") != 5
        or previous.get("lineage", {}).get("files") != lineage["files"]
    ):
        raise ValueError("gemma_corpus_previous_release_mismatch")
    checksum = previous.get("files", {}).get("prepared.json", {}).get("sha256")
    if not isinstance(checksum, str) or SHA256.fullmatch(checksum) is None:
        raise ValueError("gemma_corpus_previous_release_invalid")
    prepared = checked_file(target.parent / "prepared.json")
    if _bytes_hash(prepared.read_bytes()) != checksum:
        raise ValueError("gemma_corpus_previous_prepared_changed")
    return {
        "manifest_sha256": _bytes_hash(target.read_bytes()),
        "prepared_sha256": checksum,
        "recipe_sha256": previous["lineage"].get("recipe_sha256"),
    }


def evaluation_definition(
    manifest: Json,
    *,
    profiles: dict[str, GemmaProfile],
    precisions: tuple[str, ...] = ("nf4", "bf16"),
) -> Json:
    """Define matched experiments; this contains no model trials or results.

    Canonical problems and assets are shared. Rendering, tokenization, adapters,
    runtime identities and paired comparisons stay inside each exact variant.
    """
    from .evaluation import COMMON

    if set(profiles) != EXPERIMENT_MODELS:
        raise ValueError("gemma_corpus_evaluation_models_required")
    if (
        not precisions
        or len(set(precisions)) != len(precisions)
        or any(p not in {"nf4", "bf16"} for p in precisions)
    ):
        raise ValueError("gemma_corpus_evaluation_precision_invalid")
    reserve = manifest.get("capability_reserve")
    if (
        not isinstance(reserve, dict)
        or reserve.get("model_neutral") is not True
        or reserve.get("shared_preprocessed_tensors") is not False
    ):
        raise ValueError("gemma_corpus_capability_manifest_invalid")
    checksum = reserve.get("sha256")
    if not isinstance(checksum, str) or SHA256.fullmatch(checksum) is None:
        raise ValueError("gemma_corpus_capability_hash_required")
    case_ids = reserve.get("case_ids")
    if (
        not isinstance(case_ids, list)
        or not case_ids
        or any(not isinstance(ident, str) or not ident for ident in case_ids)
        or len(set(case_ids)) != len(case_ids)
    ):
        raise ValueError("gemma_corpus_capability_cases_invalid")
    comparisons = []
    for model, profile in sorted(profiles.items()):
        profile.validate()
        if profile.model != model:
            raise ValueError("gemma_corpus_evaluation_profile_mismatch")
        for precision in precisions:
            comparisons.append(
                {
                    "model": model,
                    "revision": profile.revision,
                    "profile_sha256": digest(profile.identity()),
                    "benchmark_sha256": checksum,
                    "requested_precision": precision,
                    "arms": [
                        {
                            "arm": "base",
                            "adapter_sha256": None,
                            "model": model,
                            "profile_sha256": digest(profile.identity()),
                        },
                        {
                            "arm": "adapter",
                            "adapter_sha256_required": True,
                            "model": model,
                            "profile_sha256": digest(profile.identity()),
                        },
                    ],
                    "required_matched_actual_fields": list(COMMON),
                    "requested_equals_effective_precision_required": True,
                    "same_variant_required": True,
                    "same_problem_ids_required": True,
                    "status": "NOT_RUN",
                }
            )
    return {
        "schema_version": 1,
        "kind": "gemma_capability_evaluation_definition",
        "status": "PLANNED_NOT_EXECUTED",
        "material_manifest_sha256": digest(manifest),
        "canonical_case_ids": reserve["case_ids"],
        "canonical_cases_sha256": checksum,
        "comparisons": comparisons,
        "cross_variant_paired_accuracy_allowed": False,
        "variant_specific_preprocessing_required": True,
        "model_evaluated": False,
        "audio_qualified": False,
        "promotion_authorized": False,
        "activation_authorized": False,
    }


def build_corpus(
    source_root: Path,
    output: Path,
    *,
    groups: Json | None = None,
    previous_manifest: Path | None = None,
) -> Json:
    """Create a new private immutable release; never alter historical source files."""
    if output.exists():
        raise FileExistsError("gemma_corpus_output_exists")
    # Restrict the destination to the same operator-approved data directories.
    parent = checked_directory(output.parent)
    target = parent / output.name
    if output.name in {"", ".", ".."} or target.is_symlink():
        raise ValueError("gemma_corpus_output_path_invalid")
    result = prepare_corpus(source_root, groups=groups)
    if previous_manifest is not None:
        result["lineage"]["previous_g05"] = _previous_release(
            previous_manifest, result["lineage"]
        )
    recipe = Path(__file__).read_bytes()
    if _bytes_hash(recipe) != result["lineage"]["recipe_sha256"]:
        raise ValueError("gemma_corpus_recipe_changed_before_export")
    target.mkdir()
    recipes = target / "recipes"
    recipes.mkdir()
    (recipes / "corpus.py").write_bytes(recipe)
    files: dict[str, Json] = {
        "recipes/corpus.py": {
            "sha256": _bytes_hash(recipe),
            "kind": "executed_recipe_source",
        }
    }
    for split, rows in result["prepared"]["records"].items():
        path = target / (split + ".jsonl")
        _write_lines(path, rows)
        files[path.name] = {"rows": len(rows), "sha256": _bytes_hash(path.read_bytes())}
    prepared_path = target / "prepared.json"
    with prepared_path.open("x") as stream:
        json.dump(
            result["prepared"],
            stream,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
    files[prepared_path.name] = {
        "sha256": _bytes_hash(prepared_path.read_bytes()),
        "contains_holdout": True,
    }
    receipts = target / "execution-receipts.jsonl"
    _write_lines(receipts, result["execution_receipts"])
    files[receipts.name] = {
        "rows": len(result["execution_receipts"]),
        "sha256": _bytes_hash(receipts.read_bytes()),
    }
    manifest = {
        "schema_version": 1,
        "material_version": 5,
        "corpus_recipe_version": CORPUS_RECIPE_VERSION,
        "status": "CPU_EXECUTED_MATERIAL",
        "lineage": result["lineage"],
        "supplement": result["supplement"],
        "files": files,
        "prepared_manifest": result["prepared"]["manifest"],
        "capability_reserve": _capability_reserve(target),
        "training_started": False,
        "model_loaded": False,
        "independent_human_review": False,
        "holdout_qualification": "synthetic_diagnostic_only",
    }
    with (target / "manifest.json").open("x") as stream:
        stream.write(_json(manifest))
    return manifest


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--worker":
        raise SystemExit("Use the operator preparation API; worker is internal.")
    _worker(Path(sys.argv[2]).resolve(strict=True), _groups(json.loads(sys.argv[3])))
