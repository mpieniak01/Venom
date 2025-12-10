"""Testy dla HybridModelRouter."""

from venom_core.config import Settings
from venom_core.execution.model_router import AIMode, HybridModelRouter, TaskType


class TestHybridModelRouter:
    """Testy dla klasy HybridModelRouter."""

    def test_initialization(self):
        """Test inicjalizacji routera."""
        router = HybridModelRouter()
        assert router.ai_mode in [AIMode.LOCAL, AIMode.HYBRID, AIMode.CLOUD]

    def test_initialization_with_custom_settings(self):
        """Test inicjalizacji z custom settings."""
        settings = Settings(AI_MODE="HYBRID")
        router = HybridModelRouter(settings=settings)
        assert router.ai_mode == AIMode.HYBRID

    def test_route_sensitive_task_always_local(self):
        """Test routingu dla wrażliwych danych - zawsze LOCAL."""
        router = HybridModelRouter()
        routing = router.route_task(TaskType.SENSITIVE, "password: secret123")

        assert routing["target"] == "local"
        assert routing["provider"] == "local"
        assert (
            "wrażliwe" in routing["reason"].lower()
            or "sensitive" in routing["reason"].lower()
        )

    def test_route_standard_task_in_local_mode(self):
        """Test routingu w trybie LOCAL."""
        settings = Settings(AI_MODE="LOCAL")
        router = HybridModelRouter(settings=settings)
        routing = router.route_task(TaskType.STANDARD, "Hello world")

        assert routing["target"] == "local"
        assert routing["provider"] == "local"

    def test_route_complex_task_in_cloud_mode(self):
        """Test routingu zadań złożonych w trybie CLOUD."""
        settings = Settings(AI_MODE="CLOUD", GOOGLE_API_KEY="test-key")
        router = HybridModelRouter(settings=settings)
        routing = router.route_task(TaskType.CODING_COMPLEX, "Analyze architecture")

        # W trybie CLOUD powinno iść do chmury (jeśli nie wrażliwe)
        assert routing["target"] == "cloud"

    def test_route_standard_task_in_hybrid_mode(self):
        """Test routingu prostych zadań w trybie HYBRID."""
        settings = Settings(AI_MODE="HYBRID")
        router = HybridModelRouter(settings=settings)
        routing = router.route_task(TaskType.STANDARD, "Simple question")

        assert routing["target"] == "local"
        assert routing["provider"] == "local"

    def test_route_complex_task_in_hybrid_mode_with_cloud_access(self):
        """Test routingu złożonych zadań w HYBRID z dostępem do chmury."""
        settings = Settings(
            AI_MODE="HYBRID", GOOGLE_API_KEY="test-key", HYBRID_CLOUD_PROVIDER="google"
        )
        router = HybridModelRouter(settings=settings)
        routing = router.route_task(TaskType.CODING_COMPLEX, "Complex analysis")

        assert routing["target"] == "cloud"
        assert routing["provider"] == "google"

    def test_route_complex_task_in_hybrid_mode_without_cloud_access(self):
        """Test routingu złożonych zadań w HYBRID bez dostępu do chmury (fallback)."""
        settings = Settings(AI_MODE="HYBRID", GOOGLE_API_KEY="")
        router = HybridModelRouter(settings=settings)
        routing = router.route_task(TaskType.CODING_COMPLEX, "Complex analysis")

        # Bez klucza API powinno wrócić do LOCAL
        assert routing["target"] == "local"
        assert "fallback" in routing["reason"].lower()

    def test_sensitive_content_detection(self):
        """Test wykrywania wrażliwych treści."""
        router = HybridModelRouter()

        # Powinno wykryć hasło
        assert router._is_sensitive_content("password: secret123") is True
        assert router._is_sensitive_content("api_key = abc123") is True
        assert router._is_sensitive_content("token: xyz") is True

        # Normalne treści
        assert router._is_sensitive_content("Hello world") is False
        assert router._is_sensitive_content("Write a function") is False

    def test_has_cloud_access_google(self):
        """Test sprawdzania dostępu do Google Cloud."""
        settings = Settings(GOOGLE_API_KEY="test-key", HYBRID_CLOUD_PROVIDER="google")
        router = HybridModelRouter(settings=settings)
        assert router._has_cloud_access() is True

    def test_has_cloud_access_openai(self):
        """Test sprawdzania dostępu do OpenAI."""
        settings = Settings(OPENAI_API_KEY="test-key", HYBRID_CLOUD_PROVIDER="openai")
        router = HybridModelRouter(settings=settings)
        assert router._has_cloud_access() is True

    def test_no_cloud_access(self):
        """Test braku dostępu do chmury."""
        settings = Settings(GOOGLE_API_KEY="", OPENAI_API_KEY="")
        router = HybridModelRouter(settings=settings)
        assert router._has_cloud_access() is False

    def test_chat_task_routing(self):
        """Test routingu dla zadań typu CHAT."""
        settings = Settings(AI_MODE="HYBRID")
        router = HybridModelRouter(settings=settings)
        routing = router.route_task(TaskType.CHAT, "What is Python?")

        assert routing["target"] == "local"

    def test_analysis_task_routing_in_hybrid(self):
        """Test routingu dla zadań analizy w HYBRID."""
        settings = Settings(AI_MODE="HYBRID", GOOGLE_API_KEY="test-key")
        router = HybridModelRouter(settings=settings)
        routing = router.route_task(TaskType.ANALYSIS, "Analyze this data")

        assert routing["target"] == "cloud"

    def test_generation_task_routing_in_hybrid(self):
        """Test routingu dla zadań generowania w HYBRID."""
        settings = Settings(AI_MODE="HYBRID", GOOGLE_API_KEY="test-key")
        router = HybridModelRouter(settings=settings)
        routing = router.route_task(TaskType.GENERATION, "Generate content")

        assert routing["target"] == "cloud"

    def test_sensitive_data_local_only_flag(self):
        """Test flagi wymuszającej wrażliwe dane tylko lokalnie."""
        settings = Settings(AI_MODE="CLOUD", SENSITIVE_DATA_LOCAL_ONLY=True)
        router = HybridModelRouter(settings=settings)

        # Nawet w trybie CLOUD, wrażliwe dane idą lokalnie
        routing = router.route_task(TaskType.SENSITIVE, "password: test")
        assert routing["target"] == "local"

    def test_get_routing_decision(self):
        """Test metody get_routing_decision."""
        router = HybridModelRouter()
        routing_info = router.get_routing_decision("Hello", TaskType.CHAT)

        # Sprawdź że zwraca routing info
        assert "target" in routing_info
        assert "provider" in routing_info
        assert "model_name" in routing_info

    def test_get_routing_info_for_task(self):
        """Test pobrania informacji o routingu."""
        router = HybridModelRouter()
        info = router.get_routing_info_for_task(TaskType.STANDARD, "Test prompt")

        assert "target" in info
        assert "provider" in info
        assert "model_name" in info
        assert "reason" in info

    def test_route_research_task_in_hybrid_mode_with_cloud(self):
        """Test routingu zadania RESEARCH w trybie HYBRID z dostępem do chmury i paid_mode ON."""
        from venom_core.core.state_manager import StateManager

        settings = Settings(
            AI_MODE="HYBRID", GOOGLE_API_KEY="test-key", HYBRID_CLOUD_PROVIDER="google"
        )
        state_manager = StateManager(state_file_path="/tmp/test_state_research.json")
        state_manager.set_paid_mode(True)  # Enable paid mode

        router = HybridModelRouter(settings=settings, state_manager=state_manager)
        routing = router.route_task(TaskType.RESEARCH, "Co to jest Python?")

        # RESEARCH powinno iść do chmury gdy paid_mode=True i jest dostęp
        assert routing["target"] == "cloud"
        assert routing["provider"] == "google"
        assert "RESEARCH" in routing["reason"] or "Grounding" in routing["reason"]

    def test_route_research_task_in_hybrid_mode_without_cloud(self):
        """Test routingu RESEARCH w HYBRID bez dostępu do chmury (fallback)."""
        from venom_core.core.state_manager import StateManager

        settings = Settings(AI_MODE="HYBRID", GOOGLE_API_KEY="")
        state_manager = StateManager(
            state_file_path="/tmp/test_state_research_no_cloud.json"
        )
        state_manager.set_paid_mode(True)  # Even with paid mode, no API key = fallback

        router = HybridModelRouter(settings=settings, state_manager=state_manager)
        routing = router.route_task(TaskType.RESEARCH, "Aktualna cena BTC")

        # Bez klucza API powinno wrócić do LOCAL z DuckDuckGo
        assert routing["target"] == "local"
        assert "RESEARCH" in routing["reason"] or "DuckDuckGo" in routing["reason"]

    def test_route_research_task_paid_mode_off(self):
        """Test routingu RESEARCH gdy paid_mode jest wyłączony."""
        from venom_core.core.state_manager import StateManager

        settings = Settings(
            AI_MODE="HYBRID", GOOGLE_API_KEY="test-key", HYBRID_CLOUD_PROVIDER="google"
        )
        state_manager = StateManager(
            state_file_path="/tmp/test_state_research_off.json"
        )
        state_manager.set_paid_mode(False)  # Disable paid mode

        router = HybridModelRouter(settings=settings, state_manager=state_manager)
        routing = router.route_task(TaskType.RESEARCH, "Aktualna cena BTC")

        # Paid mode OFF -> zawsze LOCAL (DuckDuckGo)
        assert routing["target"] == "local"
        assert "DuckDuckGo" in routing["reason"]

    def test_route_research_task_in_local_mode(self):
        """Test routingu RESEARCH w trybie LOCAL (zawsze DuckDuckGo)."""
        settings = Settings(AI_MODE="LOCAL")
        router = HybridModelRouter(settings=settings)
        routing = router.route_task(TaskType.RESEARCH, "Najnowsze wiadomości")

        assert routing["target"] == "local"
        assert routing["provider"] == "local"
