import pytest
from fastapi.testclient import TestClient

from venom_core.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_lessons_purge_endpoint(client):
    """
    Testuje czy endpoint /api/v1/lessons/purge jest dostępny i działa.
    To rozwiązuje błąd 404 zgłoszony przez użytkownika.
    """
    # 1. Sprawdzenie statusu (opcjonalnie, żeby mieć pewność że coś jest w bazie)
    stats_resp = client.get("/api/v1/lessons/stats")
    assert stats_resp.status_code == 200

    # 2. Wywołanie purge bez force=true (powinno zwrócić 400)
    purge_fail_resp = client.delete("/api/v1/lessons/purge")
    assert purge_fail_resp.status_code == 400
    assert "force=true" in purge_fail_resp.json()["detail"]

    # 3. Wywołanie purge z force=true
    purge_success_resp = client.delete(
        "/api/v1/lessons/purge", params={"force": "true"}
    )
    assert purge_success_resp.status_code == 200
    assert purge_success_resp.json()["status"] == "success"
    assert "Wyczyszczono" in purge_success_resp.json()["message"]


def test_lessons_pruning_endpoints(client):
    """
    Testuje czy pozostałe endpointy zarządzania lekcjami są dostępne pod nowym adresem.
    """
    # Prune latest
    resp = client.delete("/api/v1/lessons/prune/latest", params={"count": 1})
    # Nawet jeśli 0 usuniętych, status powinien być 200
    assert resp.status_code == 200

    # Prune TTL
    resp = client.delete("/api/v1/lessons/prune/ttl", params={"days": 30})
    assert resp.status_code == 200

    # Dedupe
    resp = client.post("/api/v1/lessons/dedupe")
    assert resp.status_code == 200


def test_lessons_learning_toggle(client):
    """
    Testuje toggle uczenia.
    """
    # Status
    resp = client.get("/api/v1/lessons/learning/status")
    assert resp.status_code == 200
    initial_status = resp.json()["enabled"]

    # Toggle
    resp = client.post(
        "/api/v1/lessons/learning/toggle", json={"enabled": not initial_status}
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] == (not initial_status)

    # Toggle back
    client.post("/api/v1/lessons/learning/toggle", json={"enabled": initial_status})
