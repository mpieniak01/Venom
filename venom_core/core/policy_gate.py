"""Moduł: policy_gate - globalny gate polityk bezpieczeństwa i etyki."""

import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class PolicyDecision(str, Enum):
    """Decyzja policy gate."""

    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"


class PolicyReasonCode(str, Enum):
    """Kody przyczyn blokady policy."""

    POLICY_UNSAFE_CONTENT = "POLICY_UNSAFE_CONTENT"
    POLICY_TOOL_RESTRICTED = "POLICY_TOOL_RESTRICTED"
    POLICY_PROVIDER_RESTRICTED = "POLICY_PROVIDER_RESTRICTED"
    POLICY_MISSING_CONTEXT = "POLICY_MISSING_CONTEXT"


class PolicyEvaluationContext(BaseModel):
    """Kontekst dla ewaluacji policy."""

    content: str
    intent: Optional[str] = None
    planned_provider: Optional[str] = None
    planned_tools: list[str] = Field(default_factory=list)
    session_id: Optional[str] = None
    forced_tool: Optional[str] = None
    forced_provider: Optional[str] = None


class PolicyEvaluationResult(BaseModel):
    """Wynik ewaluacji policy."""

    decision: PolicyDecision
    reason_code: Optional[PolicyReasonCode] = None
    message: str = ""
    technical_details: Optional[str] = None


class PolicyGate:
    """
    Globalny gate polityk bezpieczeństwa i etyki.

    Singleton zarządzający weryfikacją zgodności żądań z politykami systemu.
    """

    _instance: Optional["PolicyGate"] = None
    _initialized: bool = False

    def __new__(cls):
        """Implementacja singletonu."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Inicjalizacja PolicyGate (wykonywana raz dla singletonu)."""
        if self._initialized:
            return

        # Załaduj konfigurację z environment
        self._enabled = os.getenv("ENABLE_POLICY_GATE", "false").lower() == "true"

        self._initialized = True
        status = "enabled" if self._enabled else "disabled"
        logger.info(f"PolicyGate zainicjalizowany - status: {status}")

    @property
    def enabled(self) -> bool:
        """Zwraca czy gate jest włączony."""
        return self._enabled

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyEvaluationResult:
        """
        Ewaluuje kontekst żądania względem polityk systemu.

        Args:
            context: Kontekst żądania do weryfikacji

        Returns:
            PolicyEvaluationResult z decyzją i opcjonalnym kodem przyczyny
        """
        # Jeśli gate wyłączony, zawsze pozwól
        if not self._enabled:
            logger.debug("PolicyGate bypass - feature disabled")
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                message="Policy gate disabled",
            )

        logger.info(
            f"PolicyGate evaluating request - intent: {context.intent}, "
            f"provider: {context.planned_provider}, tools: {context.planned_tools}"
        )

        # MVP: podstawowa implementacja - w przyszłości rozbudować o reguły
        # Na razie zawsze pozwalamy, ale logujemy
        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            message="Request allowed by policy gate",
        )

    def evaluate_before_provider_selection(
        self, context: PolicyEvaluationContext
    ) -> PolicyEvaluationResult:
        """
        Ewaluuje żądanie przed wyborem providera.

        Args:
            context: Kontekst żądania

        Returns:
            PolicyEvaluationResult z decyzją
        """
        logger.debug("PolicyGate: evaluating before provider selection")
        return self.evaluate(context)

    def evaluate_before_tool_execution(
        self, context: PolicyEvaluationContext
    ) -> PolicyEvaluationResult:
        """
        Ewaluuje żądanie przed wykonaniem narzędzi.

        Args:
            context: Kontekst żądania

        Returns:
            PolicyEvaluationResult z decyzją
        """
        logger.debug("PolicyGate: evaluating before tool execution")
        return self.evaluate(context)


# Globalna instancja (singleton)
policy_gate = PolicyGate()
