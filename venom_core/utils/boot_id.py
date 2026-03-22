"""Boot identifier for the running backend process."""

import os
from uuid import uuid4

_BOOT_ID_ENV_KEY = "VENOM_BOOT_ID"

_boot_id_from_env = os.getenv(_BOOT_ID_ENV_KEY, "").strip()
if _boot_id_from_env:
    BOOT_ID = _boot_id_from_env
else:
    BOOT_ID = uuid4().hex
    os.environ[_BOOT_ID_ENV_KEY] = BOOT_ID
