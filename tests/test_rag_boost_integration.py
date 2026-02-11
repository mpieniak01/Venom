"""Integration tests for Phase B: RAG Retrieval Boost end-to-end flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from venom_core.core.retrieval_policy import RetrievalPolicyManager


class TestRAGBoostIntegration:
    """End-to-end integration tests for RAG Retrieval Boost."""

    @pytest.fixture
    def mock_settings_enabled(self):
        """Mock SETTINGS with RAG boost enabled."""
        settings = MagicMock()
        settings.ENABLE_RAG_RETRIEVAL_BOOST = True
        settings.ENABLE_META_LEARNING = True
        settings.RAG_BOOST_TOP_K_RESEARCH = 8
        settings.RAG_BOOST_MAX_HOPS_RESEARCH = 3
        settings.RAG_BOOST_LESSONS_LIMIT_RESEARCH = 5
        settings.RAG_BOOST_TOP_K_DEFAULT = 5
        settings.RAG_BOOST_MAX_HOPS_DEFAULT = 2
        settings.RAG_BOOST_LESSONS_LIMIT_DEFAULT = 3
        settings.RAG_BOOST_TOP_K_KNOWLEDGE = 8
        settings.RAG_BOOST_MAX_HOPS_KNOWLEDGE = 3
        settings.RAG_BOOST_LESSONS_LIMIT_KNOWLEDGE = 5
        settings.RAG_BOOST_TOP_K_COMPLEX = 6
        return settings

    @pytest.fixture
    def mock_settings_disabled(self):
        """Mock SETTINGS with RAG boost disabled."""
        settings = MagicMock()
        settings.ENABLE_RAG_RETRIEVAL_BOOST = False
        settings.ENABLE_META_LEARNING = True
        return settings

    def test_policy_independence_from_phase_a(self, mock_settings_enabled):
        """Test that Phase B works independently of Phase A settings."""
        with patch("venom_core.core.retrieval_policy.SETTINGS", mock_settings_enabled):
            # Phase B should work regardless of Phase A settings
            mock_settings_enabled.ENABLE_INTENT_EMBEDDING_ROUTER = False
            
            manager = RetrievalPolicyManager()
            assert manager.enabled is True
            
            policy = manager.get_policy("RESEARCH")
            assert policy.mode == "boost"
            assert policy.lessons_limit == 5

    def test_boost_disabled_returns_baseline_for_all_intents(self, mock_settings_disabled):
        """Test that all intents get baseline when boost is disabled."""
        with patch("venom_core.core.retrieval_policy.SETTINGS", mock_settings_disabled):
            manager = RetrievalPolicyManager()
            assert manager.enabled is False
            
            # All intents should get baseline
            for intent in ["RESEARCH", "KNOWLEDGE_SEARCH", "COMPLEX_PLANNING", "GENERAL_CHAT"]:
                policy = manager.get_policy(intent)
                assert policy.mode == "baseline"
                assert policy.vector_limit == 5
                assert policy.max_hops == 2
                assert policy.lessons_limit == 3

    def test_boost_only_for_eligible_intents(self, mock_settings_enabled):
        """Test that boost is only applied to eligible intents."""
        with patch("venom_core.core.retrieval_policy.SETTINGS", mock_settings_enabled):
            manager = RetrievalPolicyManager()
            
            # Eligible intents should get boost
            eligible = ["RESEARCH", "KNOWLEDGE_SEARCH", "COMPLEX_PLANNING"]
            for intent in eligible:
                policy = manager.get_policy(intent)
                assert policy.mode == "boost"
            
            # Non-eligible intents should get baseline
            non_eligible = ["GENERAL_CHAT", "TIME_REQUEST", "INFRA_STATUS", "HELP"]
            for intent in non_eligible:
                policy = manager.get_policy(intent)
                assert policy.mode == "baseline"

    def test_different_profiles_per_intent(self, mock_settings_enabled):
        """Test that different intents get different boost profiles."""
        with patch("venom_core.core.retrieval_policy.SETTINGS", mock_settings_enabled):
            manager = RetrievalPolicyManager()
            
            research_policy = manager.get_policy("RESEARCH")
            knowledge_policy = manager.get_policy("KNOWLEDGE_SEARCH")
            complex_policy = manager.get_policy("COMPLEX_PLANNING")
            
            # RESEARCH and KNOWLEDGE_SEARCH should have same aggressive profile
            assert research_policy.vector_limit == knowledge_policy.vector_limit == 8
            assert research_policy.max_hops == knowledge_policy.max_hops == 3
            assert research_policy.lessons_limit == knowledge_policy.lessons_limit == 5
            
            # COMPLEX_PLANNING should have conservative profile
            assert complex_policy.vector_limit == 6
            assert complex_policy.max_hops == 2  # Default, conservative
            assert complex_policy.lessons_limit == 3  # Default, conservative

    @pytest.mark.asyncio
    async def test_context_builder_integration_with_policy(self, mock_settings_enabled):
        """Test that context_builder correctly applies retrieval policy."""
        from types import SimpleNamespace
        
        # Reset singleton cache to ensure fresh instance with mocked settings
        from venom_core.core import retrieval_policy as rp_module
        if hasattr(rp_module._get_policy_manager_impl, 'cache_clear'):
            rp_module._get_policy_manager_impl.cache_clear()
        
        # Mock orchestrator and its components
        mock_orch = MagicMock()
        mock_orch.state_manager = MagicMock()
        mock_orch.state_manager.add_log = MagicMock()
        mock_orch.state_manager.update_context = MagicMock()
        mock_orch.request_tracer = MagicMock()
        mock_orch.request_tracer.add_step = MagicMock()
        
        # Mock lessons_manager
        mock_lessons_manager = MagicMock()
        mock_lessons_manager.add_lessons_to_context = AsyncMock(
            return_value="enriched context"
        )
        mock_orch.lessons_manager = mock_lessons_manager
        
        # Create context builder
        from venom_core.core.orchestrator.task_pipeline.context_builder import ContextBuilder
        
        # Need to patch SETTINGS in both modules
        with patch("venom_core.core.retrieval_policy.SETTINGS", mock_settings_enabled), \
             patch("venom_core.core.orchestrator.task_pipeline.context_builder.SETTINGS", mock_settings_enabled):
            builder = ContextBuilder(mock_orch)
            task_id = uuid4()
            
            # Test with RESEARCH intent (should apply boost)
            await builder.enrich_context_with_lessons(
                task_id, "test context", intent="RESEARCH"
            )
            
            # Verify lessons_manager was called with boost limit
            mock_lessons_manager.add_lessons_to_context.assert_called_once()
            call_args = mock_lessons_manager.add_lessons_to_context.call_args
            assert call_args[0][0] == task_id  # task_id
            assert call_args[0][1] == "test context"  # context
            assert call_args[1]["limit"] == 5  # boost limit for RESEARCH
            
            # Verify telemetry was recorded
            assert mock_orch.state_manager.update_context.called
            update_args = mock_orch.state_manager.update_context.call_args[0][1]
            assert "retrieval_boost.enabled" in update_args
            assert update_args["retrieval_boost.mode"] == "boost"
            assert update_args["retrieval_boost.intent"] == "RESEARCH"

    @pytest.mark.asyncio
    async def test_context_builder_no_boost_for_general_chat(self, mock_settings_enabled):
        """Test that GENERAL_CHAT doesn't get boost even when enabled."""
        from types import SimpleNamespace
        
        # Reset singleton cache to ensure fresh instance with mocked settings
        from venom_core.core import retrieval_policy as rp_module
        if hasattr(rp_module._get_policy_manager_impl, 'cache_clear'):
            rp_module._get_policy_manager_impl.cache_clear()
        
        mock_orch = MagicMock()
        mock_orch.state_manager = MagicMock()
        mock_orch.state_manager.add_log = MagicMock()
        mock_orch.state_manager.update_context = MagicMock()
        mock_orch.request_tracer = None
        
        mock_lessons_manager = MagicMock()
        mock_lessons_manager.add_lessons_to_context = AsyncMock(
            return_value="enriched context"
        )
        mock_orch.lessons_manager = mock_lessons_manager
        
        from venom_core.core.orchestrator.task_pipeline.context_builder import ContextBuilder
        
        with patch("venom_core.core.retrieval_policy.SETTINGS", mock_settings_enabled):
            builder = ContextBuilder(mock_orch)
            task_id = uuid4()
            
            # Test with GENERAL_CHAT intent (should NOT apply boost)
            await builder.enrich_context_with_lessons(
                task_id, "test context", intent="GENERAL_CHAT"
            )
            
            # Verify lessons_manager was called with baseline limit
            call_args = mock_lessons_manager.add_lessons_to_context.call_args
            # Baseline limit is 3
            assert call_args[1]["limit"] == 3

    @pytest.mark.asyncio
    async def test_graceful_fallback_on_policy_error(self):
        """Test that errors in policy don't break the request."""
        mock_orch = MagicMock()
        mock_orch.state_manager = MagicMock()
        mock_orch.state_manager.add_log = MagicMock()
        mock_orch.state_manager.update_context = MagicMock()
        mock_orch.request_tracer = None
        
        mock_lessons_manager = MagicMock()
        mock_lessons_manager.add_lessons_to_context = AsyncMock(
            return_value="enriched context"
        )
        mock_orch.lessons_manager = mock_lessons_manager
        
        from venom_core.core.orchestrator.task_pipeline.context_builder import ContextBuilder
        
        builder = ContextBuilder(mock_orch)
        task_id = uuid4()
        
        # Force an error in policy manager
        with patch(
            "venom_core.core.retrieval_policy.get_policy_manager",
            side_effect=Exception("Test error")
        ):
            # Should not raise, should fall back gracefully
            await builder.enrich_context_with_lessons(
                task_id, "test context", intent="RESEARCH"
            )
            
            # Should still call lessons_manager (with limit=None, which uses default)
            assert mock_lessons_manager.add_lessons_to_context.called
            call_args = mock_lessons_manager.add_lessons_to_context.call_args
            # When error occurs, limit should be None (falls back to default)
            assert call_args[1]["limit"] is None
