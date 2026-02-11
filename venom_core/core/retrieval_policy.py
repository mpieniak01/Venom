"""
Retrieval Policy for RAG Boost (Phase B).

This module provides intent-based retrieval policies to improve context quality
for knowledge-intensive intents (RESEARCH, KNOWLEDGE_SEARCH, COMPLEX_PLANNING).
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalPolicy:
    """
    Defines retrieval parameters based on intent.

    Attributes:
        vector_limit: Number of vector search results to retrieve
        max_hops: Maximum hops for graph traversal
        lessons_limit: Maximum lessons to include in context
        preferred_tags: Optional tags for filtering (future use)
        mode: 'baseline' or 'boost' to indicate active policy
    """

    vector_limit: int
    max_hops: int
    lessons_limit: int
    preferred_tags: Optional[list[str]] = None
    mode: str = "baseline"


class RetrievalPolicyManager:
    """
    Manages retrieval policies for different intents.

    This class determines appropriate retrieval parameters based on:
    - Intent type (RESEARCH, KNOWLEDGE_SEARCH, etc.)
    - Feature flag status (ENABLE_RAG_RETRIEVAL_BOOST)
    - Configuration settings from SETTINGS
    """

    # Knowledge-intensive intents that benefit from boosted retrieval
    BOOST_ELIGIBLE_INTENTS = {
        "RESEARCH",
        "KNOWLEDGE_SEARCH",
        "COMPLEX_PLANNING",  # Conservative profile
    }

    def __init__(self):
        """Initialize the policy manager with settings from config."""
        self.enabled = getattr(SETTINGS, "ENABLE_RAG_RETRIEVAL_BOOST", False)
        
        # Default baseline values
        self.default_vector_limit = 5
        self.default_max_hops = 2
        self.default_lessons_limit = 3
        
        # Load boost settings if available
        self._load_boost_settings()

    def _load_boost_settings(self) -> None:
        """Load boost settings from SETTINGS, falling back to defaults."""
        # Note: Configuration uses RAG_BOOST_TOP_K_* naming (common ML/retrieval term)
        # while code uses vector_limit for clarity. Both refer to the same concept:
        # the number of top results to retrieve from vector search.
        
        # Default boost settings
        self.boost_top_k_default = getattr(SETTINGS, "RAG_BOOST_TOP_K_DEFAULT", 5)
        self.boost_top_k_research = getattr(SETTINGS, "RAG_BOOST_TOP_K_RESEARCH", 8)
        self.boost_top_k_knowledge = getattr(SETTINGS, "RAG_BOOST_TOP_K_KNOWLEDGE", 8)
        self.boost_top_k_complex = getattr(SETTINGS, "RAG_BOOST_TOP_K_COMPLEX", 6)
        
        self.boost_max_hops_default = getattr(SETTINGS, "RAG_BOOST_MAX_HOPS_DEFAULT", 2)
        self.boost_max_hops_research = getattr(SETTINGS, "RAG_BOOST_MAX_HOPS_RESEARCH", 3)
        self.boost_max_hops_knowledge = getattr(SETTINGS, "RAG_BOOST_MAX_HOPS_KNOWLEDGE", 3)
        
        self.boost_lessons_limit_default = getattr(SETTINGS, "RAG_BOOST_LESSONS_LIMIT_DEFAULT", 3)
        self.boost_lessons_limit_research = getattr(SETTINGS, "RAG_BOOST_LESSONS_LIMIT_RESEARCH", 5)
        self.boost_lessons_limit_knowledge = getattr(SETTINGS, "RAG_BOOST_LESSONS_LIMIT_KNOWLEDGE", 5)

    def get_policy(
        self,
        intent: str,
        intent_source: Optional[str] = None,
        forced_intent: Optional[str] = None,
    ) -> RetrievalPolicy:
        """
        Get retrieval policy for the given intent.

        Args:
            intent: The classified intent
            intent_source: (Reserved for Phase C) Source of intent classification
            forced_intent: (Reserved for Phase C) Whether intent was forced by user

        Returns:
            RetrievalPolicy with appropriate parameters
            
        Note:
            Currently only `intent` is used to determine the policy.
            `intent_source` and `forced_intent` are reserved for future
            enhancements in Phase C (e.g., adjusting confidence based on source).
        """
        # If boost disabled, always return baseline
        if not self.enabled:
            return self._get_baseline_policy()

        # Check if intent is eligible for boost
        if intent not in self.BOOST_ELIGIBLE_INTENTS:
            return self._get_baseline_policy()

        # Get boosted policy based on intent
        try:
            policy = self._get_boost_policy(intent)
            logger.debug(
                f"RAG Boost active for intent={intent}, "
                f"vector_limit={policy.vector_limit}, "
                f"max_hops={policy.max_hops}, "
                f"lessons_limit={policy.lessons_limit}"
            )
            return policy
        except Exception as e:
            logger.warning(f"Error getting boost policy for {intent}: {e}, falling back to baseline")
            return self._get_baseline_policy()

    def _get_baseline_policy(self) -> RetrievalPolicy:
        """Return baseline (default) retrieval policy."""
        return RetrievalPolicy(
            vector_limit=self.default_vector_limit,
            max_hops=self.default_max_hops,
            lessons_limit=self.default_lessons_limit,
            mode="baseline",
        )

    def _get_boost_policy(self, intent: str) -> RetrievalPolicy:
        """
        Return boosted retrieval policy for the given intent.

        Args:
            intent: The classified intent

        Returns:
            RetrievalPolicy with boosted parameters
        """
        if intent == "RESEARCH":
            return RetrievalPolicy(
                vector_limit=self.boost_top_k_research,
                max_hops=self.boost_max_hops_research,
                lessons_limit=self.boost_lessons_limit_research,
                mode="boost",
            )
        elif intent == "KNOWLEDGE_SEARCH":
            return RetrievalPolicy(
                vector_limit=self.boost_top_k_knowledge,
                max_hops=self.boost_max_hops_knowledge,
                lessons_limit=self.boost_lessons_limit_knowledge,
                mode="boost",
            )
        elif intent == "COMPLEX_PLANNING":
            # Conservative profile for COMPLEX_PLANNING
            return RetrievalPolicy(
                vector_limit=self.boost_top_k_complex,
                max_hops=self.default_max_hops,  # Keep default hops for safety
                lessons_limit=self.default_lessons_limit,  # Keep default lessons
                mode="boost",
            )
        else:
            # Fallback to default boost settings
            return RetrievalPolicy(
                vector_limit=self.boost_top_k_default,
                max_hops=self.boost_max_hops_default,
                lessons_limit=self.boost_lessons_limit_default,
                mode="boost",
            )


def get_policy_manager() -> RetrievalPolicyManager:
    """
    Get or create the singleton policy manager instance.
    
    Uses functools.lru_cache for thread-safe singleton initialization.
    """
    return _get_policy_manager_impl()


@lru_cache(maxsize=1)
def _get_policy_manager_impl() -> RetrievalPolicyManager:
    """Thread-safe singleton implementation using lru_cache."""
    return RetrievalPolicyManager()
