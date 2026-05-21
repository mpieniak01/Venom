"""Testy jednostkowe dla OllamaAgentLoop."""

import json
from unittest.mock import MagicMock

from venom_core.execution.ollama_agent_loop import (
    AgentLoopResult,
    OllamaAgentLoop,
    ToolCall,
    build_tool_spec,
)


def _make_ollama_response(content: str, tool_calls=None, done_reason="stop"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"message": msg, "done": True, "done_reason": done_reason}


def _make_tool_call_response(name: str, args: dict, call_id: str = "call_1"):
    return _make_ollama_response(
        content="",
        tool_calls=[
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        ],
    )


class TestToolCall:
    def test_defaults(self):
        tc = ToolCall(call_id="x", name="foo", arguments={})
        assert tc.result is None
        assert tc.error is None
        assert tc.elapsed_ms == 0


class TestAgentLoopResult:
    def test_has_evidence_false_when_empty(self):
        r = AgentLoopResult(final_answer="hi")
        assert not r.has_evidence()

    def test_has_evidence_true(self):
        r = AgentLoopResult(final_answer="hi", evidence=["git: ## main"])
        assert r.has_evidence()

    def test_format_trace_no_calls(self):
        r = AgentLoopResult(final_answer="hi")
        assert "(brak" in r.format_trace()

    def test_format_trace_with_calls(self):
        tc = ToolCall(
            call_id="c1",
            name="search_code",
            arguments={"query": "foo"},
            result="bar.py:5",
            elapsed_ms=42,
        )
        r = AgentLoopResult(final_answer="hi", tool_calls=[tc])
        trace = r.format_trace()
        assert "search_code" in trace
        assert "bar.py:5" in trace
        assert "42" in trace

    def test_format_trace_with_error(self):
        tc = ToolCall(call_id="c2", name="bad_tool", arguments={}, error="not found")
        r = AgentLoopResult(final_answer="hi", tool_calls=[tc])
        assert "✗" in r.format_trace()
        assert "not found" in r.format_trace()


class TestBuildToolSpec:
    def test_builds_correct_spec(self):
        spec = build_tool_spec(
            name="my_tool",
            description="Does a thing",
            properties={"query": {"type": "string", "description": "search query"}},
            required=["query"],
        )
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "my_tool"
        assert "query" in spec["function"]["parameters"]["properties"]
        assert spec["function"]["parameters"]["required"] == ["query"]


class TestOllamaAgentLoopInit:
    def test_default_model(self):
        loop = OllamaAgentLoop()
        assert loop.model == "qwen3.5:9b"
        assert loop.max_iterations == 5

    def test_custom_model(self):
        loop = OllamaAgentLoop(model="gpt-oss:20b", max_iterations=3)
        assert loop.model == "gpt-oss:20b"
        assert loop.max_iterations == 3

    def test_register_tool(self):
        loop = OllamaAgentLoop()
        loop.register_tool(
            name="my_tool",
            description="test",
            parameters={"type": "object", "properties": {}},
            handler=lambda n, a: "result",
        )
        assert any(t["function"]["name"] == "my_tool" for t in loop.tools)
        assert "my_tool" in loop.tool_handlers


class TestOllamaAgentLoopRun:
    def _make_loop(self, responses):
        loop = OllamaAgentLoop(model="test-model", max_iterations=5)
        call_idx = [0]

        def fake_call_ollama(messages):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx < len(responses):
                return responses[idx]
            return _make_ollama_response("domyślna odpowiedź")

        loop._call_ollama = fake_call_ollama
        return loop

    def test_direct_answer_no_tool_calls(self):
        loop = self._make_loop([_make_ollama_response("Odpowiedź bezpośrednia")])
        result = loop.run("Cześć")
        assert result.final_answer == "Odpowiedź bezpośrednia"
        assert result.iterations == 1
        assert result.stopped_by == "finish"
        assert result.tool_calls == []

    def test_single_tool_call_then_answer(self):
        tool_called = []

        def handler(name, args):
            tool_called.append((name, args))
            return "wynik_narzedzia"

        loop = self._make_loop(
            [
                _make_tool_call_response("my_tool", {"q": "x"}),
                _make_ollama_response("Finalna odpowiedź z wynikiem: wynik_narzedzia"),
            ]
        )
        loop.register_tool(
            "my_tool", "test", {"type": "object", "properties": {}}, handler
        )

        result = loop.run("zrób coś")
        assert result.final_answer == "Finalna odpowiedź z wynikiem: wynik_narzedzia"
        assert len(tool_called) == 1
        assert tool_called[0] == ("my_tool", {"q": "x"})
        assert result.iterations == 2
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].result == "wynik_narzedzia"
        assert result.has_evidence()

    def test_tool_args_as_json_string(self):
        handler = MagicMock(return_value="ok")
        loop = self._make_loop(
            [
                _make_tool_call_response("my_tool", json.dumps({"key": "val"})),
                _make_ollama_response("done"),
            ]
        )
        loop.register_tool(
            "my_tool", "t", {"type": "object", "properties": {}}, handler
        )
        loop.run("test")
        call_args = handler.call_args[0][1]
        assert isinstance(call_args, dict)
        assert call_args.get("key") == "val"

    def test_missing_tool_handler_records_error(self):
        loop = self._make_loop(
            [
                _make_tool_call_response("unknown_tool", {}),
                _make_ollama_response("fallback"),
            ]
        )
        result = loop.run("test")
        assert result.tool_calls[0].error is not None
        assert "unknown_tool" in result.tool_calls[0].error

    def test_max_iterations_guard(self):
        # Zawsze zwraca tool_call → wymusi max_iterations
        always_tool = _make_tool_call_response("endless_tool", {})

        loop = OllamaAgentLoop(model="test", max_iterations=2)
        call_count = [0]

        def fake_call(messages):
            call_count[0] += 1
            if call_count[0] <= 3:
                return always_tool
            return _make_ollama_response("podsumowanie")

        loop._call_ollama = fake_call
        loop.register_tool(
            "endless_tool", "t", {"type": "object", "properties": {}}, lambda n, a: "x"
        )

        result = loop.run("test")
        assert result.stopped_by == "max_iter"
        assert result.iterations == 2

    def test_ollama_connection_error(self):
        loop = OllamaAgentLoop(model="test", max_iterations=3)
        loop._call_ollama = MagicMock(side_effect=RuntimeError("connection refused"))
        result = loop.run("test")
        assert result.stopped_by == "error"
        assert "❌" in result.final_answer

    def test_multiple_tool_calls_in_one_iteration(self):
        handler_a = MagicMock(return_value="res_a")
        handler_b = MagicMock(return_value="res_b")

        multi_tool_response = _make_ollama_response(
            content="",
            tool_calls=[
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "tool_a", "arguments": {}},
                },
                {
                    "id": "c2",
                    "type": "function",
                    "function": {"name": "tool_b", "arguments": {}},
                },
            ],
        )
        loop = self._make_loop([multi_tool_response, _make_ollama_response("done")])
        loop.register_tool(
            "tool_a", "a", {"type": "object", "properties": {}}, handler_a
        )
        loop.register_tool(
            "tool_b", "b", {"type": "object", "properties": {}}, handler_b
        )

        result = loop.run("test")
        assert len(result.tool_calls) == 2
        handler_a.assert_called_once()
        handler_b.assert_called_once()

    def test_evidence_populated_from_tool_results(self):
        loop = self._make_loop(
            [
                _make_tool_call_response("git_status", {}),
                _make_ollama_response("branch main, czyste repo"),
            ]
        )
        loop.register_tool(
            "git_status",
            "git",
            {"type": "object", "properties": {}},
            lambda n, a: "## main...origin/main",
        )
        result = loop.run("sprawdz git")
        assert any("## main" in e for e in result.evidence)


class TestDispatchTool:
    def test_dispatch_existing_handler(self):
        loop = OllamaAgentLoop()
        loop.register_tool(
            "t", "desc", {"type": "object", "properties": {}}, lambda n, a: "42"
        )
        result, error = loop._dispatch_tool("t", {})
        assert result == "42"
        assert error is None

    def test_dispatch_missing_handler(self):
        loop = OllamaAgentLoop()
        result, error = loop._dispatch_tool("nonexistent", {})
        assert result == ""
        assert error is not None

    def test_dispatch_handler_exception(self):
        loop = OllamaAgentLoop()
        loop.register_tool(
            "failing",
            "desc",
            {"type": "object", "properties": {}},
            lambda n, a: (_ for _ in ()).throw(ValueError("boom")),
        )
        result, error = loop._dispatch_tool("failing", {})
        assert error is not None
        assert "boom" in error


class TestToolCallExtraction:
    def test_extract_tool_calls_filters_invalid_entries(self):
        loop = OllamaAgentLoop()
        out = loop._extract_tool_calls(
            {"tool_calls": ["x", {"id": "1", "function": {"name": "a"}}]}
        )
        assert out == [{"id": "1", "function": {"name": "a"}}]

    def test_extract_tool_calls_handles_non_list(self):
        loop = OllamaAgentLoop()
        assert loop._extract_tool_calls({"tool_calls": "invalid"}) == []
