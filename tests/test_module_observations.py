import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from venom_core.services.conversation_providers import ConversationProviderRegistry
from venom_core.services.module_observations import module_candidates
from venom_core.services.module_registry import include_optional_api_routers


def settings(raw):
    return SimpleNamespace(API_OPTIONAL_MODULES=raw)


def test_missing_optional_module_does_not_block_core_or_disclose_path(tmp_path):
    raw = f"manifest:{tmp_path}/private-module.json"
    app = FastAPI()
    assert include_optional_api_routers(app, settings(raw)) == []
    record = app.state.optional_module_diagnostics[0]
    assert record["state"] == "unavailable"
    assert str(tmp_path) not in json.dumps(record)
    assert module_candidates(settings(raw))[0][1]["module_id"] == record["module_id"]


def test_metadata_discovery_never_imports_module_and_filters_unsafe_navigation(
    tmp_path,
):
    path = tmp_path / "module.json"
    path.write_text(
        json.dumps(
            {
                "module_id": "sample",
                "display_name": "Sample",
                "frontend": {"nav_path": "//evil.test"},
            }
        )
    )
    record = module_candidates(settings(f"manifest:{path},manifest:{path}"))
    assert len(record) == 1
    assert record[0][1]["display_name"] == "Sample"
    assert record[0][1]["state"] == "unverified"
    assert record[0][1]["nav_path"] is None


@pytest.mark.asyncio
async def test_failed_optional_provider_does_not_block_healthy_provider_or_retry_storm():
    healthy = SimpleNamespace(handle=AsyncMock(return_value=None), close=AsyncMock())
    attempts = []

    def broken(app):
        attempts.append(True)
        raise RuntimeError("secret detail")

    registry = ConversationProviderRegistry(
        None,
        lambda: {"bad": broken, "good": lambda app: healthy},
        isolate_failures=True,
    )
    await registry.refresh()
    await registry.refresh()
    assert list(registry.providers) == ["good"]
    assert attempts == [True]
    assert registry.failures == {"bad": "provider_initialization_failed"}
    healthy.close.side_effect = RuntimeError("private error")
    await registry.close()
    assert registry.failures["good"] == "provider_close_failed"


@pytest.mark.asyncio
async def test_optional_async_initialization_failure_is_isolated():
    async def broken(app):
        raise ValueError("private")

    registry = ConversationProviderRegistry(
        None, lambda: {"bad": broken}, isolate_failures=True
    )
    await registry.refresh()
    assert registry.providers == {}
    assert registry.failures["bad"] == "provider_initialization_failed"
    await registry.close()
