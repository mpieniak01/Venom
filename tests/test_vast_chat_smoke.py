"""Vast chat acceptance uses a fake API; no rentals or local model fallbacks."""

import json

import httpx
import pytest

from scripts.cloud.vast.chat_smoke import api_base, main, run

ACTIVE = {
    "active_server": "vast_ollama",
    "runtime_id": "ollama@vast:plan:generation",
    "config_hash": "abc123",
    "active_model": "same-name",
}
STATUS = {
    "available": True,
    "target_id": "ollama@vast:plan",
    "models": [{"name": "same-name", "digest": "a" * 64}],
}
SSE = (
    "event: start\ndata: {}\n\n"
    'event: content\ndata: {"text":"test response"}\n\n'
    "event: done\ndata: {}\n\n"
)


def fake_client(*, active=None, status=None, sse=SSE, on_stream=None):
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path == "/api/v1/system/vast-chat":
            return httpx.Response(200, json=STATUS if status is None else status)
        if request.url.path == "/api/v1/system/llm-servers/active":
            return httpx.Response(200, json=ACTIVE if active is None else active)
        if request.url.path == "/openapi.json":
            return httpx.Response(
                200,
                json={
                    "components": {
                        "schemas": {
                            "SimpleChatRequest": {
                                "properties": {
                                    "expected_runtime_id": {},
                                    "expected_config_hash": {},
                                }
                            },
                        }
                    }
                },
            )
        assert request.url.path == "/api/v1/llm/simple/stream"
        if on_stream:
            on_stream(request)
        return httpx.Response(
            200,
            text=sse,
            headers={"content-type": "text/event-stream"},
        )

    return httpx.Client(
        base_url="http://127.0.0.1:8800", transport=httpx.MockTransport(handle)
    ), calls


def test_default_smoke_is_read_only():
    client, calls = fake_client()
    with client:
        report = run(client)
    assert report["status"] == "passed"
    assert report["turns"] == []
    assert all(request.method == "GET" for request in calls)


def test_live_three_turns_preserve_identity_session_and_do_not_log_content():
    client, calls = fake_client()
    with client:
        report = run(client, live=True, turns=3)
    posts = [request for request in calls if request.method == "POST"]
    assert report["status"] == "passed"
    assert len(report["turns"]) == len(posts) == 3
    payloads = [json.loads(request.content) for request in posts]
    assert len({payload["session_id"] for payload in payloads}) == 1
    for payload in payloads:
        assert payload["expected_runtime_id"] == ACTIVE["runtime_id"]
        assert payload["expected_config_hash"] == ACTIVE["config_hash"]
        assert payload["model"] == ACTIVE["active_model"]
    assert "test response" not in json.dumps(report)
    assert "Remember" not in json.dumps(report)
    assert report["browser_normal_acceptance"] == "not_tested"
    assert all(turn["completed"] for turn in report["turns"])


@pytest.mark.parametrize(
    "change",
    [
        {"active_server": "ollama"},
        {"runtime_id": "ollama@http://localhost:11434"},
        {"config_hash": ""},
        {"active_model": ""},
    ],
)
def test_never_generates_when_selected_target_is_local_or_invalid(change):
    client, calls = fake_client(active={**ACTIVE, **change})
    with client:
        report = run(client, live=True)
    assert report["status"] == "failed"
    assert not any(request.method == "POST" for request in calls)


@pytest.mark.parametrize(
    "change",
    [
        {"available": False},
        {"target_id": "ollama@vast:different"},
        {"models": []},
    ],
)
def test_host_unavailable_is_not_zero_or_success(change):
    client, calls = fake_client(status={**STATUS, **change})
    with client:
        report = run(client)
    assert report["status"] == "failed"
    assert not any(request.method == "POST" for request in calls)


@pytest.mark.parametrize(
    "sse,error",
    [
        ('event: content\ndata: {"text":"partial"}\n\n', "stream_incomplete"),
        ("event: done\ndata: {}\n\n", "stream_incomplete"),
        ('event: error\ndata: {"detail":"PRIVATE"}\n\n', "stream_error"),
        ("event: content\ndata: not-json\n\n", "stream_payload_invalid"),
        ('event: content\ndata: {"text":1}\n\n', "stream_content_invalid"),
        ("event: done\ndata: {}", "stream_incomplete"),
    ],
)
def test_stream_error_and_partial_are_not_pass(sse, error):
    client, calls = fake_client(sse=sse)
    with client:
        report = run(client, live=True)
    assert report["status"] == "failed"
    assert report["error"] == error
    assert "PRIVATE" not in json.dumps(report)
    assert sum(request.method == "POST" for request in calls) == 1


def test_runtime_switch_after_response_stops_following_turns():
    active = dict(ACTIVE)

    def switch(_):
        active["runtime_id"] = "ollama@vast:other:other"

    client, calls = fake_client(active=active, on_stream=switch)
    with client:
        report = run(client, live=True)
    assert report["status"] == "failed"
    assert sum(request.method == "POST" for request in calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org:8800",
        "http://127.0.0.1@evil.test",
        "http://localhost/api",
        "http://localhost?token=private",
        "ftp://localhost",
        "http://localhost:0",
        "http://localhost:bad",
    ],
)
def test_external_or_credentialed_api_is_rejected(url):
    with pytest.raises(ValueError, match="loopback_api_required"):
        api_base(url)


def test_ipv6_loopback_is_supported():
    assert api_base("http://[::1]:8800/") == "http://[::1]:8800"


def test_cli_default_writes_report_without_mutation(tmp_path, capsys):
    client, _ = fake_client()
    report = tmp_path / "smoke.json"
    assert main(["--report", str(report)], transport=client._transport) == 0
    result = json.loads(report.read_text())
    assert result["mode"] == "read_only_preflight"
    assert result["turns"] == []
    assert report.stat().st_mode & 0o777 == 0o600
    capsys.readouterr()


def test_cli_returns_nonzero_when_not_remote(capsys):
    client, _ = fake_client(active={**ACTIVE, "active_server": "ollama"})
    assert main([], transport=client._transport) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_old_api_without_request_guard_cannot_generate():
    def handle(request):
        if request.url.path == "/api/v1/system/vast-chat":
            return httpx.Response(200, json=STATUS)
        if request.url.path == "/api/v1/system/llm-servers/active":
            return httpx.Response(200, json=ACTIVE)
        assert request.url.path == "/openapi.json"
        return httpx.Response(200, json={"components": {"schemas": {}}})

    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(handle)
    ) as client:
        result = run(client, live=True)
    assert result["error"] == "runtime_identity_guard_required"


def test_stream_total_deadline_and_limit_are_bounded():
    from scripts.cloud.vast.chat_smoke import SmokeError, _events

    response = httpx.Response(200, text=": keepalive\n")
    with pytest.raises(SmokeError, match="stream_deadline_exceeded"):
        list(_events(response, deadline=5, clock=lambda: 6))
    response = httpx.Response(200, text="x" * 1_000_001)
    with pytest.raises(SmokeError, match="stream_limit_exceeded"):
        list(_events(response, deadline=5, clock=lambda: 0))
