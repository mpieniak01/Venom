from __future__ import annotations

from venom_core.core import orchestrator as orchestrator_compat


def test_orchestrator_compat_exports_have_expected_names() -> None:
    assert "Orchestrator" in orchestrator_compat.__all__
    assert "MAX_REPAIR_ATTEMPTS" in orchestrator_compat.__all__
    assert "SESSION_HISTORY_LIMIT" in orchestrator_compat.__all__


def test_orchestrator_compat_exposes_reexported_objects() -> None:
    assert orchestrator_compat.Orchestrator is not None
    assert isinstance(orchestrator_compat.MAX_CONTEXT_CHARS, int)
    assert isinstance(orchestrator_compat.ENABLE_COUNCIL_MODE, bool)
