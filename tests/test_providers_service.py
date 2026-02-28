from __future__ import annotations

from types import SimpleNamespace

import pytest

from venom_core.services import providers_service as svc
from venom_core.utils.url_policy import build_http_url


class _DummyRequest:
    def __init__(
        self, *, user: str | None = None, headers: dict[str, str] | None = None
    ) -> None:
        self.state = SimpleNamespace(user=user)
        self.headers = headers or {}


def test_extract_user_from_request_state_and_headers() -> None:
    req = _DummyRequest(user="state-user")
    assert svc.extract_user_from_request(req) == "state-user"

    req_h = _DummyRequest(headers={"X-User": "header-user"})
    assert svc.extract_user_from_request(req_h) == "header-user"


def test_extract_user_from_request_handles_exception() -> None:
    class Broken:
        @property
        def state(self):
            raise RuntimeError("boom")

    logger = SimpleNamespace(warning=lambda *_args, **_kwargs: None)
    assert svc.extract_user_from_request(Broken(), logger=logger) == "unknown"


def test_provider_type_and_capabilities() -> None:
    assert svc.get_provider_type("openai") == "cloud_provider"
    assert svc.get_provider_type("ollama") == "catalog_integrator"
    assert svc.get_provider_type("vllm") == "local_runtime"
    assert svc.get_provider_type("x") == "unknown"

    local_caps = svc.get_provider_capabilities("local")
    assert local_caps.activate is True
    assert local_caps.install is False

    unknown = svc.get_provider_capabilities("not-real")
    assert unknown.install is False
    assert unknown.inference is False


def test_cloud_activation_and_default_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc.SETTINGS, "OPENAI_GPT4O_MODEL", "gpt-def", raising=False)
    monkeypatch.setattr(
        svc.SETTINGS, "GOOGLE_GEMINI_PRO_MODEL", "gem-def", raising=False
    )

    calls: list[dict[str, str]] = []
    monkeypatch.setattr(
        svc.config_manager, "update_config", lambda payload: calls.append(payload)
    )

    out_openai = svc.activate_cloud_provider("openai", None)
    assert out_openai["model"] == "gpt-def"

    req = SimpleNamespace(model="gemini-custom")
    out_google = svc.activate_cloud_provider("google", req)
    assert out_google["model"] == "gemini-custom"
    assert len(calls) == 2


def test_provider_status_and_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc.SETTINGS, "OPENAI_API_KEY", "", raising=False)
    assert svc.check_openai_status().reason_code == "missing_api_key"

    monkeypatch.setattr(svc.SETTINGS, "OPENAI_API_KEY", "sk-1", raising=False)
    assert svc.check_openai_status().status == "connected"

    monkeypatch.setattr(svc.SETTINGS, "GOOGLE_API_KEY", "", raising=False)
    assert svc.check_google_status().reason_code == "missing_api_key"

    monkeypatch.setattr(svc.SETTINGS, "GOOGLE_API_KEY", "g-1", raising=False)
    assert svc.check_google_status().status == "connected"

    monkeypatch.setattr(
        svc.SETTINGS, "VLLM_ENDPOINT", "http://vllm:8000", raising=False
    )
    assert svc.get_provider_endpoint("ollama") == build_http_url("localhost", 11434)
    assert svc.get_provider_endpoint("vllm") == "http://vllm:8000"
    assert svc.get_provider_endpoint("unknown") is None
