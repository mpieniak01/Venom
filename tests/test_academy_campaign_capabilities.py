"""Campaign availability is exposed without creating a study."""

from unittest.mock import Mock

import pytest

from venom_core.api.routes import academy_experiment_campaigns as routes


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        (Mock(return_value="4.9.0"), {"available": True}),
        (
            Mock(side_effect=ValueError("campaign_optuna_unavailable")),
            {"available": False, "reason": "campaign_optuna_unavailable"},
        ),
        (
            Mock(side_effect=ValueError("campaign_optuna_version_mismatch")),
            {"available": False, "reason": "campaign_optuna_version_mismatch"},
        ),
    ],
)
def test_list_keeps_campaigns_available_when_optuna_is_optional(
    monkeypatch, probe, expected
):
    service = Mock()
    service.list.return_value = [{"campaign_id": "fixed"}]
    monkeypatch.setattr(routes, "campaign_service", lambda: service)
    monkeypatch.setattr(routes, "require_optuna", probe)

    assert routes.list_campaigns() == {
        "campaigns": [{"campaign_id": "fixed"}],
        "capabilities": {"optuna": expected},
    }
    probe.assert_called_once_with()
