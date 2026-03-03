#!/usr/bin/env python3
"""Agregacja wyników benchmarku codingowego modeli Ollama."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ModelStats:
    """Zbiorcze metryki modelu."""

    model: str
    simple_pass_rate: float
    complex_pass_rate: float
    loop_success_rate: float
    avg_loop_rounds: float
    score: float


def _load_artifacts(path: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    if path.is_file() and path.suffix == ".json":
        artifacts.append(json.loads(path.read_text(encoding="utf-8")))
        return artifacts

    for file in sorted(path.glob("*.json")):
        try:
            artifacts.append(json.loads(file.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return artifacts


def _calc_score(
    simple: float, complex_: float, loop: float, loop_rounds: float
) -> float:
    if loop <= 0.0:
        speed_component = 0.0
    else:
        speed_component = max(0.0, 1.0 - max(0.0, loop_rounds - 1.0) / 3.0)
    return round(
        (0.25 * simple + 0.35 * complex_ + 0.30 * loop + 0.10 * speed_component) * 100,
        2,
    )


def aggregate(artifacts: list[dict[str, Any]]) -> list[ModelStats]:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {
            "simple": [],
            "complex": [],
            "loop": [],
            "loop_rounds": [],
        }
    )

    for item in artifacts:
        model = str(item.get("model", "")).strip()
        if not model:
            continue

        run_type = item.get("run_type")
        task_id = str(item.get("task_id", ""))

        if run_type == "single_task":
            passed = 1.0 if bool(item.get("passed")) else 0.0
            if task_id == "python_simple":
                grouped[model]["simple"].append(passed)
            elif task_id == "python_complex":
                grouped[model]["complex"].append(passed)
        elif run_type == "feedback_loop":
            solved = 1.0 if bool(item.get("solved")) else 0.0
            rounds = item.get("rounds", [])
            numeric_rounds = [
                r.get("round") for r in rounds if isinstance(r.get("round"), int)
            ]
            rounds_used = float(max(numeric_rounds) if numeric_rounds else 0)
            grouped[model]["loop"].append(solved)
            grouped[model]["loop_rounds"].append(rounds_used)

    stats: list[ModelStats] = []
    for model, values in grouped.items():
        simple = (
            sum(values["simple"]) / len(values["simple"]) if values["simple"] else 0.0
        )
        complex_ = (
            sum(values["complex"]) / len(values["complex"])
            if values["complex"]
            else 0.0
        )
        loop = sum(values["loop"]) / len(values["loop"]) if values["loop"] else 0.0
        loop_rounds = (
            sum(values["loop_rounds"]) / len(values["loop_rounds"])
            if values["loop_rounds"]
            else 0.0
        )
        stats.append(
            ModelStats(
                model=model,
                simple_pass_rate=round(simple, 4),
                complex_pass_rate=round(complex_, 4),
                loop_success_rate=round(loop, 4),
                avg_loop_rounds=round(loop_rounds, 4),
                score=_calc_score(simple, complex_, loop, loop_rounds),
            )
        )

    return sorted(stats, key=lambda row: row.score, reverse=True)


def _write_csv(path: Path, rows: list[ModelStats]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank",
                "model",
                "score",
                "simple_pass_rate",
                "complex_pass_rate",
                "loop_success_rate",
                "avg_loop_rounds",
            ]
        )
        for idx, row in enumerate(rows, start=1):
            writer.writerow(
                [
                    idx,
                    row.model,
                    row.score,
                    row.simple_pass_rate,
                    row.complex_pass_rate,
                    row.loop_success_rate,
                    row.avg_loop_rounds,
                ]
            )


def _write_markdown(path: Path, rows: list[ModelStats]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Ollama Coding Benchmark — Ranking",
        "",
        "| Rank | Model | Score | Simple | Complex | Debug Loop | Avg Rounds |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(
            f"| {idx} | {row.model} | {row.score:.2f} | {row.simple_pass_rate:.2%} | "
            f"{row.complex_pass_rate:.2%} | {row.loop_success_rate:.2%} | {row.avg_loop_rounds:.2f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate Ollama coding benchmark artifacts"
    )
    parser.add_argument(
        "--input",
        default="data/benchmarks/ollama_dev_coding",
        help="JSON file or directory with benchmark artifacts",
    )
    parser.add_argument(
        "--csv", default="data/benchmarks/ollama_dev_coding/scoreboard.csv"
    )
    parser.add_argument(
        "--md", default="data/benchmarks/ollama_dev_coding/scoreboard.md"
    )
    args = parser.parse_args()

    artifacts = _load_artifacts(Path(args.input))
    rows = aggregate(artifacts)

    _write_csv(Path(args.csv), rows)
    _write_markdown(Path(args.md), rows)

    print(
        json.dumps(
            {
                "models_ranked": len(rows),
                "csv": args.csv,
                "markdown": args.md,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
