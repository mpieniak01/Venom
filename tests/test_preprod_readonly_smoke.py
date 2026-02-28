from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from venom_core.config import SETTINGS
from venom_core.main import app


@pytest.mark.smoke
def test_preprod_readonly_smoke_health_and_status() -> None:
    if SETTINGS.ENVIRONMENT_ROLE != "preprod":
        pytest.skip(
            "Preprod readonly smoke is only applicable for ENVIRONMENT_ROLE=preprod."
        )

    assert SETTINGS.ALLOW_DATA_MUTATION is False

    client = TestClient(app)

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json().get("status") == "ok"

    system_status = client.get("/api/v1/system/status")
    assert system_status.status_code in {200, 503}
