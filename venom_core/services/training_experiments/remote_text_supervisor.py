"""Single controller process, supervised outside the GPU instance."""

import logging
import time

from venom_core.config import SETTINGS
from venom_core.services.remote_training.lifecycle import file_lock

from .remote_text import RemoteTextService, remote_text_service

LOGGER = logging.getLogger(__name__)
_ACTIVE = {"queued", "running", "finalizing", "cleanup_pending"}


def supervise(service: RemoteTextService) -> None:
    service.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with file_lock(service.root / ".supervisor.lock", blocking=False):
        while True:
            service.heartbeat()
            for state in service.list():
                if state["status"] in _ACTIVE:
                    try:
                        service.tick(state["campaign_id"])
                    except (OSError, ValueError, RuntimeError):
                        LOGGER.error(
                            "Remote text controller could not update campaign state"
                        )
            time.sleep(3)


if __name__ == "__main__":
    if not SETTINGS.VAST_API_KEY.get_secret_value().strip():
        raise SystemExit("VAST_API_KEY is required by the remote text supervisor")
    logging.basicConfig(level=logging.INFO)
    supervise(remote_text_service())
