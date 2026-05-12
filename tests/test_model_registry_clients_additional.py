"""Additional coverage tests for model_registry_clients helpers and clients."""

from __future__ import annotations

import html
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import venom_core.main as main_module
from venom_core.core import model_registry_clients as mrc
from venom_core.core.ollama_runtime_capabilities import (
    _resolve_compatibility_profile,
    normalize_ollama_show_payload,
)
from venom_core.core.ollama_runtime_probe import (
    _probe_audio,
    _probe_thinking,
    _probe_tools,
    _probe_vision,
    probe_ollama_runtime_capabilities,
    resolve_voice_pipeline,
)


def test_normalize_hf_papers_month_invalid_falls_back_current():
    value = mrc._normalize_hf_papers_month("2024-99")
    assert len(value) == 7
    assert value[4] == "-"


def test_parse_hf_blog_feed_strips_html_and_limits_items():
    payload = """<?xml version="1.0"?>
    <rss><channel>
      <item><title>A</title><link>https://a</link><description><![CDATA[<b>x</b>]]></description><pubDate>now</pubDate></item>
      <item><title>B</title><link>https://b</link><description>plain</description><pubDate>later</pubDate></item>
    </channel></rss>"""
    parsed = mrc._parse_hf_blog_feed(payload, limit=1)
    assert len(parsed) == 1
    assert parsed[0]["title"] == "A"
    assert parsed[0]["summary"] == "x"


def test_parse_hf_papers_html_invalid_and_valid_paths():
    assert mrc._parse_hf_papers_html("<html></html>", limit=3) == []

    props = {
        "dailyPapers": [
            {
                "title": "Paper 1",
                "summary": "S1",
                "publishedAt": "2026-01-01",
                "paper": {"id": "p1", "authors": [{"name": "A1"}]},
            }
        ]
    }
    raw = html.escape(__import__("json").dumps(props))
    payload = f'<div data-target="DailyPapers" data-props="{raw}"></div>'
    parsed = mrc._parse_hf_papers_html(payload, limit=5)
    assert len(parsed) == 1
    assert parsed[0]["url"] == "https://huggingface.co/papers/p1"
    assert parsed[0]["authors"] == ["A1"]


def test_extract_ollama_helpers():
    assert mrc._extract_ollama_model_name("/library/llama3.1") == "llama3.1"
    assert mrc._extract_ollama_model_name("/other/x") is None

    anchor = MagicMock()
    anchor.find.return_value = None
    anchor.get_text.return_value = "llama3.1 compact model"
    assert mrc._extract_ollama_description(anchor, "llama3.1") == "compact model"


def test_parse_ollama_search_html_with_fake_bs4(monkeypatch):
    class _Anchor:
        def __init__(self, href: str, text: str):
            self._href = href
            self._text = text

        def get(self, key):
            return self._href if key == "href" else None

        def find(self, _name):
            return None

        def get_text(self, *_args, **_kwargs):
            return self._text

    class _Soup:
        def __init__(self, _payload, _parser):
            pass

        def find_all(self, _tag, href=True):
            _ = href
            return [
                _Anchor("/library/phi4-mini", "phi4-mini compact"),
                _Anchor("/library/phi4-mini", "duplicate"),
                _Anchor("/library/qwen2.5", "qwen2.5 coder"),
            ]

    fake_bs4 = SimpleNamespace(BeautifulSoup=_Soup)
    monkeypatch.setitem(__import__("sys").modules, "bs4", fake_bs4)

    parsed = mrc._parse_ollama_search_html("<html></html>", limit=5)
    assert [item["name"] for item in parsed] == ["phi4-mini", "qwen2.5"]


def test_parse_ollama_search_html_without_bs4_returns_empty(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "bs4":
            raise ImportError("missing-bs4")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)
    parsed = mrc._parse_ollama_search_html("<html></html>", limit=3)
    assert parsed == []


@pytest.mark.asyncio
async def test_ollama_client_remove_model_paths():
    client = mrc.OllamaClient()

    with patch(
        "asyncio.to_thread",
        new=AsyncMock(return_value=SimpleNamespace(returncode=0, stderr="", stdout="")),
    ):
        assert await client.remove_model("ok-model") is True

    with patch(
        "asyncio.to_thread",
        new=AsyncMock(
            return_value=SimpleNamespace(returncode=1, stderr="err", stdout="")
        ),
    ):
        assert await client.remove_model("bad-model") is False

    with patch(
        "asyncio.to_thread",
        new=AsyncMock(
            side_effect=subprocess.TimeoutExpired(cmd="ollama rm", timeout=30)
        ),
    ):
        assert await client.remove_model("timeout-model") is False

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=FileNotFoundError())):
        assert await client.remove_model("missing-bin") is False


@pytest.mark.asyncio
async def test_ollama_client_pull_model_without_streams_returns_false():
    client = mrc.OllamaClient()

    process = SimpleNamespace(
        stdout=None,
        stderr=None,
        returncode=0,
        kill=lambda: None,
        wait=AsyncMock(return_value=0),
    )

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
        assert await client.pull_model("m1") is False


@pytest.mark.asyncio
async def test_hf_fetch_papers_month_handles_redirect():
    client = mrc.HuggingFaceClient()

    first = MagicMock()
    first.is_redirect = True
    first.headers = {"location": "/papers/month/2026-01"}
    first.raise_for_status = MagicMock()
    first.text = ""

    second = MagicMock()
    second.is_redirect = False
    second.headers = {}
    second.raise_for_status = MagicMock()
    second.text = '<div data-target="DailyPapers" data-props="{&quot;dailyPapers&quot;: []}"></div>'

    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(side_effect=[first, second])
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        parsed = await client.fetch_papers_month(limit=3, month="2026-01")
        assert parsed == []
        assert mock_client.aget.await_count == 2


@pytest.mark.asyncio
async def test_hf_fetch_papers_month_non_redirect_uses_raise_for_status():
    client = mrc.HuggingFaceClient()
    response = MagicMock()
    response.is_redirect = False
    response.headers = {}
    response.raise_for_status = MagicMock()
    response.text = '<div data-target="DailyPapers" data-props="{&quot;dailyPapers&quot;: []}"></div>'

    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(return_value=response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        parsed = await client.fetch_papers_month(limit=1, month="2026-01")

    assert parsed == []
    response.raise_for_status.assert_called_once()


def test_remove_cached_model_rejects_path_escape(tmp_path):
    client = mrc.HuggingFaceClient()
    assert client.remove_cached_model(tmp_path, "../outside") is False


@pytest.mark.asyncio
async def test_hf_download_snapshot_returns_none_when_hub_missing():
    client = mrc.HuggingFaceClient()
    with patch.dict(sys.modules, {"huggingface_hub": None}):
        result = await client.download_snapshot("org/model", "/tmp/cache")
    assert result is None


@pytest.mark.asyncio
async def test_ollama_list_tags_uses_traffic_control_client():
    client = mrc.OllamaClient(endpoint="http://localhost:11434")
    mock_response = MagicMock()
    mock_response.json.return_value = {"models": [{"name": "llama3:latest"}]}

    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        payload = await client.list_tags()

    assert payload["models"][0]["name"] == "llama3:latest"
    assert mock_client_cls.call_args.kwargs["provider"] == "ollama"
    mock_client.aget.assert_awaited_once()


@pytest.mark.asyncio
async def test_ollama_list_tags_returns_empty_on_exception():
    client = mrc.OllamaClient(endpoint="http://localhost:11434")
    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(side_effect=RuntimeError("boom"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        payload = await client.list_tags()

    assert payload == {"models": []}


@pytest.mark.asyncio
async def test_ollama_search_models_success_and_failure():
    client = mrc.OllamaClient(endpoint="http://localhost:11434")

    response = MagicMock()
    response.text = "<html></html>"
    with patch(
        "venom_core.core.model_registry_clients._parse_ollama_search_html",
        return_value=[{"name": "qwen2.5"}],
    ):
        with patch(
            "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aget = AsyncMock(return_value=response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            data = await client.search_models("qwen", limit=3)
            assert data == [{"name": "qwen2.5"}]

    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(side_effect=RuntimeError("catalog down"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        data = await client.search_models("qwen", limit=3)
        assert data == []


@pytest.mark.asyncio
async def test_ollama_pull_model_stream_success_and_failed_return_code():
    client = mrc.OllamaClient()
    progress = AsyncMock()

    class _Stream:
        def __init__(self, lines):
            self._lines = list(lines)

        async def readline(self):
            return self._lines.pop(0) if self._lines else b""

    process_ok = SimpleNamespace(
        stdout=_Stream([b"pulling...\n", b"done\n", b""]),
        stderr=SimpleNamespace(read=AsyncMock(return_value=b"")),
        returncode=0,
        wait=AsyncMock(return_value=0),
        kill=MagicMock(),
    )
    with patch(
        "asyncio.create_subprocess_exec", new=AsyncMock(return_value=process_ok)
    ):
        assert await client.pull_model("m1", progress_callback=progress) is True
    assert progress.await_count >= 1

    process_fail = SimpleNamespace(
        stdout=_Stream([b"step\n", b""]),
        stderr=SimpleNamespace(read=AsyncMock(return_value=b"failed")),
        returncode=1,
        wait=AsyncMock(return_value=1),
        kill=MagicMock(),
    )
    with patch(
        "asyncio.create_subprocess_exec", new=AsyncMock(return_value=process_fail)
    ):
        assert await client.pull_model("m1") is False


@pytest.mark.asyncio
async def test_hf_list_models_fallbacks_from_trending_to_downloads():
    client = mrc.HuggingFaceClient(token="secret")

    status_error = httpx.HTTPStatusError(
        "bad status",
        request=MagicMock(),
        response=MagicMock(status_code=503),
    )
    fallback_response = MagicMock()
    fallback_response.json.return_value = [{"id": "google/gemma-2b-it"}]

    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(side_effect=[status_error, fallback_response])
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        payload = await client.list_models(sort="trendingScore", limit=5)

    assert payload == [{"id": "google/gemma-2b-it"}]
    assert mock_client.aget.await_count == 2
    first_call = mock_client.aget.await_args_list[0]
    second_call = mock_client.aget.await_args_list[1]
    assert first_call.kwargs["params"]["sort"] == "trendingScore"
    assert second_call.kwargs["params"]["sort"] == "downloads"


@pytest.mark.asyncio
async def test_hf_list_models_non_trending_http_error_is_raised():
    client = mrc.HuggingFaceClient(token="secret")
    status_error = httpx.HTTPStatusError(
        "bad status",
        request=MagicMock(),
        response=MagicMock(status_code=503),
    )
    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(side_effect=status_error)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(httpx.HTTPStatusError):
            await client.list_models(sort="downloads", limit=5)


@pytest.mark.asyncio
async def test_hf_search_models_non_list_and_exception_paths():
    client = mrc.HuggingFaceClient(token="tok")
    response = MagicMock()
    response.json.return_value = {"unexpected": True}

    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(return_value=response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        assert await client.search_models("phi", limit=2) == []

    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(side_effect=RuntimeError("hf down"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        assert await client.search_models("phi", limit=2) == []


@pytest.mark.asyncio
async def test_hf_fetch_blog_feed_uses_traffic_control_client():
    client = mrc.HuggingFaceClient()
    response = MagicMock()
    response.text = """<?xml version="1.0"?>
    <rss><channel>
      <item><title>Blog</title><link>https://huggingface.co/blog/a</link><description>desc</description></item>
    </channel></rss>"""

    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(return_value=response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        items = await client.fetch_blog_feed(limit=3)

    assert len(items) == 1
    assert items[0]["title"] == "Blog"
    assert mock_client_cls.call_args.kwargs["provider"] == "huggingface"
    mock_client.aget.assert_awaited_once()


def test_parse_hf_blog_feed_channel_missing_returns_empty():
    payload = "<?xml version='1.0'?><rss><no-channel /></rss>"
    assert mrc._parse_hf_blog_feed(payload, limit=2) == []


def test_parse_hf_papers_html_invalid_data_props_shape_returns_empty():
    raw = html.escape("[]")
    payload = f'<div data-target="DailyPapers" data-props="{raw}"></div>'
    assert mrc._parse_hf_papers_html(payload, limit=2) == []


def test_parse_hf_papers_html_missing_data_props_end_quote_returns_empty():
    payload = '<div data-target="DailyPapers" data-props="'
    assert mrc._parse_hf_papers_html(payload, limit=2) == []


@pytest.mark.asyncio
async def test_hf_download_snapshot_success_calls_callback(tmp_path):
    called = []

    async def _progress(message: str):
        called.append(message)

    fake_module = SimpleNamespace(
        snapshot_download=lambda **kwargs: str(
            tmp_path / kwargs["repo_id"].replace("/", "--")
        )
    )

    client = mrc.HuggingFaceClient(token="tok")
    with patch.dict(sys.modules, {"huggingface_hub": fake_module}):
        result = await client.download_snapshot(
            "org/model",
            str(tmp_path),
            progress_callback=_progress,
        )

    assert result is not None
    assert called and "Pobieranie org/model" in called[0]


def test_remove_cached_model_success_missing_and_rmtree_error(tmp_path, monkeypatch):
    client = mrc.HuggingFaceClient()
    model_name = "org/model"
    model_dir = tmp_path / "org--model"
    model_dir.mkdir(parents=True, exist_ok=True)

    assert client.remove_cached_model(tmp_path, model_name) is True
    assert model_dir.exists() is False

    assert client.remove_cached_model(tmp_path, model_name) is False

    model_dir.mkdir(parents=True, exist_ok=True)

    def _raise(*_args, **_kwargs):
        raise OSError("cannot remove")

    monkeypatch.setattr(mrc.shutil, "rmtree", _raise)
    assert client.remove_cached_model(tmp_path, model_name) is False


@pytest.mark.asyncio
async def test_ollama_get_model_show_and_chat_use_traffic_control_client():
    client = mrc.OllamaClient(endpoint="http://localhost:11434")
    show_response = MagicMock()
    show_response.json.return_value = {"model": "gemma4:latest"}
    chat_response = MagicMock()
    chat_response.json.return_value = {"message": {"content": "ok"}}

    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.apost = AsyncMock(side_effect=[show_response, chat_response])
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        show_payload = await client.get_model_show("gemma4:latest")
        chat_payload = await client.chat({"model": "gemma4:latest"})

    assert show_payload["model"] == "gemma4:latest"
    assert chat_payload["message"]["content"] == "ok"


@pytest.mark.asyncio
async def test_ollama_get_model_show_and_chat_failure_paths_return_empty_dict():
    client = mrc.OllamaClient(endpoint="http://localhost:11434")

    with patch(
        "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.apost = AsyncMock(side_effect=Exception("boom"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        assert await client.get_model_show("gemma4:latest") == {}
        assert await client.chat({"model": "gemma4:latest"}) == {}


@pytest.mark.asyncio
async def test_voice_runtime_helpers_cover_branches(monkeypatch):
    assert _resolve_compatibility_profile({"audio"}) == "multimodal_audio"
    assert _resolve_compatibility_profile({"vision"}) == "vision_text"
    assert _resolve_compatibility_profile({"tools"}) == "text_tools"
    assert _resolve_compatibility_profile({"thinking"}) == "text_thinking"
    assert _resolve_compatibility_profile(set()) == "legacy_text_only"

    caps = normalize_ollama_show_payload(
        model_name="gemma4:latest",
        payload={
            "capabilities": ["completion", "vision", "audio", "tools", "thinking"],
            "details": {"parameter_size": "8.0B", "context_length": "131072"},
            "model_info": {"general.context_length": "131072"},
        },
        endpoint="http://localhost:11434/",
        probe_status="verified",
    )

    assert caps.endpoint == "http://localhost:11434"
    assert caps.to_dict()["probe_status"] == "verified"
    assert caps.context_length == 131072

    class ProbeClient:
        def __init__(self):
            self.endpoint = "http://localhost:11434"

        async def get_model_show(self, model_name: str):
            return {
                "capabilities": ["completion", "vision", "audio", "tools", "thinking"],
                "details": {"parameter_size": "8.0B"},
                "model_info": {"gemma4.context_length": 131072},
            }

        async def chat(self, payload):
            if payload.get("think"):
                return {
                    "message": {
                        "role": "assistant",
                        "thinking": "trace",
                        "content": "answer",
                    }
                }
            if payload.get("tools"):
                return {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {"function": {"name": "noop_status", "arguments": {}}}
                        ],
                        "content": "",
                    }
                }
            if payload.get("messages") and payload["messages"][-1].get("images"):
                return {"message": {"role": "assistant", "content": "image ok"}}
            return {"message": {"role": "assistant", "content": "audio ok"}}

    caps = await probe_ollama_runtime_capabilities(
        client=ProbeClient(),
        model_name="gemma4:latest",
        endpoint="http://localhost:11434",
    )
    decision = resolve_voice_pipeline(caps)
    assert caps.probe_status == "verified"
    assert decision.reasoning == "think_api"
    assert decision.tools == "policy_gated_tools"
    assert decision.vision == "images_api"

    class EmptyProbeClient(ProbeClient):
        async def get_model_show(self, model_name: str):
            return {}

        async def chat(self, payload):
            return {"message": {"role": "assistant", "content": ""}}

    empty_caps = await probe_ollama_runtime_capabilities(
        client=EmptyProbeClient(),
        model_name="missing-model",
        endpoint="http://localhost:11434",
    )
    assert empty_caps.probe_status == "failed"

    assert (await _probe_thinking(EmptyProbeClient(), "model"))["status"] == "failed"
    assert (await _probe_tools(EmptyProbeClient(), "model"))["status"] == "failed"
    assert (await _probe_vision(EmptyProbeClient(), "model"))["status"] == "failed"
    assert (await _probe_audio(EmptyProbeClient(), "model"))["status"] == "failed"


@pytest.mark.asyncio
async def test_build_voice_runtime_snapshot_and_audio_status(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_active_llm_runtime",
        lambda: SimpleNamespace(
            runtime_id="ollama@localhost",
            provider="ollama",
            model_name="gemma4:latest",
            endpoint="http://localhost:11434",
            config_hash="abc123",
        ),
    )

    class DummyCaps:
        def to_dict(self):
            return {"compatibility_profile": "multimodal_audio"}

    class DummyPipeline:
        def to_dict(self):
            return {"stt": "faster_whisper"}

    monkeypatch.setattr(
        main_module,
        "OllamaClient",
        lambda endpoint: SimpleNamespace(endpoint=endpoint),
    )
    monkeypatch.setattr(
        main_module,
        "probe_ollama_runtime_capabilities",
        AsyncMock(return_value=DummyCaps()),
    )
    monkeypatch.setattr(
        main_module,
        "resolve_voice_pipeline",
        lambda _caps: DummyPipeline(),
    )

    snapshot = await main_module._build_voice_runtime_snapshot()
    assert snapshot["provider"] == "ollama"
    assert snapshot["voice_pipeline"]["stt"] == "faster_whisper"

    monkeypatch.setattr(main_module, "audio_stream_handler", None)
    monkeypatch.setattr(
        main_module,
        "_build_voice_runtime_snapshot",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    request = SimpleNamespace(url_for=lambda name: f"https://example.test/{name}")
    status = await main_module.audio_status_endpoint(request)
    assert status["runtime_snapshot"]["error"] == "boom"
