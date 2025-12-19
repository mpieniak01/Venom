"""Testy jednostkowe dla AssistantSkill."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.core.service_monitor import ServiceInfo, ServiceRegistry, ServiceStatus
from venom_core.execution.skills.assistant_skill import AssistantSkill


@pytest.fixture
def service_registry():
    """Fixture dla ServiceRegistry."""
    registry = ServiceRegistry()
    # Dodaj testową usługę
    test_service = ServiceInfo(
        name="Test Service",
        service_type="api",
        endpoint="http://test.example.com",
        status=ServiceStatus.ONLINE,
        is_critical=True,
    )
    registry.register_service(test_service)
    return registry


@pytest.fixture
def assistant_skill(service_registry):
    """Fixture dla AssistantSkill."""
    return AssistantSkill(service_registry=service_registry)


class TestAssistantSkill:
    """Testy dla AssistantSkill."""

    def test_assistant_skill_initialization(self, assistant_skill):
        """Test inicjalizacji AssistantSkill."""
        assert assistant_skill is not None
        assert assistant_skill.service_registry is not None
        assert assistant_skill.service_monitor is not None

    @pytest.mark.asyncio
    async def test_get_current_time_short(self, assistant_skill):
        """Test pobierania czasu w formacie krótkim."""
        result = await assistant_skill.get_current_time(format_type="short")

        assert "🕐" in result
        assert "Aktualna godzina:" in result
        assert ":" in result  # Format HH:MM zawiera dwukropek

    @pytest.mark.asyncio
    async def test_get_current_time_full(self, assistant_skill):
        """Test pobierania czasu w formacie pełnym."""
        result = await assistant_skill.get_current_time(format_type="full")

        assert "📅" in result
        assert "🕐" in result
        assert "Godzina:" in result
        assert "Strefa czasowa:" in result

        # Sprawdź czy zwraca polską nazwę dnia
        polish_days = [
            "Poniedziałek",
            "Wtorek",
            "Środa",
            "Czwartek",
            "Piątek",
            "Sobota",
            "Niedziela",
        ]
        assert any(day in result for day in polish_days)

    @pytest.mark.asyncio
    async def test_get_current_time_default(self, assistant_skill):
        """Test pobierania czasu z domyślnym formatem."""
        result = await assistant_skill.get_current_time()

        # Domyślnie powinien być format 'full'
        assert "📅" in result
        assert "Godzina:" in result

    @pytest.mark.asyncio
    async def test_get_weather_success(self, assistant_skill):
        """Test pobierania pogody - sukces."""
        # Mock odpowiedzi z wttr.in
        mock_response_data = {
            "current_condition": [
                {
                    "temp_C": "15",
                    "temp_F": "59",
                    "FeelsLikeC": "13",
                    "humidity": "65",
                    "weatherDesc": [{"value": "Partly cloudy"}],
                    "windspeedKmph": "10",
                    "winddir16Point": "NW",
                }
            ],
            "nearest_area": [
                {
                    "areaName": [{"value": "Warsaw"}],
                    "country": [{"value": "Poland"}],
                }
            ],
        }

        async def mock_json():
            return mock_response_data

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = mock_json
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await assistant_skill.get_weather(location="Warsaw")

            assert "🌤️" in result
            assert "Warsaw" in result
            assert "Poland" in result
            assert "15°C" in result
            assert "Partly cloudy" in result
            assert "65%" in result
            assert "10 km/h" in result

    @pytest.mark.asyncio
    async def test_get_weather_imperial_units(self, assistant_skill):
        """Test pobierania pogody z jednostkami imperialskimi."""
        mock_response_data = {
            "current_condition": [
                {
                    "temp_C": "20",
                    "temp_F": "68",
                    "FeelsLikeC": "19",
                    "humidity": "70",
                    "weatherDesc": [{"value": "Clear"}],
                    "windspeedKmph": "5",
                    "winddir16Point": "N",
                }
            ],
            "nearest_area": [
                {
                    "areaName": [{"value": "London"}],
                    "country": [{"value": "UK"}],
                }
            ],
        }

        async def mock_json():
            return mock_response_data

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = mock_json
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await assistant_skill.get_weather(
                location="London", units="imperial"
            )

            assert "68°F" in result
            assert "London" in result

    @pytest.mark.asyncio
    async def test_get_weather_not_found(self, assistant_skill):
        """Test pobierania pogody - lokalizacja nie znaleziona."""
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await assistant_skill.get_weather(location="NonExistentCity")

            assert "✗" in result
            assert "NonExistentCity" in result

    @pytest.mark.asyncio
    async def test_get_weather_timeout(self, assistant_skill):
        """Test pobierania pogody - timeout."""
        import asyncio

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=asyncio.TimeoutError())
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await assistant_skill.get_weather(location="Warsaw")

            assert "✗" in result
            assert "limit czasu" in result.lower()

    @pytest.mark.asyncio
    async def test_check_services_basic(self, assistant_skill):
        """Test sprawdzania usług - podstawowe podsumowanie."""
        # Mock check_health
        with patch.object(
            assistant_skill.service_monitor, "check_health", new=AsyncMock()
        ):
            result = await assistant_skill.check_services(detailed=False)

            assert "🔍" in result
            assert "Status usług" in result
            assert "Online:" in result or "Offline:" in result

    @pytest.mark.asyncio
    async def test_check_services_detailed(self, assistant_skill):
        """Test sprawdzania usług - szczegółowe informacje."""
        # Mock check_health
        with patch.object(
            assistant_skill.service_monitor, "check_health", new=AsyncMock()
        ):
            result = await assistant_skill.check_services(detailed=True)

            assert "🔍" in result
            assert "Szczegóły usług:" in result
            # Powinna być informacja o "Test Service" z fixture
            assert "Test Service" in result

    @pytest.mark.asyncio
    async def test_check_services_critical_offline(self, service_registry):
        """Test sprawdzania usług - krytyczna usługa offline."""
        # Dodaj usługę krytyczną offline
        offline_service = ServiceInfo(
            name="Critical LLM",
            service_type="api",
            status=ServiceStatus.OFFLINE,
            is_critical=True,
        )
        service_registry.register_service(offline_service)

        assistant = AssistantSkill(service_registry=service_registry)

        with patch.object(assistant.service_monitor, "check_health", new=AsyncMock()):
            result = await assistant.check_services(detailed=False)

            assert "UWAGA" in result
            assert "Krytyczne usługi offline" in result
            assert "Critical LLM" in result

    @pytest.mark.asyncio
    async def test_check_services_empty_registry(self):
        """Test sprawdzania usług - pusty rejestr."""
        empty_registry = MagicMock()
        empty_registry.get_all_services.return_value = []

        assistant = AssistantSkill(service_registry=empty_registry)

        with patch.object(assistant.service_monitor, "check_health", new=AsyncMock()):
            result = await assistant.check_services()

            assert "⚠️" in result
            assert "Brak zarejestrowanych usług" in result

    @pytest.mark.asyncio
    async def test_check_services_with_latency(self, service_registry):
        """Test sprawdzania usług - z informacją o latencji."""
        # Dodaj usługę z latencją
        service_with_latency = ServiceInfo(
            name="Fast Service",
            service_type="api",
            status=ServiceStatus.ONLINE,
            latency_ms=42.5,
        )
        service_registry.register_service(service_with_latency)

        assistant = AssistantSkill(service_registry=service_registry)

        with patch.object(assistant.service_monitor, "check_health", new=AsyncMock()):
            result = await assistant.check_services(detailed=True)

            assert "Fast Service" in result
            assert "42.5" in result or "42.50" in result  # Latencja w ms

    @pytest.mark.asyncio
    async def test_check_services_with_error(self, service_registry):
        """Test sprawdzania usług - z komunikatem błędu."""
        # Dodaj usługę z błędem
        error_service = ServiceInfo(
            name="Error Service",
            service_type="api",
            status=ServiceStatus.OFFLINE,
            error_message="Connection refused",
        )
        service_registry.register_service(error_service)

        assistant = AssistantSkill(service_registry=service_registry)

        with patch.object(assistant.service_monitor, "check_health", new=AsyncMock()):
            result = await assistant.check_services(detailed=True)

            assert "Error Service" in result
            assert "Connection refused" in result

    @pytest.mark.asyncio
    async def test_check_services_exception_handling(self, assistant_skill):
        """Test obsługi wyjątków podczas sprawdzania usług."""
        with patch.object(
            assistant_skill.service_monitor,
            "check_health",
            side_effect=Exception("Test error"),
        ):
            result = await assistant_skill.check_services()

            assert "✗" in result
            assert "Błąd" in result
