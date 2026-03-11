from __future__ import annotations

import pytest
from fastapi import HTTPException

from venom_core.api.routes import governance


def test_governance_permission_denied_branch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        governance,
        "ensure_data_mutation_allowed",
        lambda _op: (_ for _ in ()).throw(PermissionError("blocked")),
    )
    with pytest.raises(HTTPException) as exc_info:
        governance.reset_usage()
    assert exc_info.value.status_code == 403
    assert isinstance(exc_info.value.detail, dict)
    assert exc_info.value.detail["decision"] == "block"
    assert exc_info.value.detail["reason_code"] == "PERMISSION_DENIED"
    assert (
        exc_info.value.detail["technical_context"]["operation"]
        == "governance.reset_usage"
    )
