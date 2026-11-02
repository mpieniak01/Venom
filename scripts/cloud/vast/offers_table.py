#!/usr/bin/env python3
"""Read-only presentation of the cheapest eligible offers for a workload profile."""

from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from venom_core.config import Settings  # noqa: E402
from venom_core.infrastructure.providers.vast.client import (  # noqa: E402
    VastClient,
    VastError,
)
from venom_core.infrastructure.providers.vast.models import amount  # noqa: E402
from venom_core.services.granite_operator.contract import write_json  # noqa: E402
from venom_core.services.vast_environments.cli import main as vast_main  # noqa: E402

TEXT = {
    "pl": {
        "training": "Trening: VM, VRAM ≥{gpu_vram_gb} GB, RAM instancji ≥{ram_gb} GB, dysk {disk_gb} GB; źródło: {suite}.",
        "headers": [
            "ID",
            "USD/h",
            "Opis",
            "GPU",
            "FLOPS [TFLOPS]",
            "VRAM [GB]",
            "RAM hosta [GB]",
            "RAM instancji ~[GB]",
            "Procesor / efektywne rdzenie",
            "Lokalizacja",
        ],
        "summary": "Pokazano {shown} z {count} pasujących ofert w pobranej puli (API: do 100); cena rosnąco, dysk zgodny z profilem, transfer osobno.",
        "note": "RAM instancji to szacunek cpu_ram × gpu_frac. Limit kontenera i działanie GPU wymagają odbioru po wynajmie.",
        "empty": "Brak ofert spełniających profil z kompletną wyceną. Filtry nie zostały poluzowane.",
    },
    "en": {
        "training": "Training: VM, VRAM ≥{gpu_vram_gb} GB, instance RAM ≥{ram_gb} GB, disk {disk_gb} GB; source: {suite}.",
        "headers": [
            "ID",
            "USD/h",
            "Description",
            "GPU",
            "FLOPS [TFLOPS]",
            "VRAM [GB]",
            "Host RAM [GB]",
            "Instance RAM ~[GB]",
            "CPU / effective cores",
            "Location",
        ],
        "summary": "Showing {shown} of {count} matching offers in the fetched pool (API: up to 100); ascending hourly price, profile disk included, transfer separate.",
        "note": "Instance RAM is an estimate: cpu_ram × gpu_frac. Container limits and GPU operation require acceptance after rental.",
        "empty": "No offers meet the profile with a complete quote. Filters were not relaxed.",
    },
    "de": {
        "training": "Training: VM, VRAM ≥{gpu_vram_gb} GB, Instanz-RAM ≥{ram_gb} GB, Speicher {disk_gb} GB; Quelle: {suite}.",
        "headers": [
            "ID",
            "USD/h",
            "Beschreibung",
            "GPU",
            "FLOPS [TFLOPS]",
            "VRAM [GB]",
            "Host-RAM [GB]",
            "Instanz-RAM ~[GB]",
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


def memory_gb(value: object) -> str:
    megabytes = amount(value)
    return f"{megabytes / 1000:.2f}" if megabytes is not None else "?"


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
            f"{amount(row['quote']['hourly_usd']):.4f}",
            f"CUDA {offer.get('cuda_max_good', '?')}; NVIDIA {offer.get('driver_version', '?')}; machine {offer.get('machine_id', '?')}",
            offer.get("gpu_name"),
            f"{flops:.0f}" if flops is not None else None,
            memory_gb(offer.get("gpu_ram")),
            memory_gb(offer.get("cpu_ram")),
            memory_gb(memory.get("baseline_ram_mb")),
            f"{offer.get('cpu_name', '?')} / {offer.get('cpu_cores_effective', '?')}",
            offer.get("geolocation") or row["host"].get("country_code"),
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines += ["", labels["note"]]
    return "\n".join(lines)


def training_offers(suite_path, env_file, state_dir, *, client_factory=None):
    """Reuse the current training suite and provider client; read-only API calls."""
    if suite_path is None:
        pointer = json.loads(
            (ROOT / "data/training/current-experiment.json").read_text()
        )
        suite_path = Path(pointer["suite"])
    suite = json.loads(suite_path.read_text())
    requirements = suite["common_host_requirements"]
    for key in ("gpu_vram_gb", "ram_gb", "disk_gb"):
        if type(requirements[key]) is not int or requirements[key] < 1:
            raise ValueError("vast.invalid_training_requirements")
    if requirements.get("vm_required") is not True:
        raise ValueError("vast.training_vm_required")
    policy = json.loads((ROOT / "config/granite_operator_host.json").read_text())
    filters = {
        "vms_enabled": {"eq": True},
        "verified": {"eq": True},
        "num_gpus": {"eq": 1},
        "cpu_arch": {"eq": "amd64"},
        "gpu_ram": {"gte": requirements["gpu_vram_gb"] * 1000},
        "cpu_ram": {"gte": requirements["ram_gb"] * 1000},
        "disk_space": {"gte": requirements["disk_gb"]},
        "cpu_cores_effective": {"gte": policy["min_cpu_threads"]},
        "reliability": {"gte": policy["min_reliability"]},
        "cuda_vers": {"gte": policy["min_cuda"]},
        "driver_version": {"gte": policy["min_driver"]},
        "direct_port_count": {"gte": 1},
        "order": [["dph_total", "asc"]],
    }
    client = (client_factory or VastClient)(Settings(_env_file=env_file).VAST_API_KEY)
    try:
        offers = client.offers(requirements["disk_gb"], filters, limit=100)
    finally:
        client.close()
    rows = []
    for offer in offers:
        cpu, fraction = amount(offer.get("cpu_ram")), amount(offer.get("gpu_frac"))
        ram = (
            cpu * fraction
            if cpu is not None and fraction is not None and 0 < fraction <= 1
            else None
        )
        search = offer.get("search") or {}
        hourly = amount(search.get("totalHour", offer.get("dph_total")))
        eligible = (
            ram is not None
            and ram >= requirements["ram_gb"] * 1000
            and hourly is not None
        )
        rows.append(
            {
                "offer": offer,
                "status": "eligible" if eligible else "ineligible",
                "quote": {"hourly_usd": str(hourly) if hourly is not None else None},
                "runtime": {
                    "memory_allocation": {
                        "baseline_ram_mb": str(ram) if ram is not None else None
                    }
                },
                "host": {},
            }
        )
    receipt = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "suite": str(suite_path.resolve()),
        "requirements": requirements,
        "filters": filters,
        "disk_gb": requirements["disk_gb"],
        "result": rows,
        "rental_created": False,
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    write_json(state_dir / "latest-training-offers.json", receipt)
    return rows, requirements, suite_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        type=Path,
        default=ROOT / ".venom_runtime/vast/prepared/chat-gemma4-26b-q4-24gb.json",
    )
    parser.add_argument(
        "--training",
        action="store_true",
        help="Use the current prepared training campaign",
    )
    parser.add_argument(
        "--training-suite",
        type=Path,
        help="Explicit training suite; implies --training",
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.dev")
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".venom_runtime/vast")
    parser.add_argument(
        "--limit", type=int, choices=range(1, 101), default=10, metavar="1..100"
    )
    parser.add_argument("--locale", choices=list(TEXT), default="pl")
    args = parser.parse_args(argv)
    if args.training or args.training_suite is not None:
        try:
            rows, requirements, suite = training_offers(
                args.training_suite, args.env_file, args.state_dir
            )
        except (VastError, OSError, ValueError, KeyError, TypeError) as error:
            code = (
                error.code
                if isinstance(error, VastError)
                else "vast.training_offers_failed"
            )
            print(json.dumps({"error": code}), file=sys.stderr)
            return 1
        selected, count = select(rows, args.limit)
        print(TEXT[args.locale]["training"].format(**requirements, suite=suite))
        print(render(selected, count, args.locale))
        return 0
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
