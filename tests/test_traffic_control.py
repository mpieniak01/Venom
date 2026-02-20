"""Testy dla modułu traffic_control - globalna kontrola ruchu API."""

import time
from logging.handlers import TimedRotatingFileHandler
from unittest.mock import MagicMock, patch

import pytest

from venom_core.infrastructure.traffic_control import (
    CircuitBreaker,
    CircuitState,
    RetryPolicy,
    RetryResult,
    TokenBucket,
    TrafficControlConfig,
    TrafficController,
)
from venom_core.infrastructure.traffic_control.retry_policy import (
    is_retriable_http_error,
)


class TestTokenBucket:
    """Testy dla TokenBucket rate limitera."""

    def test_token_bucket_initialization(self):
        """Test inicjalizacji bucketa z pełną pojemnością."""
        bucket = TokenBucket(capacity=100, refill_rate=10.0)
        assert bucket.capacity == 100
        assert bucket.refill_rate == 10.0
        assert bucket.tokens == 100.0

    def test_token_bucket_acquire_success(self):
        """Test pobrania tokenów gdy są dostępne."""
        bucket = TokenBucket(capacity=100, refill_rate=10.0)
        assert bucket.acquire(10) is True
        assert bucket.tokens == 90.0

    def test_token_bucket_acquire_failure(self):
        """Test pobrania tokenów gdy nie ma wystarczająco."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        bucket.tokens = 5.0
        assert bucket.acquire(10) is False
        # Tokeny mogą się lekko zwiększyć przez czas w _refill() (microseconds)
        assert bucket.tokens >= 5.0 and bucket.tokens < 5.1

    def test_token_bucket_try_acquire_with_wait(self):
        """Test try_acquire z sugerowanym czasem oczekiwania."""
        bucket = TokenBucket(capacity=100, refill_rate=10.0)
        bucket.tokens = 5.0
        success, wait_seconds = bucket.try_acquire(10)
        assert success is False
        assert wait_seconds is not None
        assert wait_seconds > 0  # Potrzeba czasu na refill

    def test_token_bucket_refill(self):
        """Test uzupełniania tokenów w czasie."""
        bucket = TokenBucket(capacity=100, refill_rate=10.0)
        bucket.tokens = 50.0
        time.sleep(0.5)  # 0.5s * 10 tokens/s = 5 tokens
        bucket._refill()
        assert bucket.tokens >= 54.0  # ~55 tokens (margin for timing)

    def test_token_bucket_refill_cap(self):
        """Test że refill nie przekracza capacity."""
        bucket = TokenBucket(capacity=100, refill_rate=100.0)
        bucket.tokens = 90.0
        time.sleep(1.0)  # 1s * 100 tokens/s = 100 tokens, ale cap=100
        bucket._refill()
        assert bucket.tokens == 100.0

    def test_token_bucket_available_tokens(self):
        """Test zwracania dostępnych tokenów."""
        bucket = TokenBucket(capacity=100, refill_rate=10.0)
        bucket.tokens = 50.0
        assert bucket.available_tokens() >= 50.0

    def test_token_bucket_reset(self):
        """Test resetowania bucketa."""
        bucket = TokenBucket(capacity=100, refill_rate=10.0)
        bucket.acquire(50)
        bucket.reset()
        assert bucket.tokens == 100.0


class TestCircuitBreaker:
    """Testy dla Circuit Breaker pattern."""

    def test_circuit_breaker_initialization(self):
        """Test inicjalizacji w stanie CLOSED."""
        breaker = CircuitBreaker(failure_threshold=5)
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_circuit_breaker_closed_allows_requests(self):
        """Test że CLOSED przepuszcza requesty."""
        breaker = CircuitBreaker()
        assert breaker.is_request_allowed() is True

    def test_circuit_breaker_open_after_failures(self):
        """Test przejścia do OPEN po przekroczeniu failure_threshold."""
        breaker = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_request_allowed() is False

    def test_circuit_breaker_half_open_after_timeout(self):
        """Test przejścia do HALF_OPEN po timeout."""
        breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=0.1)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        time.sleep(0.2)
        assert breaker.is_request_allowed() is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_circuit_breaker_recovery_to_closed(self):
        """Test powrotu do CLOSED po udanych requestach w HALF_OPEN."""
        breaker = CircuitBreaker(
            failure_threshold=2, success_threshold=2, timeout_seconds=0.1
        )
        breaker.record_failure()
        breaker.record_failure()
        time.sleep(0.2)
        breaker.is_request_allowed()  # Przejście do HALF_OPEN
        breaker.record_success()
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_circuit_breaker_failure_in_half_open(self):
        """Test że failure w HALF_OPEN wraca do OPEN."""
        breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=0.1)
        breaker.record_failure()
        breaker.record_failure()
        time.sleep(0.2)
        breaker.is_request_allowed()  # HALF_OPEN
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_circuit_breaker_reset(self):
        """Test resetowania circuit breakera."""
        breaker = CircuitBreaker(failure_threshold=2)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_circuit_breaker_get_stats(self):
        """Test zwracania statystyk."""
        breaker = CircuitBreaker(failure_threshold=3)
        breaker.record_failure()
        stats = breaker.get_stats()
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 1


class TestRetryPolicy:
    """Testy dla RetryPolicy z exponential backoff."""

    def test_retry_policy_calculate_delay(self):
        """Test obliczania opóźnienia dla próby."""
        policy = RetryPolicy(
            initial_delay_seconds=1.0, exponential_base=2.0, jitter_factor=0.0
        )
        # attempt=0: 1.0 * 2^0 = 1.0
        assert policy.calculate_delay(0) == 1.0
        # attempt=1: 1.0 * 2^1 = 2.0
        assert policy.calculate_delay(1) == 2.0
        # attempt=2: 1.0 * 2^2 = 4.0
        assert policy.calculate_delay(2) == 4.0

    def test_retry_policy_max_delay_cap(self):
        """Test że delay nie przekracza max_delay."""
        policy = RetryPolicy(
            initial_delay_seconds=1.0,
            max_delay_seconds=5.0,
            exponential_base=2.0,
            jitter_factor=0.0,
        )
        # attempt=10: 1.0 * 2^10 = 1024.0, ale cap=5.0
        assert policy.calculate_delay(10) == 5.0

    def test_retry_policy_jitter(self):
        """Test że jitter dodaje losowość."""
        policy = RetryPolicy(
            initial_delay_seconds=1.0, exponential_base=2.0, jitter_factor=0.1
        )
        delays = [policy.calculate_delay(0) for _ in range(10)]
        # Powinny być różne (z prawdopodobieństwem >99%)
        assert len(set(delays)) > 1

    def test_retry_policy_execute_success(self):
        """Test udanego wywołania bez retry."""

        def successful_func():
            return "success"

        policy = RetryPolicy()
        result, value, error = policy.execute_with_retry(successful_func)
        assert result == RetryResult.SUCCESS
        assert value == "success"
        assert error is None

    def test_retry_policy_execute_with_retries(self):
        """Test wywołania z retry po niepowodzeniach."""
        attempts = [0]

        def failing_then_success():
            attempts[0] += 1
            if attempts[0] < 3:
                raise ValueError("Temporary error")
            return "success"

        policy = RetryPolicy(max_attempts=3, initial_delay_seconds=0.01)
        result, value, error = policy.execute_with_retry(failing_then_success)
        assert result == RetryResult.SUCCESS
        assert value == "success"
        assert attempts[0] == 3

    def test_retry_policy_execute_exhausted(self):
        """Test wyczerpania prób retry."""

        def always_failing():
            raise ValueError("Persistent error")

        policy = RetryPolicy(max_attempts=3, initial_delay_seconds=0.01)
        result, value, error = policy.execute_with_retry(always_failing)
        assert result == RetryResult.FAILED
        assert value is None
        assert error is not None

    def test_retry_policy_non_retriable_error(self):
        """Test że non-retriable error nie jest retry."""

        def auth_error():
            raise PermissionError("Unauthorized")

        def is_retriable(e):
            return not isinstance(e, PermissionError)

        policy = RetryPolicy(max_attempts=3)
        result, value, error = policy.execute_with_retry(
            auth_error, is_retriable=is_retriable
        )
        assert result == RetryResult.FAILED
        assert isinstance(error, PermissionError)

    def test_is_retriable_http_error_timeout(self):
        """Test że timeout jest retriable."""

        class TimeoutError(Exception):
            pass

        error = TimeoutError("Request timeout")
        assert is_retriable_http_error(error) is True

    def test_is_retriable_http_error_429(self):
        """Test że 429 jest retriable."""

        class HTTPError(Exception):
            def __init__(self, status_code):
                self.response = MagicMock()
                self.response.status_code = status_code

        error = HTTPError(429)
        assert is_retriable_http_error(error) is True

    def test_is_retriable_http_error_5xx(self):
        """Test że 5xx jest retriable."""

        class HTTPError(Exception):
            def __init__(self, status_code):
                self.response = MagicMock()
                self.response.status_code = status_code

        error = HTTPError(503)
        assert is_retriable_http_error(error) is True

    def test_is_retriable_http_error_401(self):
        """Test że 401 nie jest retriable."""

        class HTTPError(Exception):
            def __init__(self, status_code):
                self.response = MagicMock()
                self.response.status_code = status_code

        error = HTTPError(401)
        assert is_retriable_http_error(error) is False


class TestTrafficController:
    """Testy dla TrafficController orchestratora."""

    def test_traffic_controller_initialization(self):
        """Test inicjalizacji z domyślną konfiguracją."""
        controller = TrafficController()
        assert controller.config is not None
        assert len(controller._outbound_policies) == 0

    def test_traffic_controller_check_outbound_allowed(self):
        """Test że outbound request jest przepuszczany."""
        controller = TrafficController()
        allowed, reason, wait = controller.check_outbound_request("test_provider")
        assert allowed is True
        assert reason is None

    def test_traffic_controller_check_outbound_rate_limit(self):
        """Test że rate limit blokuje requesty."""
        config = TrafficControlConfig()
        config.global_outbound.rate_limit.capacity = 2
        controller = TrafficController(config)

        # Pierwsze 2 requesty OK
        assert controller.check_outbound_request("test", 1)[0] is True
        assert controller.check_outbound_request("test", 1)[0] is True

        # Trzeci request zablokowany
        allowed, reason, wait = controller.check_outbound_request("test", 1)
        assert allowed is False
        assert reason == "rate_limit_exceeded"
        assert wait is not None

    def test_resolve_safe_log_dir_world_writable_uses_scoped_subdir(self, tmp_path):
        """Publicznie zapisywalny katalog bazowy powinien mieć izolowany podkatalog."""
        public_dir = tmp_path / "public-logs"
        public_dir.mkdir(parents=True, exist_ok=True)
        public_dir.chmod(0o777)

        with (
            patch.dict("os.environ", {"TRAFFIC_CONTROL_LOG_DIR": str(public_dir)}),
            patch("os.getuid", return_value=4242),
        ):
            resolved = TrafficController._resolve_safe_log_dir()

        assert resolved == (public_dir / "user-4242").resolve()
        assert resolved.exists()
        assert resolved.is_dir()

    def test_setup_rotating_logging_uses_resolved_safe_dir(self, tmp_path):
        """Setup logowania powinien tworzyć handler w bezpiecznie resolved katalogu."""
        public_dir = tmp_path / "public-logs"
        public_dir.mkdir(parents=True, exist_ok=True)
        public_dir.chmod(0o777)

        tc_logger = __import__("logging").getLogger("venom_core.traffic_control")
        old_handlers = list(tc_logger.handlers)
        try:
            config = TrafficControlConfig.from_env()
            config.enable_logging = True
            config.log_rotation_hours = 24
            config.log_retention_days = 3
            with (
                patch.dict("os.environ", {"TRAFFIC_CONTROL_LOG_DIR": str(public_dir)}),
                patch("os.getuid", return_value=31337),
            ):
                controller = TrafficController(config)
                assert controller is not None

            expected_prefix = str((public_dir / "user-31337").resolve())
            tc_handlers = [
                h for h in tc_logger.handlers if isinstance(h, TimedRotatingFileHandler)
            ]
            assert any(
                getattr(h, "baseFilename", "").startswith(expected_prefix)
                for h in tc_handlers
            )
        finally:
            for handler in list(tc_logger.handlers):
                if handler not in old_handlers:
                    tc_logger.removeHandler(handler)
                    try:
                        handler.close()
                    except Exception:
                        pass

    def test_resolve_safe_log_dir_stat_error_fallbacks_to_base(self, tmp_path):
        base = tmp_path / "broken-stat"
        with (
            patch.dict("os.environ", {"TRAFFIC_CONTROL_LOG_DIR": str(base)}),
            patch("pathlib.Path.stat", side_effect=OSError("stat-failed")),
        ):
            resolved = TrafficController._resolve_safe_log_dir()
        assert resolved == base.resolve()

    def test_resolve_safe_log_dir_without_getuid_uses_user_local(
        self, tmp_path, monkeypatch
    ):
        public_dir = tmp_path / "public-logs-nouid"
        public_dir.mkdir(parents=True, exist_ok=True)
        public_dir.chmod(0o777)
        monkeypatch.delattr("os.getuid", raising=False)

        with patch.dict("os.environ", {"TRAFFIC_CONTROL_LOG_DIR": str(public_dir)}):
            resolved = TrafficController._resolve_safe_log_dir()

        assert resolved == (public_dir / "user-local").resolve()

    def test_resolve_safe_log_dir_ignores_chmod_errors(self, tmp_path):
        private_dir = tmp_path / "private-logs"
        private_dir.mkdir(parents=True, exist_ok=True)
        private_dir.chmod(0o755)
        with (
            patch.dict("os.environ", {"TRAFFIC_CONTROL_LOG_DIR": str(private_dir)}),
            patch("os.chmod", side_effect=OSError("chmod-failed")),
        ):
            resolved = TrafficController._resolve_safe_log_dir()

        assert resolved == private_dir.resolve()

    def test_traffic_controller_circuit_breaker_open(self):
        """Test że circuit breaker blokuje requesty po failures."""
        config = TrafficControlConfig()
        config.global_outbound.circuit_breaker.failure_threshold = 2
        controller = TrafficController(config)

        # Record failures
        controller.check_outbound_request("test")
        controller.record_outbound_response("test", 500)
        controller.check_outbound_request("test")
        controller.record_outbound_response("test", 500)

        # Circuit powinien być otwarty
        allowed, reason, _ = controller.check_outbound_request("test")
        assert allowed is False
        assert reason == "circuit_breaker_open"

    def test_traffic_controller_check_inbound_allowed(self):
        """Test że inbound request jest przepuszczany."""
        controller = TrafficController()
        allowed, reason, wait = controller.check_inbound_request("chat")
        assert allowed is True
        assert reason is None

    def test_traffic_controller_check_inbound_rate_limit(self):
        """Test że inbound rate limit działa."""
        config = TrafficControlConfig()
        config.global_inbound.rate_limit.capacity = 2
        controller = TrafficController(config)

        # Pierwsze 2 requesty OK
        assert controller.check_inbound_request("chat", 1)[0] is True
        assert controller.check_inbound_request("chat", 1)[0] is True

        # Trzeci request zablokowany
        allowed, reason, wait = controller.check_inbound_request("chat", 1)
        assert allowed is False
        assert reason == "rate_limit_exceeded"

    def test_traffic_controller_record_response_2xx(self):
        """Test rejestrowania udanej odpowiedzi."""
        controller = TrafficController()
        controller.check_outbound_request("test")
        controller.record_outbound_response("test", 200)

        metrics = controller.get_metrics("test")
        assert metrics["metrics"]["total_2xx"] == 1

    def test_traffic_controller_record_response_429(self):
        """Test rejestrowania rate limit response."""
        controller = TrafficController()
        controller.check_outbound_request("test")
        controller.record_outbound_response("test", 429)

        metrics = controller.get_metrics("test")
        assert metrics["metrics"]["total_429"] == 1
        assert metrics["metrics"]["total_4xx"] == 1

    def test_traffic_controller_record_response_5xx(self):
        """Test rejestrowania błędu serwera."""
        controller = TrafficController()
        controller.check_outbound_request("test")
        controller.record_outbound_response("test", 503)

        metrics = controller.get_metrics("test")
        assert metrics["metrics"]["total_5xx"] == 1

    def test_traffic_controller_get_global_metrics(self):
        """Test pobierania globalnych metryk."""
        controller = TrafficController()
        controller.check_outbound_request("test1")
        controller.check_inbound_request("chat")

        metrics = controller.get_metrics()
        assert "global" in metrics
        assert "outbound_scopes" in metrics
        assert "inbound_scopes" in metrics

    def test_traffic_controller_provider_specific_limits(self):
        """Test że provider-specific limity są stosowane."""
        config = TrafficControlConfig.from_env()
        controller = TrafficController(config)

        # Musimy najpierw wykonać request, żeby polityka została utworzona
        controller.check_outbound_request("github")
        controller.check_outbound_request("openai")

        # GitHub powinien mieć niższe limity (60/min)
        metrics = controller.get_metrics("github")
        assert metrics["rate_limit"]["capacity"] == 60

        # OpenAI powinien mieć wyższe limity (500/min)
        metrics = controller.get_metrics("openai")
        assert metrics["rate_limit"]["capacity"] == 500


@pytest.mark.parametrize(
    "provider,expected_capacity",
    [
        ("github", 60),
        ("reddit", 60),
        ("openai", 500),
        ("unknown_provider", 100),  # Default
    ],
)
def test_traffic_controller_provider_configs(provider, expected_capacity):
    """Test konfiguracji per-provider."""
    config = TrafficControlConfig.from_env()
    controller = TrafficController(config)
    controller.check_outbound_request(provider)  # Create policy
    metrics = controller.get_metrics(provider)
    assert metrics["rate_limit"]["capacity"] == expected_capacity


class TestAntiLoopProtection:
    """Testy dla anti-loop protection helper methods."""

    def test_is_under_global_request_cap_below_threshold(self):
        """Test że requests poniżej globalnego limitu zwracają True."""
        config = TrafficControlConfig()
        config.max_requests_per_minute_global = 1000

        assert config.is_under_global_request_cap(500) is True
        assert config.is_under_global_request_cap(999) is True

    def test_is_under_global_request_cap_at_threshold(self):
        """Test że requests równe limitowi zwracają False."""
        config = TrafficControlConfig()
        config.max_requests_per_minute_global = 1000

        assert config.is_under_global_request_cap(1000) is False

    def test_is_under_global_request_cap_above_threshold(self):
        """Test że requests powyżej limitu zwracają False."""
        config = TrafficControlConfig()
        config.max_requests_per_minute_global = 1000

        assert config.is_under_global_request_cap(1001) is False
        assert config.is_under_global_request_cap(2000) is False

    def test_can_retry_operation_below_max(self):
        """Test że retry_count poniżej max_retries zwraca True."""
        config = TrafficControlConfig()
        config.max_retries_per_operation = 5

        assert config.can_retry_operation(0) is True
        assert config.can_retry_operation(4) is True

    def test_can_retry_operation_at_max(self):
        """Test że retry_count równy max_retries zwraca False."""
        config = TrafficControlConfig()
        config.max_retries_per_operation = 5

        assert config.can_retry_operation(5) is False

    def test_can_retry_operation_above_max(self):
        """Test że retry_count powyżej max_retries zwraca False."""
        config = TrafficControlConfig()
        config.max_retries_per_operation = 5

        assert config.can_retry_operation(6) is False
        assert config.can_retry_operation(10) is False

    def test_should_enter_degraded_state_disabled(self):
        """Test że degraded mode wyłączony zawsze zwraca False."""
        config = TrafficControlConfig()
        config.degraded_mode_enabled = False
        config.max_requests_per_minute_global = 1000
        config.degraded_mode_failure_threshold = 10

        # Nawet przy przekroczeniu limitów
        assert config.should_enter_degraded_state(2000, 20) is False

    def test_should_enter_degraded_state_request_cap_exceeded(self):
        """Test przejścia w degraded gdy przekroczony globalny limit requestów."""
        config = TrafficControlConfig()
        config.degraded_mode_enabled = True
        config.max_requests_per_minute_global = 1000
        config.degraded_mode_failure_threshold = 10

        # Przekroczenie requestów
        assert config.should_enter_degraded_state(1000, 0) is True
        assert config.should_enter_degraded_state(1500, 5) is True

    def test_should_enter_degraded_state_failure_threshold_exceeded(self):
        """Test przejścia w degraded gdy przekroczony próg błędów."""
        config = TrafficControlConfig()
        config.degraded_mode_enabled = True
        config.max_requests_per_minute_global = 1000
        config.degraded_mode_failure_threshold = 10

        # Przekroczenie błędów
        assert config.should_enter_degraded_state(500, 10) is True
        assert config.should_enter_degraded_state(100, 15) is True

    def test_should_enter_degraded_state_below_all_thresholds(self):
        """Test że degraded mode nie włącza się gdy wszystko w normie."""
        config = TrafficControlConfig()
        config.degraded_mode_enabled = True
        config.max_requests_per_minute_global = 1000
        config.degraded_mode_failure_threshold = 10

        assert config.should_enter_degraded_state(500, 5) is False
        assert config.should_enter_degraded_state(999, 9) is False

    def test_should_enter_degraded_state_boundary_conditions(self):
        """Test warunków brzegowych dla degraded mode."""
        config = TrafficControlConfig()
        config.degraded_mode_enabled = True
        config.max_requests_per_minute_global = 1000
        config.degraded_mode_failure_threshold = 10

        # Dokładnie na granicy requestów (should trigger)
        assert config.should_enter_degraded_state(1000, 0) is True

        # Dokładnie na granicy błędów (should trigger)
        assert config.should_enter_degraded_state(0, 10) is True

        # Jeden poniżej granic (should not trigger)
        assert config.should_enter_degraded_state(999, 9) is False
