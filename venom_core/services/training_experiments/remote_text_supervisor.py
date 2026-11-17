"""Persistent recovery for local workers and the remote text controller."""

import logging
import time
from pathlib import Path

from venom_core.config import SETTINGS
from venom_core.services.remote_training.lifecycle import file_lock
from venom_core.services.remote_training.paths import operator_path

from .local_campaign_final import resume_pending
from .remote_text import RemoteTextService, remote_text_service

LOGGER = logging.getLogger(__name__)
_ACTIVE = {"queued", "running", "finalizing", "cleanup_pending"}


def _remote_tick(service: RemoteTextService) -> None:
    service.heartbeat()
    for state in service.list():
        if state["status"] in _ACTIVE:
            try:
                service.tick(state["campaign_id"])
            except (OSError, ValueError, RuntimeError):
                LOGGER.error("Remote text controller could not update campaign state")


def supervise(
    service: RemoteTextService | None, *, academy_root: Path | None = None
) -> None:
    root = (
        service.local.experiments.root
        if service is not None
        else academy_root or Path(SETTINGS.ACADEMY_TRAINING_DIR) / "experiments"
    )
    directory = operator_path(root / "remote-text")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with file_lock(directory / ".supervisor.lock", blocking=False):
        while True:
            try:
                # This only ensures a detached worker. Inference never blocks
                # recovery or the remote controller's billing/cleanup loop.
                resume_pending(root)
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                LOGGER.error("Local campaign recovery could not ensure its worker")
            if service is not None:
                try:
                    _remote_tick(service)
                except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                    LOGGER.error(
                        "Remote text controller could not read or update its state"
                    )
            time.sleep(3)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    remote = (
        remote_text_service()
        if SETTINGS.VAST_API_KEY.get_secret_value().strip()
        else None
    )
    supervise(remote)
