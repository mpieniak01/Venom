#!/usr/bin/env python3
"""Read-only presentation of the cheapest eligible offers for a workload profile."""

from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from venom_core.infrastructure.providers.vast.models import amount  # noqa: E402
from venom_core.services.vast_environments.cli import main as vast_main  # noqa: E402

TEXT = {
    "pl": {
        "headers": [
            "ID",
            "USD/h",
            "Opis",
            "GPU",
            "FLOPS [TFLOPS]",
            "VRAM [MB]",
            "RAM hosta [MB]",
            "RAM instancji ~[MB]",
            "Procesor / efektywne rdzenie",
            "Lokalizacja",
        ],
        "summary": "Pokazano {shown} z {count} pasujących ofert w pobranej puli (API: do 100); cena rosnąco, dysk zgodny z profilem, transfer osobno.",
        "note": "RAM instancji to szacunek cpu_ram × gpu_frac. Limit kontenera i działanie GPU wymagają odbioru po wynajmie.",
        "empty": "Brak ofert spełniających profil z kompletną wyceną. Filtry nie zostały poluzowane.",
    },
    "en": {
        "headers": [
            "ID",
            "USD/h",
            "Description",
            "GPU",
            "FLOPS [TFLOPS]",
            "VRAM [MB]",
            "Host RAM [MB]",
            "Instance RAM ~[MB]",
            "CPU / effective cores",
            "Location",
        ],
        "summary": "Showing {shown} of {count} matching offers in the fetched pool (API: up to 100); ascending hourly price, profile disk included, transfer separate.",
        "note": "Instance RAM is an estimate: cpu_ram × gpu_frac. Container limits and GPU operation require acceptance after rental.",
        "empty": "No offers meet the profile with a complete quote. Filters were not relaxed.",
    },
    "de": {
        "headers": [
            "ID",
            "USD/h",
            "Beschreibung",
            "GPU",
            "FLOPS [TFLOPS]",
            "VRAM [MB]",
            "Host-RAM [MB]",
            "Instanz-RAM ~[MB]",
            "CPU / effektive Kerne",
            "Standort",
        ],
        "summary": "{shown} von {count} passenden Angeboten im abgerufenen Pool (API: bis zu 100); Stundenpreis aufsteigend, Profil-Speicher inklusive, Transfer separat.",
        "note": "Instanz-RAM ist eine Schätzung: cpu_ram × gpu_frac. Container-Limits und GPU-Betrieb müssen nach der Anmietung geprüft werden.",
        "empty": "Keine Angebote erfüllen das Profil mit vollständigem Preis. Die Filter wurden nicht gelockert.",
    },
}


def cell(value: object) -> str:
    return " ".join(str(value if value is not None else "?").split()).replace("|", "/")


def select(rows: list[dict], limit: int) -> tuple[list[dict], int]:
    eligible = [
        row
        for row in rows
        if row["status"] == "eligible"
        and amount(row["quote"]["hourly_usd"]) is not None
    ]
    eligible.sort(
        key=lambda row: (amount(row["quote"]["hourly_usd"]), row["offer"]["id"])
    )
    return eligible[:limit], len(eligible)


def render(rows: list[dict], count: int, locale: str) -> str:
    labels = TEXT[locale]
    lines = [labels["summary"].format(shown=len(rows), count=count)]
    if rows:
        lines += [
            "",
            "| " + " | ".join(labels["headers"]) + " |",
            "| " + " | ".join(["---"] * len(labels["headers"])) + " |",
        ]
    else:
        lines.append(labels["empty"])
    for row in rows:
        offer = row["offer"]
        memory = row["runtime"].get("memory_allocation", {})
        flops = amount(offer.get("total_flops"))
        values = [
            offer["id"],
            f"{amount(row['quote']['hourly_usd']):.5f}",
            f"CUDA {offer.get('cuda_max_good', '?')}; NVIDIA {offer.get('driver_version', '?')}; machine {offer.get('machine_id', '?')}",
            offer.get("gpu_name"),
            f"{flops:.0f}" if flops is not None else None,
            offer.get("gpu_ram"),
            offer.get("cpu_ram"),
            memory.get("baseline_ram_mb"),
            f"{offer.get('cpu_name', '?')} / {offer.get('cpu_cores_effective', '?')}",
            offer.get("geolocation") or row["host"].get("country_code"),
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines += ["", labels["note"]]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        type=Path,
        default=ROOT / ".venom_runtime/vast/prepared/chat-gemma4-26b-q4-24gb.json",
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.dev")
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".venom_runtime/vast")
    parser.add_argument(
        "--limit", type=int, choices=range(1, 101), default=10, metavar="1..100"
    )
    parser.add_argument("--locale", choices=list(TEXT), default="pl")
    args = parser.parse_args(argv)
    captured = io.StringIO()
    with redirect_stdout(captured):
        result = vast_main(
            [
                "--json",
                "--env-file",
                str(args.env_file),
                "--state-dir",
                str(args.state_dir),
                "offers",
                "--profile",
                str(args.profile),
                "--sort",
                "price",
                "--no-country-preference",
                "--any-gpu",
            ]
        )
    document = json.loads(captured.getvalue())
    if result:
        print(json.dumps(document, ensure_ascii=False), file=sys.stderr)
        return result
    rows, count = select(document["result"], args.limit)
    print(render(rows, count, args.locale))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
