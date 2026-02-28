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
