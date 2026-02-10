"""Testy dla EnergyManager."""

import asyncio
import time

import pytest

from venom_core.core.energy_manager import EnergyManager, SystemMetrics


class TestSystemMetrics:
    """Testy dla SystemMetrics."""

    def test_system_metrics_creation(self):
        """Test tworzenia metryki systemowej."""
        metrics = SystemMetrics(cpu_percent=50.0, memory_percent=70.0)

        assert metrics.cpu_percent == pytest.approx(50.0)
        assert metrics.memory_percent == pytest.approx(70.0)
        assert metrics.temperature is None
        assert metrics.timestamp > 0

    def test_system_metrics_with_temperature(self):
        """Test metryki z temperaturą."""
        metrics = SystemMetrics(cpu_percent=60.0, memory_percent=80.0, temperature=45.5)

        assert metrics.temperature == pytest.approx(45.5)


class TestEnergyManager:
    """Testy dla EnergyManager."""

    def test_initialization(self):
        """Test inicjalizacji EnergyManager."""
        em = EnergyManager(cpu_threshold=0.7, memory_threshold=0.8)

        assert em.cpu_threshold == pytest.approx(0.7)
        assert em.memory_threshold == pytest.approx(0.8)
        assert not em.is_monitoring
        assert len(em._alert_callbacks) == 0
        assert em.sensors_active  # Nowa flaga dla sensorów

    def test_get_metrics(self):
        """Test pobierania metryki systemu."""
        em = EnergyManager()
        metrics = em.get_metrics()

        assert isinstance(metrics, SystemMetrics)
        assert 0 <= metrics.cpu_percent <= 100
        assert 0 <= metrics.memory_percent <= 100

    def test_sensor_failure_handling(self):
        """Test obsługi awarii sensora temperatury."""
        em = EnergyManager()
        # Wywołaj get_metrics - sensor może być niedostępny w środowisku testowym
        metrics = em.get_metrics()
        assert isinstance(metrics, SystemMetrics)

        # Sprawdź że flaga sensors_active istnieje
        assert hasattr(em, "sensors_active")
        assert isinstance(em.sensors_active, bool)

        # Jeśli sensor rzucił wyjątek (exception), flaga powinna być False
        # W przeciwnym razie pozostaje True
        # (test weryfikuje jedynie, że mechanizm flagowania działa)

    def test_is_system_busy_below_threshold(self):
        """Test sprawdzania czy system zajęty - poniżej progu."""
        # Ustaw bardzo wysokie progi (100%), system nie będzie zajęty
        em = EnergyManager(cpu_threshold=1.0, memory_threshold=1.0)

        assert not em.is_system_busy()

    def test_is_system_busy_above_threshold(self):
        """Test sprawdzania czy system zajęty - powyżej progu."""
        # Ustaw bardzo niskie progi (0%), system zawsze będzie zajęty
        em = EnergyManager(cpu_threshold=0.0, memory_threshold=0.0)

        assert em.is_system_busy()

    def test_idle_time_tracking(self):
        """Test śledzenia czasu bezczynności."""
        em = EnergyManager()

        # Początkowy czas bezczynności (bardzo mały)
        idle_time_1 = em.get_idle_time()
        assert idle_time_1 >= 0

        # Poczekaj trochę
        time.sleep(0.1)

        # Idle time powinien wzrosnąć
        idle_time_2 = em.get_idle_time()
        assert idle_time_2 > idle_time_1

        # Oznacz aktywność
        em.mark_activity()

        # Idle time powinien się zresetować
        idle_time_3 = em.get_idle_time()
        assert idle_time_3 < idle_time_2

    def test_is_idle_threshold(self):
        """Test sprawdzania bezczynności z progiem."""
        em = EnergyManager()

        # System nie powinien być bezczynny (świeżo utworzony)
        assert not em.is_idle(threshold_minutes=1)

        # Symuluj długi czas bezczynności
        em.last_activity_time = time.time() - 120  # 2 minuty temu

        # Teraz powinien być bezczynny dla progu 1 minuta
        assert em.is_idle(threshold_minutes=1)

    def test_register_alert_callback(self):
        """Test rejestracji callbacka alarmowego."""
        em = EnergyManager()

        def dummy_callback():
            """No-op callback używany wyłącznie do testu rejestracji."""
            return None

        em.register_alert_callback(dummy_callback)

        assert len(em._alert_callbacks) == 1
        assert dummy_callback in em._alert_callbacks

    def test_wake_up(self):
        """Test funkcji wake_up."""
        em = EnergyManager()

        em.wake_up()

        # Idle time powinien być bardzo mały (aktywność została oznaczona)
        assert em.get_idle_time() < 1.0

    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self):
        """Test uruchamiania i zatrzymywania monitorowania."""
        em = EnergyManager(check_interval=1)

        assert not em.is_monitoring

        # Uruchom monitoring
        em.start_monitoring()
        assert em.is_monitoring
        assert em._monitor_task is not None

        # Poczekaj chwilę
        await asyncio.sleep(0.5)

        # Zatrzymaj monitoring
        await em.stop_monitoring()
        assert not em.is_monitoring

    @pytest.mark.asyncio
    async def test_monitoring_with_callback(self):
        """Test monitorowania z callbackiem."""
        callback_called = []

        async def alert_callback():
            callback_called.append(True)
            await asyncio.sleep(0)

        # Ustaw bardzo niskie progi żeby wywołać callback
        em = EnergyManager(cpu_threshold=0.0, memory_threshold=0.0, check_interval=1)
        em.register_alert_callback(alert_callback)

        # Uruchom monitoring
        em.start_monitoring()

        # Poczekaj na wykonanie callbacka
        await asyncio.sleep(2)

        # Zatrzymaj
        await em.stop_monitoring()

        # Callback powinien zostać wywołany (system jest "zajęty" z progami 0%)
        assert len(callback_called) > 0

    @pytest.mark.asyncio
    async def test_run_alert_callbacks_handles_sync_async_and_errors(self):
        em = EnergyManager()
        called = {"sync": 0, "async": 0}

        def sync_cb():
            called["sync"] += 1

        async def async_cb():
            called["async"] += 1

        def failing_cb():
            raise RuntimeError("boom")

        em.register_alert_callback(sync_cb)
        em.register_alert_callback(async_cb)
        em.register_alert_callback(failing_cb)

        await em._run_alert_callbacks()

        assert called["sync"] == 1
        assert called["async"] == 1

    def test_get_status(self):
        """Test pobierania statusu EnergyManager."""
        em = EnergyManager(cpu_threshold=0.7, memory_threshold=0.8)

        status = em.get_status()

        assert "is_monitoring" in status
        assert "cpu_percent" in status
        assert "memory_percent" in status
        assert "cpu_threshold" in status
        assert "memory_threshold" in status
        assert "is_busy" in status
        assert "idle_time_seconds" in status
        assert "is_idle" in status
        assert "registered_callbacks" in status

        assert status["cpu_threshold"] == pytest.approx(70.0)  # 0.7 * 100
        assert status["memory_threshold"] == pytest.approx(80.0)  # 0.8 * 100
        assert status["registered_callbacks"] == 0
