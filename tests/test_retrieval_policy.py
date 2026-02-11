"""Tests for RAG Retrieval Boost policy (Phase B)."""

import pytest
from unittest.mock import MagicMock, patch

from venom_core.core.retrieval_policy import (
    RetrievalPolicy,
    RetrievalPolicyManager,
    get_policy_manager,
)


class TestRetrievalPolicy:
    """Test RetrievalPolicy dataclass."""

    def test_baseline_policy_creation(self):
        """Test creating a baseline policy."""
        policy = RetrievalPolicy(
            vector_limit=5,
            max_hops=2,
            lessons_limit=3,
            mode="baseline",
        )
        assert policy.vector_limit == 5
        assert policy.max_hops == 2
        assert policy.lessons_limit == 3
        assert policy.mode == "baseline"
        assert policy.preferred_tags is None

    def test_boost_policy_creation(self):
        """Test creating a boost policy with tags."""
        policy = RetrievalPolicy(
            vector_limit=8,
            max_hops=3,
            lessons_limit=5,
            preferred_tags=["research", "technical"],
            mode="boost",
        )
        assert policy.vector_limit == 8
        assert policy.max_hops == 3
        assert policy.lessons_limit == 5
        assert policy.mode == "boost"
        assert policy.preferred_tags == ["research", "technical"]


class TestRetrievalPolicyManager:
    """Test RetrievalPolicyManager logic."""

    @pytest.fixture
    def mock_settings(self):
        """Mock SETTINGS for testing."""
        settings = MagicMock()
        settings.ENABLE_RAG_RETRIEVAL_BOOST = False
        settings.RAG_BOOST_TOP_K_DEFAULT = 5
        settings.RAG_BOOST_TOP_K_RESEARCH = 8
        settings.RAG_BOOST_TOP_K_KNOWLEDGE = 8
        settings.RAG_BOOST_TOP_K_COMPLEX = 6
        settings.RAG_BOOST_MAX_HOPS_DEFAULT = 2
        settings.RAG_BOOST_MAX_HOPS_RESEARCH = 3
        settings.RAG_BOOST_MAX_HOPS_KNOWLEDGE = 3
        settings.RAG_BOOST_LESSONS_LIMIT_DEFAULT = 3
        settings.RAG_BOOST_LESSONS_LIMIT_RESEARCH = 5
        settings.RAG_BOOST_LESSONS_LIMIT_KNOWLEDGE = 5
        return settings

    @pytest.fixture
    def manager_disabled(self, mock_settings):
        """Create manager with boost disabled."""
        with patch("venom_core.core.retrieval_policy.SETTINGS", mock_settings):
            return RetrievalPolicyManager()

    @pytest.fixture
    def manager_enabled(self, mock_settings):
        """Create manager with boost enabled."""
        mock_settings.ENABLE_RAG_RETRIEVAL_BOOST = True
        with patch("venom_core.core.retrieval_policy.SETTINGS", mock_settings):
            return RetrievalPolicyManager()

    def test_manager_initialization_disabled(self, manager_disabled):
        """Test manager initializes correctly when disabled."""
        assert manager_disabled.enabled is False
        assert manager_disabled.default_vector_limit == 5
        assert manager_disabled.default_max_hops == 2
        assert manager_disabled.default_lessons_limit == 3

    def test_manager_initialization_enabled(self, manager_enabled):
        """Test manager initializes correctly when enabled."""
        assert manager_enabled.enabled is True
        assert manager_enabled.boost_top_k_research == 8
        assert manager_enabled.boost_max_hops_research == 3
        assert manager_enabled.boost_lessons_limit_research == 5

    def test_get_baseline_when_disabled(self, manager_disabled):
        """Test that baseline is returned when boost is disabled."""
        policy = manager_disabled.get_policy("RESEARCH")
        assert policy.mode == "baseline"
        assert policy.vector_limit == 5
        assert policy.max_hops == 2
        assert policy.lessons_limit == 3

    def test_get_baseline_for_non_eligible_intent(self, manager_enabled):
        """Test baseline for intents not eligible for boost."""
        policy = manager_enabled.get_policy("GENERAL_CHAT")
        assert policy.mode == "baseline"
        assert policy.vector_limit == 5
        assert policy.max_hops == 2
        assert policy.lessons_limit == 3

    def test_get_boost_for_research(self, manager_enabled):
        """Test boost policy for RESEARCH intent."""
        policy = manager_enabled.get_policy("RESEARCH")
        assert policy.mode == "boost"
        assert policy.vector_limit == 8
        assert policy.max_hops == 3
        assert policy.lessons_limit == 5

    def test_get_boost_for_knowledge_search(self, manager_enabled):
        """Test boost policy for KNOWLEDGE_SEARCH intent."""
        policy = manager_enabled.get_policy("KNOWLEDGE_SEARCH")
        assert policy.mode == "boost"
        assert policy.vector_limit == 8
        assert policy.max_hops == 3
        assert policy.lessons_limit == 5

    def test_get_boost_for_complex_planning(self, manager_enabled):
        """Test conservative boost for COMPLEX_PLANNING."""
        policy = manager_enabled.get_policy("COMPLEX_PLANNING")
        assert policy.mode == "boost"
        assert policy.vector_limit == 6
        assert policy.max_hops == 2  # Conservative: uses default
        assert policy.lessons_limit == 3  # Conservative: uses default

    def test_fallback_on_error(self, manager_enabled):
        """Test fallback to baseline on error."""
        # Force an error by passing invalid intent type
        with patch.object(
            manager_enabled, "_get_boost_policy", side_effect=Exception("Test error")
        ):
            policy = manager_enabled.get_policy("RESEARCH")
            assert policy.mode == "baseline"

    def test_get_policy_with_intent_source(self, manager_enabled):
        """Test policy retrieval with intent_source parameter."""
        policy = manager_enabled.get_policy("RESEARCH", intent_source="embedding")
        assert policy.mode == "boost"
        assert policy.vector_limit == 8

    def test_get_policy_with_forced_intent(self, manager_enabled):
        """Test policy retrieval with forced_intent parameter."""
        policy = manager_enabled.get_policy(
            "RESEARCH", forced_intent="KNOWLEDGE_SEARCH"
        )
        # Should still use the provided intent (RESEARCH), not forced_intent
        assert policy.mode == "boost"
        assert policy.vector_limit == 8


class TestGetPolicyManager:
    """Test singleton policy manager."""

    def test_singleton_pattern(self):
        """Test that get_policy_manager returns singleton."""
        # Clear cache to ensure fresh test
        from venom_core.core import retrieval_policy as module
        if hasattr(module._get_policy_manager_impl, 'cache_clear'):
            module._get_policy_manager_impl.cache_clear()

        manager1 = get_policy_manager()
        manager2 = get_policy_manager()
        assert manager1 is manager2

    def test_manager_configuration_persistence(self):
        """Test that manager configuration persists across calls."""
        from venom_core.core import retrieval_policy as module
        if hasattr(module._get_policy_manager_impl, 'cache_clear'):
            module._get_policy_manager_impl.cache_clear()

        manager = get_policy_manager()
        initial_enabled = manager.enabled

        # Get manager again
        manager2 = get_policy_manager()
        assert manager2.enabled == initial_enabled


class TestRetrievalPolicyIntegration:
    """Integration tests for retrieval policy."""

    @pytest.fixture
    def mock_settings_boost_enabled(self):
        """Mock settings with boost enabled."""
        settings = MagicMock()
        settings.ENABLE_RAG_RETRIEVAL_BOOST = True
        settings.RAG_BOOST_TOP_K_DEFAULT = 5
        settings.RAG_BOOST_TOP_K_RESEARCH = 8
        settings.RAG_BOOST_TOP_K_KNOWLEDGE = 8
        settings.RAG_BOOST_TOP_K_COMPLEX = 6
        settings.RAG_BOOST_MAX_HOPS_DEFAULT = 2
        settings.RAG_BOOST_MAX_HOPS_RESEARCH = 3
        settings.RAG_BOOST_MAX_HOPS_KNOWLEDGE = 3
        settings.RAG_BOOST_LESSONS_LIMIT_DEFAULT = 3
        settings.RAG_BOOST_LESSONS_LIMIT_RESEARCH = 5
        settings.RAG_BOOST_LESSONS_LIMIT_KNOWLEDGE = 5
        return settings

    def test_intent_to_policy_mapping(self, mock_settings_boost_enabled):
        """Test complete intent to policy mapping."""
        with patch(
            "venom_core.core.retrieval_policy.SETTINGS", mock_settings_boost_enabled
        ):
            manager = RetrievalPolicyManager()

            # Test all boost-eligible intents
            research_policy = manager.get_policy("RESEARCH")
            assert research_policy.vector_limit == 8
            assert research_policy.lessons_limit == 5

            knowledge_policy = manager.get_policy("KNOWLEDGE_SEARCH")
            assert knowledge_policy.vector_limit == 8
            assert knowledge_policy.lessons_limit == 5

            complex_policy = manager.get_policy("COMPLEX_PLANNING")
            assert complex_policy.vector_limit == 6
            assert complex_policy.lessons_limit == 3

            # Test non-eligible intent
            general_policy = manager.get_policy("GENERAL_CHAT")
            assert general_policy.mode == "baseline"
            assert general_policy.vector_limit == 5

    def test_boost_toggle_behavior(self):
        """Test that boost can be toggled on/off."""
        settings_disabled = MagicMock()
        settings_disabled.ENABLE_RAG_RETRIEVAL_BOOST = False

        settings_enabled = MagicMock()
        settings_enabled.ENABLE_RAG_RETRIEVAL_BOOST = True
        settings_enabled.RAG_BOOST_TOP_K_RESEARCH = 8
        settings_enabled.RAG_BOOST_MAX_HOPS_RESEARCH = 3
        settings_enabled.RAG_BOOST_LESSONS_LIMIT_RESEARCH = 5

        # Test disabled
        with patch("venom_core.core.retrieval_policy.SETTINGS", settings_disabled):
            manager_off = RetrievalPolicyManager()
            policy_off = manager_off.get_policy("RESEARCH")
            assert policy_off.mode == "baseline"

        # Test enabled
        with patch("venom_core.core.retrieval_policy.SETTINGS", settings_enabled):
            manager_on = RetrievalPolicyManager()
            policy_on = manager_on.get_policy("RESEARCH")
            assert policy_on.mode == "boost"
