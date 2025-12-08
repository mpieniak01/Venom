"""Testy jednostkowe dla CloudProvisioner."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.infrastructure.cloud_provisioner import (
    CloudProvisioner,
    CloudProvisionerError,
)


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
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yml", delete=False
    ) as compose_file:
        compose_file.write("version: '3'\nservices:\n  app:\n    image: nginx")
        compose_path = compose_file.name

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


@pytest.mark.asyncio
async def test_configure_domain_placeholder():
    """Test funkcji placeholder configure_domain."""
    provisioner = CloudProvisioner()
    result = await provisioner.configure_domain(
        domain="example.com",
        ip="1.2.3.4",
    )

    assert result["status"] == "not_implemented"
    assert result["domain"] == "example.com"
    assert result["ip"] == "1.2.3.4"
