from fastapi.testclient import TestClient

from venom_core.api.schemas.system import ApiMapResponse, ConnectionStatus
from venom_core.main import app

client = TestClient(app)


def test_get_api_map_contract():
    """Weryfikuje, czy endpoint /api/v1/system/api-map zwraca poprawny schemat."""
    response = client.get("/api/v1/system/api-map")
    assert response.status_code == 200

    # Walidacja Pydantic (czy odpowiedź pasuje do modelu)
    api_map = ApiMapResponse(**response.json())

    # Sprawdzenie czy mamy sekcje
    assert len(api_map.internal_connections) > 0
    assert isinstance(api_map.internal_connections, list)
    assert isinstance(api_map.external_connections, list)

    # Sprawdzenie pól w pierwszym połączeniu wewnętrznym
    first_internal = api_map.internal_connections[0]
    assert hasattr(first_internal, "source_component")
    assert hasattr(first_internal, "target_component")
    assert hasattr(first_internal, "methods")
    assert isinstance(first_internal.methods, list)

    # Sprawdzenie przykładowego połączenia wewnętrznego
    backend_conn = next(
        (
            c
            for c in api_map.internal_connections
            if c.source_component == "Backend API"
            and c.target_component == "Frontend (Next.js)"
        ),
        None,
    )
    assert backend_conn is not None
    assert backend_conn.protocol in ["http", "ws"]
    assert backend_conn.status == ConnectionStatus.OK
    assert backend_conn.is_critical is True


def test_api_map_has_external_connections_if_configured():
    """Weryfikuje obecność połączeń zewnętrznych (zależnie od configu)."""
    # Domyślny config w testach może mieć różne wartości,
    # ale zazwyczaj Local LLM jest włączony (lub nie).
    # Sprawdźmy czy lista nie wywala błędu.
    response = client.get("/api/v1/system/api-map")
    assert response.status_code == 200
    data = response.json()

    # Połączenia zewnętrzne mogą być puste, jeśli wszystko wyłączone
    # ale sam klucz musi istnieć
    assert "external_connections" in data


def test_get_api_map_connects_to_service_monitor():
    """Weryfikuje, czy API map pobiera statusy z ServiceMonitor."""
    from unittest.mock import MagicMock, patch

    from venom_core.core.service_monitor import ServiceInfo, ServiceStatus

    # Mock ServiceMonitor
    mock_service_monitor = MagicMock()

    # Symulujemy usługi z różnymi statusami
    mock_services = [
        ServiceInfo(name="Redis", service_type="database", status=ServiceStatus.ONLINE),
        ServiceInfo(
            name="OpenAI API", service_type="api", status=ServiceStatus.OFFLINE
        ),
        ServiceInfo(
            name="LanceDB", service_type="database", status=ServiceStatus.DEGRADED
        ),
    ]
    mock_service_monitor.get_all_services.return_value = mock_services

    # Patchujemy system_deps.get_service_monitor
    with patch(
        "venom_core.api.routes.system_deps.get_service_monitor",
        return_value=mock_service_monitor,
    ):
        # Wywołujemy endpoint
        response = client.get("/api/v1/system/api-map")
        assert response.status_code == 200
        api_map = ApiMapResponse(**response.json())

        # Sprawdzamy czy statusy zostały zaktualizowane
        # Redis -> ONLINE -> OK
        redis_conn = next(
            (c for c in api_map.internal_connections if c.target_component == "Redis"),
            None,
        )
        if redis_conn:
            assert redis_conn.status == ConnectionStatus.OK

        # OpenAI -> OFFLINE -> DOWN
        openai_conn = next(
            (
                c
                for c in api_map.external_connections
                if c.target_component == "OpenAI API"
            ),
            None,
        )
        if openai_conn:
            assert openai_conn.status == ConnectionStatus.DOWN

        # LanceDB -> DEGRADED -> DEGRADED
        lancedb_conn = next(
            (
                c
                for c in api_map.internal_connections
                if c.target_component == "LanceDB"
            ),
            None,
        )
        if lancedb_conn:
            assert lancedb_conn.status == ConnectionStatus.DEGRADED
