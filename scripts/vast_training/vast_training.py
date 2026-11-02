#!/usr/bin/env python3
"""Prepare Vast CLI commands; no API requests or paid resources by default."""

import argparse
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def stack():
    return json.loads((ROOT / "stack.json").read_text())


def offer_query(profile, max_hourly):
    if not math.isfinite(max_hourly) or max_hourly <= 0:
        raise ValueError("max-hourly must be finite and positive")
    pinned = stack()
    driver = int(pinned["minimum_driver_major"]) * 1000000
    return (
        f"verified=True rentable=True rented=False direct_port_count>=1 cpu_arch=amd64 num_gpus={profile['gpus']} "
        f"gpu_ram>={profile['gpu_ram_gb']} cpu_ram>={profile['cpu_ram_gb']} "
        f"disk_space>={profile['disk_gb']} cuda_vers>={pinned['cuda']} "
        f"driver_version>={driver} reliability>=0.99 dph_total<={max_hourly}"
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
            "--storage",
            str(profile["disk_gb"]),
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
            "--cancel-unavail",
            "--label",
            "training-" + args.profile,
            "--env",
            "-e JUPYTER_DISABLE=1",
            "--onstart-cmd",
            startup(),
            "--raw",
        ]
    raise ValueError("unknown action")


def raw_response(stdout):
    """Accept JSON or the exact 2FA retry preamble emitted by pinned CLI 1.10.0."""
    lines = stdout.lstrip().splitlines()
    expired = {
        f"Failed with error {code}: Your 2FA session has expired."
        for code in (401, 404)
    }
    if lines and lines[0] in expired:
        if (
            len(lines) < 4
            or not lines[1].startswith("Trying again with your normal API Key from ")
            or not lines[1].endswith("...")
            or lines[2] != "To start a new 2FA session, run: vastai tfa login"
        ):
            raise ValueError("vast_auth_retry_output_incomplete")
        stdout = "\n".join(lines[3:])
    return json.loads(stdout)


def unconfirmed_creation():
    print(
        "Creation outcome unconfirmed. Run `vastai show instances --raw` and check "
        "existing instances before retrying create; the previous request may have succeeded.",
        file=sys.stderr,
    )
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["offers", "create", "template"])
    parser.add_argument("--profile", choices=["lora", "qlora", "full"], default="qlora")
    parser.add_argument(
        "--max-hourly",
        type=float,
        default=1.0,
        help="Offer price filter USD/h with selected storage allocation; transfer billed separately",
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
                    "cancel_unavail": True,
                    "pricing_storage_gb": config["profiles"][args.profile]["disk_gb"],
                    "search_params": offer_query(
                        config["profiles"][args.profile], args.max_hourly
                    ),
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
    result = subprocess.run(
        argv, check=False, env=os.environ.copy(), capture_output=True, text=True
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode:
        if args.action == "create":
            unconfirmed_creation()
        return result.returncode
    try:
        response = raw_response(result.stdout)
    except ValueError:
        return unconfirmed_creation() if args.action == "create" else 1
    if args.action == "create":
        if isinstance(response, dict):
            if response.get("success") is False or response.get("error") is True:
                return 1
            contract = response.get("new_contract")
            if (
                response.get("success") is True
                and type(contract) is int
                and contract > 0
            ):
                return 0
        return unconfirmed_creation()
    return 0 if isinstance(response, list) else 1


if __name__ == "__main__":
    raise SystemExit(main())
