"""Behavioral regressions for the Sonar runtime refactoring boundaries."""

import pytest

from venom_core.execution.agent_contracts import ToolPolicy, tool_function
from venom_core.services import conversation_providers as conversation
from venom_core.services.module_registry import _FACTORY_IMPORT


def test_tool_policy_constructor_keeps_subclass_binding_and_filters():
    class CustomPolicy(ToolPolicy):
        pass

    filters = {"included_plugins": ["files"]}
    policy = CustomPolicy.Auto(filters=filters)
    default = CustomPolicy.Auto()
    assert type(policy) is CustomPolicy
    assert policy.filters is filters
    assert type(default) is CustomPolicy
    assert default.filters == {}


def test_tool_decorator_preserves_bound_method_and_declared_metadata():
    class Skills:
        @tool_function(name="read", description="Read a workspace file")
        def read_file(self, path: str) -> str:
            return "contents:" + path

    skills = Skills()
    assert skills.read_file("example.txt") == "contents:example.txt"
    assert Skills.read_file.__venom_tool__ == {
        "name": "read",
        "description": "Read a workspace file",
    }


@pytest.mark.parametrize(
    "value, allowed",
    [
        ("module.factory:create_2", True),
        ("_module:create", True),
        ("módulo:create", False),
        ("module:créer", False),
        ("module.9invalid:create", False),
        ("module:create\n", False),
    ],
)
def test_factory_import_allowlist_stays_ascii(value, allowed):
    assert bool(_FACTORY_IMPORT.fullmatch(value)) is allowed


@pytest.mark.asyncio
async def test_registry_close_drains_multiple_providers_from_snapshot():
    closed = []

    class Provider:
        def __init__(self, name):
            self.name = name

        async def handle(self, text, context):
            return None

        async def close(self):
            closed.append(self.name)

    registry = conversation.ConversationProviderRegistry(None)
    await registry.register("first", Provider("first"))
    await registry.register("second", Provider("second"))
    await registry.close()
    assert closed == ["first", "second"]
    assert registry.providers == {}


def test_server_status_merge_keeps_fresh_onnx_and_display_name_fallback():
    from types import SimpleNamespace

    from venom_core.api.routes.system_llm import _merge_monitor_status_into_servers

    stale = SimpleNamespace(
        name="ONNX",
        status=SimpleNamespace(value="offline"),
        latency_ms=99,
        last_check="old",
        error_message="stale monitor",
    )
    online = SimpleNamespace(
        name="Custom daemon",
        status=SimpleNamespace(value="online"),
        latency_ms=1,
        last_check="now",
        error_message=None,
    )
    monitor = SimpleNamespace(get_all_services=lambda: [stale, online])
    fresh = {"name": "onnx", "onnx": {"ready": True}, "status": "online"}
    alias = {"name": "unknown-id", "display_name": "Custom daemon"}
    servers = [fresh, alias]
    _merge_monitor_status_into_servers(servers, monitor)
    assert fresh == {"name": "onnx", "onnx": {"ready": True}, "status": "online"}
    assert alias["status"] == "online"
    assert alias["latency_ms"] == 1
    assert alias["last_check"] == "now"
    assert alias["error_message"] is None
