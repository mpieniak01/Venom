"""Verify and summarize one frozen Polish chat GPU evaluation without auto-grading text."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

from scripts.academy.omni_pl_chat_data import sha256
from scripts.academy.polish_chat_quality import (
    CASES,
    _source_urls,
    model_cases,
    read_cases,
)


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _verified_run(
    directory: Path, input_path: Path, case_ids: set[str]
) -> tuple[dict, list[dict]]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["data_sha256"] != sha256(input_path):
        raise ValueError("evaluation input differs from its GPU manifest")
    if set(manifest["evaluated_ids"]) != case_ids or len(
        manifest["evaluated_ids"]
    ) != len(case_ids):
        raise ValueError("evaluation did not cover the expected cases")
    outputs = manifest["outputs"]
    if "raw.jsonl" not in outputs:
        raise ValueError("GPU manifest does not include the raw response hash")
    if set(outputs) - {"raw.jsonl", "blind.jsonl", "unblind.json"}:
        raise ValueError("GPU manifest contains unknown output files")
    for name, digest in outputs.items():
        if sha256(directory / name) != digest:
            raise ValueError(f"evaluation output differs from its GPU manifest: {name}")
    rows = _read_jsonl(directory / "raw.jsonl")
    variants = set(manifest["models"])
    if "base" not in variants or len(variants) != 2:
        raise ValueError("expected base and one adapter")
    keys = [(row["case"], row["model"]) for row in rows]
    if len(keys) != len(set(keys)) or set(keys) != {
        (case_id, variant) for case_id in case_ids for variant in variants
    }:
        raise ValueError("raw GPU responses are missing or duplicated")
    return manifest, rows


def _technical(rows: list[dict]) -> dict:
    finishes = Counter(row["response"]["finish"] for row in rows)
    return {
        "cases": len(rows),
        "finish": dict(sorted(finishes.items())),
        "output_tokens_median": statistics.median(row["output_tokens"] for row in rows),
        "generation_seconds_total": round(
            sum(row["elapsed_seconds"] for row in rows), 2
        ),
    }


def _identical_answers(rows: list[dict]) -> int:
    by_case: dict[str, list[str]] = {}
    for row in rows:
        by_case.setdefault(row["case"], []).append(row["response"]["text"])
    return sum(
        len(answers) == 2 and answers[0] == answers[1] for answers in by_case.values()
    )


def build_report(root: Path) -> dict:
    """Reject unsealed or incomplete inputs before deriving descriptive metrics."""
    cases = read_cases()
    model_ids = {row["record_id"] for row in cases if row["capability"] == "model"}
    tool_ids = {row["record_id"] for row in cases if row["capability"] != "model"}
    capture = root / "tool-capture"
    capture_manifest = json.loads(
        (capture / "manifest.json").read_text(encoding="utf-8")
    )
    if capture_manifest["cases_sha256"] != sha256(CASES):
        raise ValueError("quality cases differ from source capture")
    for key, name in (
        ("tool_dev_sha256", "tool-dev.jsonl"),
        ("source_evidence_sha256", "source-evidence.jsonl"),
    ):
        if capture_manifest[key] != sha256(capture / name):
            raise ValueError(f"source capture differs from its manifest: {name}")
    evidence = _read_jsonl(capture / "source-evidence.jsonl")
    if (
        len(evidence) != len(tool_ids)
        or {row["record_id"] for row in evidence} != tool_ids
    ):
        raise ValueError("source evidence does not cover nine tool cases")
    evidence_by_id = {row["record_id"]: row for row in evidence}
    model_input = root / "model-dev.jsonl"
    expected = {
        row["record_id"]: {**row, "max_new_tokens": 512} for row in model_cases(cases)
    }
    actual = _read_jsonl(model_input)
    if (
        len(actual) != len(expected)
        or any(
            {"max_new_tokens": 512, **row} != expected.get(row["record_id"])
            for row in actual
        )
        or {row["record_id"] for row in actual} != model_ids
    ):
        raise ValueError("model evaluation input differs from the frozen cases")
    model_manifest, model_rows = _verified_run(
        root / "model-eval", model_input, model_ids
    )
    tool_manifest, tool_rows = _verified_run(
        root / "tool-eval", capture / "tool-dev.jsonl", tool_ids
    )
    variants = set(model_manifest["models"])
    if set(tool_manifest["models"]) != variants:
        raise ValueError("model and source evaluations used different variants")
    if (
        model_manifest["snapshot_manifest_sha256"]
        != tool_manifest["snapshot_manifest_sha256"]
    ):
        raise ValueError("model and source evaluations used different snapshots")
    if model_manifest["models"] != tool_manifest["models"]:
        raise ValueError("model and source evaluations used different adapter weights")
    adapter = next(name for name in variants if name != "base")
    technical = {
        variant: {
            "model": _technical([row for row in model_rows if row["model"] == variant]),
            "with_sources": _technical(
                [row for row in tool_rows if row["model"] == variant]
            ),
        }
        for variant in ("base", adapter)
    }
    citations = {}
    for variant in ("base", adapter):
        cited = unsupported = 0
        for row in tool_rows:
            if row["model"] != variant:
                continue
            urls = _source_urls(row["response"]["text"])
            allowed = set(evidence_by_id[row["case"]]["source_urls"])
            cited += sum(url in allowed for url in urls)
            unsupported += sum(url not in allowed for url in urls)
        citations[variant] = {
            "matching_source_urls": cited,
            "urls_without_captured_evidence": unsupported,
        }
    return {
        "schema_version": 1,
        "cases_sha256": sha256(CASES),
        "capture_manifest_sha256": sha256(capture / "manifest.json"),
        "model_manifest_sha256": sha256(root / "model-eval/manifest.json"),
        "tool_manifest_sha256": sha256(root / "tool-eval/manifest.json"),
        "variants": ["base", adapter],
        "technical": technical,
        "identical_answers": {
            "model": _identical_answers(model_rows),
            "with_sources": _identical_answers(tool_rows),
        },
        "source_states": dict(
            sorted(Counter(row["source_state"] for row in evidence).items())
        ),
        "source_by_case": {
            row["record_id"]: {
                "capability": row["capability"],
                "route": row["route"],
                "state": row["source_state"],
                "urls": row["source_urls"],
            }
            for row in evidence
        },
        "citations": citations,
        "content_review_status": "awaiting_blind_review",
        "limitations": [
            "Source contexts were prepared by Studio Normal, but generations used the pinned direct Omni GPU evaluator rather than the Ollama streaming runtime.",
            "The 32 authored dev cases are not representative user traffic or a sealed holdout.",
            "URL matching is descriptive and does not establish factual correctness.",
        ],
    }


def write_report(root: Path, directory: Path) -> dict:
    if directory.exists():
        raise FileExistsError(directory)
    report = build_report(root)
    directory.mkdir(parents=True)
    (directory / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Polski czat — techniczna ocena 32 przypadków",
        "",
        f"Warianty: `base` i `{report['variants'][1]}`. Ocena treści wymaga ślepego przeglądu.",
        "",
        "| Wariant | Część | Zakończone | Limit | Mediana tokenów | Czas generacji |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for variant in report["variants"]:
        for part, label in (
            ("model", "23 modelowe"),
            ("with_sources", "9 ze źródłami"),
        ):
            item = report["technical"][variant][part]
            lines.append(
                f"| {variant} | {label} | {item['finish'].get('stop', 0)}/{item['cases']} "
                f"| {item['finish'].get('length', 0)} | {item['output_tokens_median']} "
                f"| {item['generation_seconds_total']} s |"
            )
    lines.extend(
        (
            "",
            "## Źródła",
            "",
            "| Stan | Liczba przypadków |",
            "| --- | ---: |",
        )
    )
    lines.insert(
        lines.index("## Źródła"),
        f"Dokładnie identyczne odpowiedzi bazy i adaptera: "
        f"{report['identical_answers']['model']}/23 modelowe i "
        f"{report['identical_answers']['with_sources']}/9 ze źródłami.\n",
    )
    lines.extend(
        f"| {state} | {count} |" for state, count in report["source_states"].items()
    )
    lines.extend(
        (
            "",
            "| Przypadek | Zdolność | Routing | Stan źródła |",
            "| --- | --- | --- | --- |",
        )
    )
    lines.extend(
        f"| {case_id} | {item['capability']} | {item['route'] or 'brak'} | {item['state']} |"
        for case_id, item in report["source_by_case"].items()
    )
    lines.extend(
        (
            "",
            "| Wariant | Cytowane adresy ze źródeł | Adresy bez dowodu |",
            "| --- | ---: | ---: |",
        )
    )
    lines.extend(
        f"| {variant} | {report['citations'][variant]['matching_source_urls']} | "
        f"{report['citations'][variant]['urls_without_captured_evidence']} |"
        for variant in report["variants"]
    )
    lines.extend(
        (
            "",
            "Pełne odpowiedzi do ślepego przeglądu: `../model-eval/blind.jsonl` i "
            "`../tool-eval/blind.jsonl`. Zapis źródeł: `../tool-capture/source-evidence.jsonl`.",
            "Bez oceny treści nie wybieramy adaptera ani nowego treningu.",
            "",
        )
    )
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = write_report(args.root, args.directory)
    print(
        json.dumps(
            {"variants": report["variants"], "source_states": report["source_states"]}
        )
    )


if __name__ == "__main__":
    main()
