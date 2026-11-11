"""Detached campaign worker. The run service owns child process lifetimes."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from venom_core.services.remote_training.lifecycle import file_lock, process_identity

from .campaign import CampaignService
from .service import ExperimentService


def supervise(service: CampaignService, campaign_id: str) -> None:
    directory = service.directory(campaign_id)
    with file_lock(directory / ".supervisor.lock"):
        with file_lock(directory / ".state.lock"):
            state = service._state(directory)
            if state["status"] not in {
                "running",
                "awaiting_review",
                "stopping",
                "interrupted",
            }:
                return
            state["worker"] = process_identity(os.getpid())
            service._save(directory, state)
        while service.advance(campaign_id)["status"] in {
            "running",
            "awaiting_review",
            "stopping",
        }:
            time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("campaign_id")
    args = parser.parse_args()
    supervise(CampaignService(ExperimentService(args.root)), args.campaign_id)


if __name__ == "__main__":
    main()
