"""Durable installation identity contract, independent of optional modules."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes.transport import router
from venom_core.config import SETTINGS
from venom_core.services.transport_identity import read_transport_identity


@pytest.fixture
def identity_path(tmp_path, monkeypatch):
    path = tmp_path / "transport" / "identity.json"
    monkeypatch.setattr(SETTINGS, "VENOM_TRANSPORT_IDENTITY_FILE", str(path))
    return path


def test_identity_is_durable_private_and_passive(identity_path):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        first = client.get("/api/v1/transport/identity")
        second = client.get("/api/v1/transport/identity")
    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["protocol_version"] == 1
    assert first.json()["service_role"] == "venom"
    assert len(first.json()["peer_id"]) == 32
    assert identity_path.stat().st_mode & 0o777 == 0o600
    assert len(first.content) < 256


def test_concurrent_first_reads_keep_one_identity(identity_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: read_transport_identity(), range(16)))
    assert all(result == results[0] for result in results)


@pytest.mark.parametrize(
    "content", ["{}", '{"peer_id":""}', '{"peer_id":"bad id"}', "[]", "bad", "x" * 1025]
)
def test_invalid_identity_is_not_replaced(identity_path, content):
    identity_path.parent.mkdir()
    identity_path.write_text(content)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/api/v1/transport/identity")
    assert response.status_code == 503
    assert response.json()["detail"]["reason_code"] == "TRANSPORT_IDENTITY_UNAVAILABLE"
    assert identity_path.read_text() == content


def test_symlink_is_rejected_without_changing_target(identity_path, tmp_path):
    target = tmp_path / "existing.json"
    target.write_text(json.dumps({"peer_id": "other"}))
    identity_path.parent.mkdir()
    identity_path.symlink_to(target)
    with pytest.raises(OSError):
        read_transport_identity()
    assert json.loads(target.read_text()) == {"peer_id": "other"}


def test_existing_canonical_peer_id_is_supported(identity_path):
    identity_path.parent.mkdir()
    identity_path.write_text(
        json.dumps({"peer_id": "0123456789abcdef0123456789abcdef"})
    )
    assert read_transport_identity()["peer_id"] == "0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize(
    "peer_id", ["installation-1", "a" * 31, "a" * 33, "A" * 32, "g" * 32]
)
def test_v1_rejects_noncanonical_persisted_peer_ids(identity_path, peer_id):
    identity_path.parent.mkdir()
    identity_path.write_text(json.dumps({"peer_id": peer_id}))
    with pytest.raises(ValueError):
        read_transport_identity()
