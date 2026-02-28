from __future__ import annotations

import venom_core.nodes as nodes


def test_nodes_all_exports_match_expected_symbols() -> None:
    expected = {
        "MessageType",
        "Capabilities",
        "NodeHandshake",
        "SkillExecutionRequest",
        "HeartbeatMessage",
        "NodeResponse",
        "NodeMessage",
    }

    assert set(nodes.__all__) == expected
    for symbol in expected:
        assert hasattr(nodes, symbol)
