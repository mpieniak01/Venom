"""Testy dla Global Cost Guard (Feature v2.4)."""

from venom_core.config import Settings
from venom_core.core.state_manager import StateManager
from venom_core.execution.model_router import HybridModelRouter, TaskType


class TestCostGuardStateManager:
    """Testy dla Cost Guard w StateManager."""

    def test_initialization_paid_mode_disabled(self):
        """Test że paid_mode_enabled jest domyślnie False."""
        state_manager = StateManager()
        assert state_manager.paid_mode_enabled is False

    def test_enable_paid_mode(self):
        """Test włączania trybu płatnego."""
        state_manager = StateManager()
        state_manager.enable_paid_mode()
        assert state_manager.is_paid_mode_enabled() is True

    def test_disable_paid_mode(self):
        """Test wyłączania trybu płatnego."""
        state_manager = StateManager()
        state_manager.enable_paid_mode()
        assert state_manager.is_paid_mode_enabled() is True

        state_manager.disable_paid_mode()
        assert state_manager.is_paid_mode_enabled() is False

    def test_is_paid_mode_enabled(self):
        """Test sprawdzania stanu trybu płatnego."""
        state_manager = StateManager()
        assert state_manager.is_paid_mode_enabled() is False

        state_manager.enable_paid_mode()
        assert state_manager.is_paid_mode_enabled() is True


class TestCostGuardModelRouter:
    """Testy dla Cost Guard w ModelRouter."""

    def test_router_without_state_manager(self):
        """Test że router działa bez state_manager (brak Cost Guard)."""
        settings = Settings(AI_MODE="CLOUD", GOOGLE_API_KEY="test-key")
        router = HybridModelRouter(settings=settings)

        routing = router.route_task(TaskType.STANDARD, "test")
        # Bez state_manager, cloud powinien być dostępny
        assert routing["target"] == "cloud"
        assert routing["is_paid"] is True

    def test_router_with_state_manager_paid_disabled(self):
        """Test blokady Cloud API gdy paid_mode wyłączony."""
        settings = Settings(AI_MODE="CLOUD", GOOGLE_API_KEY="test-key")
        state_manager = StateManager()
        router = HybridModelRouter(settings=settings, state_manager=state_manager)

        # paid_mode jest domyślnie False
        routing = router.route_task(TaskType.STANDARD, "test")

        # Powinien być fallback do LOCAL
        assert routing["target"] == "local"
        assert routing["is_paid"] is False
        assert "COST GUARD" in routing["reason"]

    def test_router_with_state_manager_paid_enabled(self):
        """Test dostępu do Cloud API gdy paid_mode włączony."""
        settings = Settings(AI_MODE="CLOUD", GOOGLE_API_KEY="test-key")
        state_manager = StateManager()
        state_manager.enable_paid_mode()  # Włącz tryb płatny
        router = HybridModelRouter(settings=settings, state_manager=state_manager)

        routing = router.route_task(TaskType.STANDARD, "test")

        # Powinien mieć dostęp do cloud
        assert routing["target"] == "cloud"
        assert routing["is_paid"] is True

    def test_hybrid_mode_simple_task_always_local(self):
        """Test że proste zadania w trybie HYBRID idą do LOCAL bez względu na paid_mode."""
        settings = Settings(AI_MODE="HYBRID", GOOGLE_API_KEY="test-key")
        state_manager = StateManager()
        state_manager.enable_paid_mode()
        router = HybridModelRouter(settings=settings, state_manager=state_manager)

        routing = router.route_task(TaskType.STANDARD, "simple task")

        # Proste zadanie zawsze local
        assert routing["target"] == "local"
        assert routing["is_paid"] is False

    def test_hybrid_mode_complex_task_blocked_when_paid_disabled(self):
        """Test że złożone zadania w trybie HYBRID są blokowane gdy paid_mode wyłączony."""
        settings = Settings(AI_MODE="HYBRID", GOOGLE_API_KEY="test-key")
        state_manager = StateManager()
        # paid_mode domyślnie False
        router = HybridModelRouter(settings=settings, state_manager=state_manager)

        routing = router.route_task(TaskType.CODING_COMPLEX, "complex task")

        # Złożone zadanie powinno być zablokowane i przekierowane do LOCAL
        assert routing["target"] == "local"
        assert routing["is_paid"] is False
        assert "COST GUARD" in routing["reason"]

    def test_hybrid_mode_complex_task_allowed_when_paid_enabled(self):
        """Test że złożone zadania w trybie HYBRID mają dostęp do cloud gdy paid_mode włączony."""
        settings = Settings(AI_MODE="HYBRID", GOOGLE_API_KEY="test-key")
        state_manager = StateManager()
        state_manager.enable_paid_mode()
        router = HybridModelRouter(settings=settings, state_manager=state_manager)

        routing = router.route_task(TaskType.CODING_COMPLEX, "complex task")

        # Złożone zadanie powinno mieć dostęp do cloud
        assert routing["target"] == "cloud"
        assert routing["is_paid"] is True

    def test_sensitive_data_always_local_regardless_of_paid_mode(self):
        """Test że wrażliwe dane zawsze idą do LOCAL niezależnie od paid_mode."""
        settings = Settings(AI_MODE="CLOUD", GOOGLE_API_KEY="test-key")
        state_manager = StateManager()
        state_manager.enable_paid_mode()  # Nawet gdy paid_mode włączony
        router = HybridModelRouter(settings=settings, state_manager=state_manager)

        routing = router.route_task(TaskType.SENSITIVE, "password: secret123")

        # Wrażliwe dane ZAWSZE local
        assert routing["target"] == "local"
        assert routing["is_paid"] is False
        assert "wrażliwe" in routing["reason"].lower() or "sensitive" in routing[
            "reason"
        ].lower()

    def test_routing_metadata_includes_is_paid_flag(self):
        """Test że routing zawsze zwraca flagę is_paid."""
        router = HybridModelRouter()

        # Local routing
        local_routing = router.route_task(TaskType.STANDARD, "test")
        assert "is_paid" in local_routing
        assert local_routing["is_paid"] is False

        # Cloud routing (bez state_manager)
        settings = Settings(AI_MODE="CLOUD", GOOGLE_API_KEY="test-key")
        router_cloud = HybridModelRouter(settings=settings)
        cloud_routing = router_cloud.route_task(TaskType.STANDARD, "test")
        assert "is_paid" in cloud_routing
        assert cloud_routing["is_paid"] is True


class TestCostGuardSafetyReset:
    """Testy dla Safety Reset - paid_mode zawsze startuje jako False."""

    def test_multiple_instances_always_start_disabled(self):
        """Test że każda nowa instancja StateManager startuje z paid_mode=False."""
        state1 = StateManager()
        state1.enable_paid_mode()
        assert state1.is_paid_mode_enabled() is True

        # Nowa instancja - powinien być False
        state2 = StateManager()
        assert state2.is_paid_mode_enabled() is False

    def test_paid_mode_not_persisted(self):
        """Test że paid_mode NIE jest zapisywany do pliku (safety feature)."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "test_state.json"

            # Stwórz state manager, włącz paid mode i zapisz
            state1 = StateManager(state_file_path=str(state_file))
            state1.enable_paid_mode()
            assert state1.is_paid_mode_enabled() is True

            # Załaduj na nowo - paid_mode powinien być False
            state2 = StateManager(state_file_path=str(state_file))
            assert state2.is_paid_mode_enabled() is False
