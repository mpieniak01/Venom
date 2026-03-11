from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def test_governance_permission_denied_audit_actor_from_request(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        governance,
        "ensure_data_mutation_allowed",
        lambda _op: (_ for _ in ()).throw(PermissionError("blocked")),
    )
    req = SimpleNamespace(
        headers={"x-authenticated-user": "alice"},
        client=SimpleNamespace(host="10.20.30.40"),
    )
    audit_stream = MagicMock()
    with patch(
        "venom_core.api.routes.permission_denied_contract.get_audit_stream",
        return_value=audit_stream,
    ):
        with pytest.raises(HTTPException):
            governance.reset_usage(req=req)

    audit_stream.publish.assert_called_once()
    assert audit_stream.publish.call_args.kwargs["actor"] == "alice"
