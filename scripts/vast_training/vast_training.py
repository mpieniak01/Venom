#!/usr/bin/env python3
"""Prepare Vast CLI commands; no API requests or paid resources by default."""

import argparse
import json
import math
import os
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def stack():
    return json.loads((ROOT / "stack.json").read_text())


def offer_query(profile, max_hourly):
    if not math.isfinite(max_hourly) or max_hourly <= 0:
        raise ValueError("max-hourly must be finite and positive")
    return (
        f"verified=True rentable=True rented=False cpu_arch=amd64 num_gpus={profile['gpus']} "
        f"gpu_ram>={profile['gpu_ram_gb']} cpu_ram>={profile['cpu_ram_gb']} "
        f"disk_space>={profile['disk_gb']} cuda_vers>=13.0 "
        f"driver_version>=580000000 reliability>=0.99 dph_total<={max_hourly}"
    )


def startup():
    # Called by Vast SSH launch mode. No downloads, pip installs or training.
    return (
        "set -eu; umask 077; mkdir -p /workspace/data/vast-training/datasets /workspace/data/vast-training/outputs /workspace/data/vast-training/logs; "
        "echo awaiting_upload > /workspace/data/vast-training/environment.state"
    )


def command(args):
    config = stack()
    profile = config["profiles"][args.profile]
    if args.action == "offers":
        return [
            "vastai",
            "search",
            "offers",
            offer_query(profile, args.max_hourly),
            "--order",
            "dph_total",
            "--limit",
            "10",
            "--raw",
        ]
    if args.action == "create":
        if args.offer is None or args.offer <= 0:
            raise ValueError("create requires a positive --offer selected from offers")
        return [
            "vastai",
            "create",
            "instance",
            str(args.offer),
            "--image",
            config["image"],
            "--disk",
            str(profile["disk_gb"]),
            "--ssh",
            "--direct",
            "--label",
            "training-" + args.profile,
            "--env",
            "-e JUPYTER_DISABLE=1",
            "--onstart-cmd",
            startup(),
            "--raw",
        ]
    raise ValueError("unknown action")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["offers", "create", "template"])
    parser.add_argument("--profile", choices=["lora", "qlora", "full"], default="qlora")
    parser.add_argument(
        "--max-hourly",
        type=float,
        default=1.0,
        help="Offer compute-price filter USD/h; storage/transfer billed separately",
    )
    parser.add_argument("--offer", type=int)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually invoke Vast CLI; create rents GPU",
    )
    args = parser.parse_args()
    if args.action == "template":
        config = stack()
        print(
            json.dumps(
                {
                    "name": "venom-training-" + args.profile,
                    "image": config["image"],
                    "launch_mode": "SSH direct",
                    "onstart_cmd": startup(),
                    "environment": {"JUPYTER_DISABLE": "1"},
                    "requirements": config["profiles"][args.profile],
                    "gpu_qualified": False,
                },
                indent=2,
            )
        )
        return 0
    argv = command(args)
    print(shlex.join(argv), flush=True)
    if not args.execute:
        print("DRY RUN: no network requests, no instance created.")
        return 0
    if not shutil.which("vastai"):
        parser.error("vastai missing; install pinned CLI using install-cli.sh")
    if args.action == "create":
        print(
            "RENTING selected offer. Verify current compute/storage/transfer price before this command.",
            flush=True,
        )
    return subprocess.run(argv, check=False, env=os.environ.copy()).returncode


if __name__ == "__main__":
    raise SystemExit(main())
