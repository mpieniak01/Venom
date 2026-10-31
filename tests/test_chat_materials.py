"""Materials never cross sessions or execute uploaded active content."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from venom_core.api.routes import chat_materials as routes
from venom_core.services.chat_materials import MAX_BYTES, MaterialStore


def test_materials_are_durable_session_scoped_and_delete_is_explicit(tmp_path):
    store = MaterialStore(tmp_path)
    uploaded = store.save("session/a", "notes.md", "text/markdown", b"# Context")
    assert uploaded.kind == "document"
    assert MaterialStore(tmp_path).list("session/a") == [uploaded]
    assert store.read("session/a", uploaded.id)[1] == b"# Context"
    with pytest.raises(HTTPException) as error:
        store.read("session/b", uploaded.id)
    assert error.value.status_code == 404
    store.delete("session/a", uploaded.id)
    assert store.list("session/a") == []


def test_material_upload_checks_stream_limit_mime_and_inert_preview(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(routes, "MaterialStore", lambda: MaterialStore(tmp_path))
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        path = "/api/v1/chat/materials?session_id=one&name=notes.txt"
        assert (
            client.post(
                path, content=b"x", headers={"content-type": "text/html"}
            ).status_code
            == 415
        )
        assert (
            client.post(
                path,
                content=b"x" * (MAX_BYTES + 1),
                headers={"content-type": "text/plain"},
            ).status_code
            == 413
        )
        assert (
            client.post(
                path,
                content=b"x",
                headers={
                    "content-type": "text/plain",
                    "origin": "https://foreign.example",
                },
            ).status_code
            == 403
        )
        response = client.post(
            path,
            content=b"<script>inert</script>",
            headers={"content-type": "text/plain"},
        )
        assert response.status_code == 200
        item = response.json()
        preview = client.get(item["preview_url"])
        assert preview.text == "<script>inert</script>"
        assert preview.headers["x-content-type-options"] == "nosniff"
        assert "sandbox" in preview.headers["content-security-policy"]
        assert (
            client.delete(
                f"/api/v1/chat/materials/{item['id']}?session_id=one"
            ).status_code
            == 204
        )


@pytest.mark.parametrize(
    "name,mime,data,code",
    [
        ("bad", "text/plain", b"", "material_empty"),
        ("bad\nname", "text/plain", b"ok", "material_name_invalid"),
        ("binary.txt", "text/plain", b"\xff", "material_utf8_required"),
        ("binary.txt", "text/plain", b"a\x00b", "material_text_limit"),
        ("long.txt", "text/plain", b"a" * 64001, "material_text_limit"),
        ("fake.png", "image/png", b"not an image", "material_image_invalid"),
        ("active.svg", "image/svg+xml", b"<svg/>", "material_type_unsupported"),
        ("input.mp3", "audio/mpeg", b"ID3", "material_type_unsupported"),
        ("input.mp4", "video/mp4", b"video", "material_type_unsupported"),
    ],
)
def test_invalid_material_is_never_published(tmp_path, name, mime, data, code):
    store = MaterialStore(tmp_path)
    with pytest.raises(HTTPException) as error:
        store.save("one", name, mime, data)
    assert error.value.detail == {"reason_code": code}
    assert store.list("one") == []


def test_noncanonical_ids_session_limit_and_corrupt_content_fail_closed(
    monkeypatch, tmp_path
):
    from venom_core.services import chat_materials

    store = MaterialStore(tmp_path)
    item = store.save("one", "text.txt", "text/plain", b"hi")
    for key in ("../other", "not-an-id", item.id.upper()):
        with pytest.raises(HTTPException) as error:
            store.get("one", key)
        assert error.value.status_code == 404
    monkeypatch.setattr(chat_materials, "MAX_SESSION_FILES", 1)
    with pytest.raises(HTTPException) as error:
        store.save("one", "other.txt", "text/plain", b"x")
    assert error.value.detail == {"reason_code": "material_session_limit"}
    _, binary = store._paths("one", item.id)
    binary.write_bytes(b"truncated")
    with pytest.raises(HTTPException) as error:
        store.read("one", item.id)
    assert error.value.detail == {"reason_code": "material_content_invalid"}


def _image_bytes():
    import io

    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", (2, 2), "green").save(stream, format="PNG")
    return stream.getvalue()


def test_verified_image_keeps_binary_and_mime_not_filename(tmp_path):
    image = _image_bytes()
    store = MaterialStore(tmp_path)
    item = store.save("one", "untrusted.html", "image/png", image)
    assert item.kind == "image"
    assert store.read("one", item.id)[1] == image
    with pytest.raises(HTTPException) as error:
        store.save("one", "mismatch.jpg", "image/jpeg", image)
    assert error.value.detail == {"reason_code": "material_image_invalid"}


def test_preprod_upload_delete_are_readonly_and_foreign_access_denied(
    monkeypatch, tmp_path
):
    from venom_core.config import SETTINGS

    monkeypatch.setattr(routes, "MaterialStore", lambda: MaterialStore(tmp_path))
    monkeypatch.setattr(SETTINGS, "ENVIRONMENT_ROLE", "preprod")
    monkeypatch.setattr(SETTINGS, "ALLOW_DATA_MUTATION", False)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app, client=("127.0.0.1", 1)) as client:
        response = client.post(
            "/api/v1/chat/materials?session_id=one&name=x",
            content=b"hi",
            headers={"content-type": "text/plain"},
        )
        assert response.status_code == 403
        assert (
            response.json()["detail"]["reason_code"] == "material_environment_read_only"
        )
        assert (
            client.delete("/api/v1/chat/materials/unknown?session_id=one").status_code
            == 403
        )
    with TestClient(app, client=("192.0.2.9", 1)) as client:
        assert client.get("/api/v1/chat/materials?session_id=one").status_code == 403


def test_documents_expand_current_and_history_in_original_session(
    monkeypatch, tmp_path
):
    from venom_core.api.schemas.llm_simple import HistoryMessage, SimpleChatRequest
    from venom_core.services import chat_material_payload as payload

    store = MaterialStore(tmp_path)
    monkeypatch.setattr(payload, "MaterialStore", lambda: store)
    item = store.save("one", "note.md", "text/markdown", "Zażółć".encode())
    request = SimpleChatRequest(
        content="Summarize",
        session_id="one",
        material_ids=[item.id],
        history=[
            HistoryMessage(role="user", content="Earlier", material_ids=[item.id])
        ],
    )
    expanded = payload.text_material_request(request)
    assert "Zażółć" in expanded.content
    assert "Zażółć" in expanded.history[0].content
    assert expanded.material_ids == []
    assert expanded.history[0].material_ids == []
    assert request.material_ids == [item.id]
    request.session_id = "other"
    with pytest.raises(HTTPException) as error:
        payload.text_material_request(request)
    assert error.value.status_code == 404
    request.session_id = None
    with pytest.raises(HTTPException) as error:
        payload.text_material_request(request)
    assert error.value.detail == {"reason_code": "material_session_required"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,endpoint,capabilities,expected",
    [
        ("ollama", "http://127.0.0.1:11434/v1", ["vision"], True),
        ("ollama", "http://127.0.0.1:11434/v1", ["completion"], False),
        ("ollama", "https://remote.invalid/v1", ["vision"], False),
        ("openrouter", "https://openrouter.invalid", ["vision"], False),
        ("vllm", "http://localhost:8067/v1", ["vision"], False),
    ],
)
async def test_image_capability_requires_verified_local_ollama(
    monkeypatch, provider, endpoint, capabilities, expected
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from venom_core.services import chat_material_payload as payload

    show = AsyncMock(return_value={"capabilities": capabilities})
    monkeypatch.setattr(
        payload, "OllamaClient", lambda **kw: SimpleNamespace(get_model_show=show)
    )
    runtime = SimpleNamespace(provider=provider, endpoint=endpoint, runtime_id=provider)
    assert await payload.image_capability(runtime, "any-model-name") is expected
    if provider != "ollama" or "remote.invalid" in endpoint:
        show.assert_not_called()
    else:
        show.assert_awaited_once_with("any-model-name")


@pytest.mark.asyncio
async def test_image_payload_reaches_native_adapter_and_never_cloud(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from venom_core.api.schemas.llm_simple import SimpleChatRequest
    from venom_core.services import chat_material_payload as payload

    store = MaterialStore(tmp_path)
    monkeypatch.setattr(payload, "MaterialStore", lambda: store)
    item = store.save("one", "frame.png", "image/png", _image_bytes())
    request = SimpleChatRequest(
        content="Describe", session_id="one", material_ids=[item.id]
    )
    monkeypatch.setattr(payload, "image_capability", AsyncMock(return_value=True))
    messages = await payload.direct_material_messages(
        request, SimpleNamespace(), "vision-model"
    )
    assert messages[-1]["content"][0] == {"type": "text", "text": "Describe"}
    assert messages[-1]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    with pytest.raises(HTTPException) as error:
        payload.text_material_request(request)
    assert error.value.detail == {"reason_code": "material_image_adapter_unsupported"}
    monkeypatch.setattr(payload, "image_capability", AsyncMock(return_value=False))
    material_runtime = SimpleNamespace()
    with pytest.raises(HTTPException) as error:
        await payload.direct_material_messages(request, material_runtime, "text-model")
    assert error.value.detail == {"reason_code": "material_image_adapter_unsupported"}


def test_normal_tasks_cannot_silently_ignore_direct_materials():
    from pydantic import ValidationError

    from venom_core.api.schemas.tasks import TaskRequest

    with pytest.raises(ValidationError):
        TaskRequest(content="hello", material_ids=["reference"])


def test_repeated_upload_reuses_reference_without_double_quota(tmp_path):
    store = MaterialStore(tmp_path)
    first = store.save("one", "note.txt", "text/plain", b"reference")
    retry = store.save("one", "note.txt", "text/plain", b"reference")
    assert first == retry
    assert len(store.list("one")) == 1


def test_context_bound_and_missing_references_fail_before_transport(
    monkeypatch, tmp_path
):
    from venom_core.api.schemas.llm_simple import SimpleChatRequest
    from venom_core.services import chat_material_payload as payload

    store = MaterialStore(tmp_path)
    monkeypatch.setattr(payload, "MaterialStore", lambda: store)
    item = store.save("one", "note.txt", "text/plain", b"x" * 49999)
    value = SimpleChatRequest(
        content="summarize", session_id="one", material_ids=[item.id]
    )
    with pytest.raises(HTTPException) as error:
        payload.text_material_request(value)
    assert error.value.detail == {"reason_code": "material_context_limit"}
    store.delete("one", item.id)
    with pytest.raises(HTTPException) as error:
        payload.text_material_request(value)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_cancelled_and_oversized_chunked_upload_never_publishes(
    monkeypatch, tmp_path
):
    import asyncio
    from types import SimpleNamespace

    monkeypatch.setattr(routes, "MaterialStore", lambda: MaterialStore(tmp_path))

    async def cancelled():
        yield b"first chunk"
        raise asyncio.CancelledError

    value = SimpleNamespace(headers={"content-type": "text/plain"}, stream=cancelled)
    operation = routes.upload_material(value, session_id="one", name="text.txt")
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert MaterialStore(tmp_path).list("one") == []

    async def oversized():
        yield b"x" * (MAX_BYTES // 2)
        yield b"x" * (MAX_BYTES // 2 + 1)

    value.stream = oversized
    with pytest.raises(HTTPException) as error:
        await routes.upload_material(value, session_id="one", name="text.txt")
    assert error.value.status_code == 413
    assert MaterialStore(tmp_path).list("one") == []


def test_total_material_context_bound_includes_every_history_reference(
    monkeypatch, tmp_path
):
    from venom_core.api.schemas.llm_simple import HistoryMessage, SimpleChatRequest
    from venom_core.services import chat_material_payload as payload

    store = MaterialStore(tmp_path)
    monkeypatch.setattr(payload, "MaterialStore", lambda: store)
    monkeypatch.setattr(payload, "MAX_CONTEXT_BYTES", 5)
    item = store.save("one", "doc.txt", "text/plain", b"1234")
    value = SimpleChatRequest(
        content="now",
        session_id="one",
        material_ids=[item.id],
        history=[HistoryMessage(role="user", content="prior", material_ids=[item.id])],
    )
    with pytest.raises(HTTPException) as error:
        payload.material_messages(value, allow_images=False)
    assert error.value.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [{"remote_model": "cloud-vision"}, {"remote_host": "https://cloud.invalid"}],
)
async def test_loopback_ollama_cloud_metadata_never_grants_image_support(
    monkeypatch, metadata
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from venom_core.services import chat_material_payload as payload

    show = AsyncMock(return_value={"capabilities": ["vision"], **metadata})
    monkeypatch.setattr(
        payload, "OllamaClient", lambda **kw: SimpleNamespace(get_model_show=show)
    )
    runtime = SimpleNamespace(
        provider="ollama", endpoint="http://127.0.0.1:11434/v1", runtime_id="ollama"
    )
    assert await payload.image_capability(runtime, "looks-local") is False


@pytest.mark.parametrize("damage", ["metadata", "missing_content", "wrong_owner"])
def test_unreadable_material_does_not_block_list_or_upload(
    monkeypatch, tmp_path, damage
):
    from venom_core.services import chat_materials

    store = MaterialStore(tmp_path)
    valid = store.save("one", "valid.txt", "text/plain", b"valid")
    broken = store.save("one", "broken.txt", "text/plain", b"broken")
    meta, binary = store._paths("one", broken.id)
    if damage == "metadata":
        meta.write_text("invalid json")
    elif damage == "missing_content":
        binary.unlink()
    else:
        import json

        data = json.loads(meta.read_text())
        data["session_id"] = "other"
        meta.write_text(json.dumps(data))
    from types import SimpleNamespace

    warnings = []
    monkeypatch.setattr(
        chat_materials,
        "logger",
        SimpleNamespace(warning=lambda *args: warnings.append(args)),
    )
    monkeypatch.setattr(chat_materials, "MAX_SESSION_FILES", 2)
    assert store.list("one") == [valid]
    assert warnings == [("Skipping unreadable chat material {}", broken.id)]
    uploaded = store.save("one", "new.txt", "text/plain", b"new")
    assert {item.id for item in store.list("one")} == {valid.id, uploaded.id}
    with pytest.raises(HTTPException) as error:
        store.get("one", broken.id)
    assert error.value.status_code == 404
