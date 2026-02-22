"""Testy jednostkowe dla CloudProvisioner."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.helpers.url_fixtures import http_url
from venom_core.infrastructure.cloud_provisioner import (
    CloudProvisioner,
    CloudProvisionerError,
)


def _create_temp_compose_file(compose_content: str) -> str:
    """Tworzy tymczasowy plik docker-compose i zwraca ścieżkę."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(compose_content)
        return f.name


@pytest.fixture
def temp_ssh_key():
    """Fixture dla tymczasowego klucza SSH."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
        f.write("fake ssh key")
        key_path = f.name
    yield key_path
    Path(key_path).unlink(missing_ok=True)


def test_cloud_provisioner_initialization(temp_ssh_key):
    """Test inicjalizacji CloudProvisioner."""
    provisioner = CloudProvisioner(
        ssh_key_path=temp_ssh_key,
        default_user="testuser",
        timeout=60,
    )

    assert provisioner.ssh_key_path == temp_ssh_key
    assert provisioner.default_user == "testuser"
    assert provisioner.timeout == 60


def test_cloud_provisioner_nonexistent_key():
    """Test inicjalizacji z nieistniejącym kluczem."""
    # Powinien ostrzec, ale nie crashować
    provisioner = CloudProvisioner(
        ssh_key_path="/nonexistent/key.pem",
        default_user="root",
    )
    assert provisioner.ssh_key_path == "/nonexistent/key.pem"


@pytest.mark.asyncio
async def test_execute_ssh_command_no_credentials():
    """Test wykonania SSH bez credentials."""
    provisioner = CloudProvisioner(ssh_key_path=None)

    with pytest.raises(CloudProvisionerError, match="Brak klucza SSH"):
        await provisioner._execute_ssh_command(
            host="test.example.com",
            command="ls",
        )


@pytest.mark.asyncio
@patch("venom_core.infrastructure.cloud_provisioner.asyncssh.connect")
async def test_execute_ssh_command_success(mock_connect, temp_ssh_key):
    """Test pomyślnego wykonania komendy SSH."""
    # Mock SSH connection
    mock_result = MagicMock()
    mock_result.stdout = "Hello World"
    mock_result.stderr = ""
    mock_result.exit_status = 0

    mock_conn = AsyncMock()
    mock_conn.run = AsyncMock(return_value=mock_result)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_connect.return_value = mock_conn

    provisioner = CloudProvisioner(ssh_key_path=temp_ssh_key)
    stdout, stderr, exit_code = await provisioner._execute_ssh_command(
        host="test.example.com",
        command="echo 'Hello World'",
    )

    assert stdout == "Hello World"
    assert stderr == ""
    assert exit_code == 0


@pytest.mark.asyncio
@patch("venom_core.infrastructure.cloud_provisioner.asyncssh.connect")
async def test_execute_ssh_command_failure(mock_connect, temp_ssh_key):
    """Test nieudanego wykonania komendy SSH."""
    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.stderr = "Command not found"
    mock_result.exit_status = 127

    mock_conn = AsyncMock()
    mock_conn.run = AsyncMock(return_value=mock_result)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_connect.return_value = mock_conn

    provisioner = CloudProvisioner(ssh_key_path=temp_ssh_key)
    stdout, stderr, exit_code = await provisioner._execute_ssh_command(
        host="test.example.com",
        command="nonexistent_command",
    )

    assert exit_code == 127
    assert "Command not found" in stderr


@pytest.mark.asyncio
@patch("venom_core.infrastructure.cloud_provisioner.asyncssh.connect")
async def test_provision_server_success(mock_connect, temp_ssh_key):
    """Test pomyślnego provisioningu serwera."""
    # Mock wszystkie komendy jako sukces
    mock_result = MagicMock()
    mock_result.stdout = "Docker version 20.10.0"
    mock_result.stderr = ""
    mock_result.exit_status = 0

    mock_conn = AsyncMock()
    mock_conn.run = AsyncMock(return_value=mock_result)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_connect.return_value = mock_conn

    provisioner = CloudProvisioner(ssh_key_path=temp_ssh_key)
    results = await provisioner.provision_server(host="test.example.com")

    # Sprawdź czy wszystkie komendy zostały wykonane
    assert "apt-get update" in results
    assert results["apt-get update"] == "OK"


@pytest.mark.asyncio
@patch("venom_core.infrastructure.cloud_provisioner.asyncssh.connect")
async def test_deploy_stack_success(mock_connect, temp_ssh_key):
    """Test pomyślnego deploymentu stacku."""
    # Stwórz tymczasowy docker-compose.yml
    compose_path = await asyncio.to_thread(
        _create_temp_compose_file, "version: '3'\nservices:\n  app:\n    image: nginx"
    )

    try:
        # Mock SSH connection i SFTP
        mock_result = MagicMock()
        mock_result.stdout = "Container started"
        mock_result.stderr = ""
        mock_result.exit_status = 0

        mock_sftp = AsyncMock()
        mock_sftp.put = AsyncMock()
        mock_sftp.__aenter__ = AsyncMock(return_value=mock_sftp)
        mock_sftp.__aexit__ = AsyncMock(return_value=None)

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        mock_conn.start_sftp_client = MagicMock(return_value=mock_sftp)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_connect.return_value = mock_conn

        provisioner = CloudProvisioner(ssh_key_path=temp_ssh_key)
        result = await provisioner.deploy_stack(
            host="test.example.com",
            stack_name="test_app",
            compose_file_path=compose_path,
        )

        assert result["status"] == "deployed"
        assert result["stack_name"] == "test_app"
        assert result["host"] == "test.example.com"

    finally:
        Path(compose_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_deploy_stack_nonexistent_compose():
    """Test deploymentu z nieistniejącym plikiem compose."""
    provisioner = CloudProvisioner()

    with pytest.raises(CloudProvisionerError, match="nie istnieje"):
        await provisioner.deploy_stack(
            host="test.example.com",
            stack_name="test",
            compose_file_path="/nonexistent/compose.yml",
        )


@pytest.mark.asyncio
@patch("venom_core.infrastructure.cloud_provisioner.asyncssh.connect")
async def test_check_deployment_health(mock_connect, temp_ssh_key):
    """Test sprawdzania stanu deploymentu."""
    mock_result = MagicMock()
    mock_result.stdout = "app_container   Up 5 minutes"
    mock_result.stderr = ""
    mock_result.exit_status = 0

    mock_conn = AsyncMock()
    mock_conn.run = AsyncMock(return_value=mock_result)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_connect.return_value = mock_conn

    provisioner = CloudProvisioner(ssh_key_path=temp_ssh_key)
    result = await provisioner.check_deployment_health(
        host="test.example.com",
        stack_name="test_app",
    )

    assert result["status"] == "healthy"
    assert "app_container" in result["containers"]


def test_start_broadcasting():
    """Test uruchamiania mDNS broadcasting."""
    provisioner = CloudProvisioner(service_port=8000)
    result = provisioner.start_broadcasting(service_name="test-venom")

    # Broadcasting może nie działać w środowisku testowym bez pełnej sieci
    # Ale powinien zwrócić odpowiedź
    assert "status" in result
    assert result["status"] in ["active", "error"]

    if result["status"] == "active":
        assert "service_name" in result
        assert "ip" in result
        assert "port" in result
        assert result["port"] == 8000
        assert "service_url" in result

    # Cleanup
    provisioner.stop_broadcasting()


def test_stop_broadcasting():
    """Test zatrzymywania mDNS broadcasting."""
    provisioner = CloudProvisioner()

    # Spróbuj zatrzymać bez uruchomienia
    result = provisioner.stop_broadcasting()
    assert result["status"] in ["stopped", "not_running"]


def test_get_service_url():
    """Test pobierania URL usługi."""
    provisioner = CloudProvisioner(service_port=8000)

    # Test domyślnej nazwy
    url = provisioner.get_service_url()
    assert url == http_url("venom.local", 8000)

    # Test z własną nazwą
    url = provisioner.get_service_url("test-agent")
    assert url == http_url("test-agent.local", 8000)

    # Test z nazwą zawierającą .local
    url = provisioner.get_service_url("agent.local")
    assert url == http_url("agent.local", 8000)


def test_get_service_url_with_custom_port():
    """Test URL usługi z niestandardowym portem."""
    provisioner = CloudProvisioner(service_port=9000)
    url = provisioner.get_service_url("custom")
    assert url == http_url("custom.local", 9000)


@pytest.mark.asyncio
async def test_deploy_stack_invalid_stack_name():
    """Test deploymentu z nieprawidłową nazwą stacku (security)."""
    provisioner = CloudProvisioner()

    # Stwórz tymczasowy docker-compose.yml
    compose_path = await asyncio.to_thread(
        _create_temp_compose_file, "version: '3'\nservices:\n  app:\n    image: nginx"
    )

    try:
        # Test path traversal attempt
        with pytest.raises(CloudProvisionerError, match="Invalid stack_name"):
            await provisioner.deploy_stack(
                host="test.example.com",
                stack_name="../../etc",
                compose_file_path=compose_path,
            )

        # Test command injection attempt
        with pytest.raises(CloudProvisionerError, match="Invalid stack_name"):
            await provisioner.deploy_stack(
                host="test.example.com",
                stack_name="test; rm -rf /",
                compose_file_path=compose_path,
            )

        # Test invalid characters
        with pytest.raises(CloudProvisionerError, match="Invalid stack_name"):
            await provisioner.deploy_stack(
                host="test.example.com",
                stack_name="test$app",
                compose_file_path=compose_path,
            )

    finally:
        Path(compose_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_check_deployment_health_invalid_stack_name():
    """Test sprawdzania zdrowia z nieprawidłową nazwą stacku (security)."""
    provisioner = CloudProvisioner()

    with pytest.raises(CloudProvisionerError, match="Invalid stack_name"):
        await provisioner.check_deployment_health(
            host="test.example.com",
            stack_name="../etc/passwd",
        )


@pytest.mark.asyncio
async def test_register_in_hive_no_url():
    """Test rejestracji w Ulu bez skonfigurowanego URL."""
    provisioner = CloudProvisioner()
    provisioner.hive_url = ""

    result = await provisioner.register_in_hive()

    assert result["status"] == "skipped"
    assert "not configured" in result["message"]
    assert not provisioner.hive_registered


@pytest.mark.asyncio
async def test_register_in_hive_success():
    """Test pomyślnej rejestracji w Ulu."""
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "registered",
        "agent_id": "test-agent-123",
        "message": "Agent registered successfully",
    }

    with patch(
        "venom_core.infrastructure.cloud_provisioner.TrafficControlledHttpClient"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client.apost = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        provisioner = CloudProvisioner()
        result = await provisioner.register_in_hive(hive_url="https://hive.example.com")

    assert result["status"] == "registered"
    assert result["hive_url"] == "https://hive.example.com"
    assert "hive_response" in result
    assert provisioner.hive_registered is True


@pytest.mark.asyncio
async def test_register_in_hive_error_status():
    """Test rejestracji w Ulu z błędnym statusem odpowiedzi."""
    # Mock response z błędem
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "Forbidden: Invalid token"

    with patch(
        "venom_core.infrastructure.cloud_provisioner.TrafficControlledHttpClient"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client.apost = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        provisioner = CloudProvisioner()
        result = await provisioner.register_in_hive(hive_url="https://hive.example.com")

    assert result["status"] == "error"
    assert result["status_code"] == 403
    assert "Forbidden" in result["message"]
    assert provisioner.hive_registered is False


@pytest.mark.asyncio
async def test_register_in_hive_timeout():
    """Test timeout podczas rejestracji w Ulu."""
    with patch(
        "venom_core.infrastructure.cloud_provisioner.TrafficControlledHttpClient"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client.apost = AsyncMock(
            side_effect=__import__("httpx").TimeoutException("")
        )
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        provisioner = CloudProvisioner()
        result = await provisioner.register_in_hive(hive_url="https://hive.example.com")

    assert result["status"] == "timeout"
    assert "Timeout" in result["message"]


@pytest.mark.asyncio
async def test_register_in_hive_with_metadata():
    """Test rejestracji w Ulu z dodatkowymi metadanymi."""
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"status": "ok"}

    with patch(
        "venom_core.infrastructure.cloud_provisioner.TrafficControlledHttpClient"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client.apost = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        provisioner = CloudProvisioner()
        custom_metadata = {
            "location": "datacenter-1",
            "environment": "production",
        }

        result = await provisioner.register_in_hive(
            hive_url="https://hive.example.com", metadata=custom_metadata
        )

    assert result["status"] == "registered"

    # Sprawdź czy metadata została przekazana w POST
    call_args = mock_client.apost.call_args
    payload = call_args[1]["json"]
    assert "location" in payload
    assert payload["location"] == "datacenter-1"
    assert payload["environment"] == "production"
