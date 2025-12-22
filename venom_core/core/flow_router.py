"""Moduł: flow_router - decyzje o routingu zadań do odpowiednich flow."""

from typing import Tuple

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class FlowRouter:
    """Router decydujący o wyborze odpowiedniego flow dla zadania."""

    def __init__(self, council_flow=None):
        """
        Inicjalizacja FlowRouter.

        Args:
            council_flow: Opcjonalna instancja CouncilFlow (lazy initialized)
        """
        self._council_flow = council_flow

    def should_use_council(self, context: str, intent: str) -> bool:
        """
        Decyduje czy zadanie powinno być przekierowane do Council mode.

        Deleguje decyzję do CouncilFlow jeśli jest dostępny.

        Args:
            context: Treść zadania
            intent: Sklasyfikowana intencja

        Returns:
            True jeśli należy użyć Council mode
        """
        if self._council_flow is None:
            # Brak council_flow - nie używaj council mode
            return False

        # Deleguj decyzję do CouncilFlow
        return self._council_flow.should_use_council(context, intent)

    def set_council_flow(self, council_flow) -> None:
        """
        Ustawia instancję CouncilFlow.

        Args:
            council_flow: Instancja CouncilFlow do użycia w routingu
        """
        self._council_flow = council_flow

    def determine_flow(
        self, context: str, intent: str
    ) -> Tuple[str, dict]:
        """
        Określa jaki flow powinien obsłużyć zadanie.

        Args:
            context: Treść zadania
            intent: Sklasyfikowana intencja

        Returns:
            Tuple (flow_name, flow_metadata) gdzie:
            - flow_name: nazwa flow (council/code_review/standard/help/campaign)
            - flow_metadata: dodatkowe metadane dla flow
        """
        # Specjalne przypadki
        if intent == "START_CAMPAIGN":
            return ("campaign", {"mode": "campaign"})

        if intent == "HELP_REQUEST":
            return ("help", {"mode": "help"})

        # Council mode
        if self.should_use_council(context, intent):
            return (
                "council",
                {
                    "mode": "council",
                    "reason": "collaboration_or_complex",
                },
            )

        # Code generation z review loop
        if intent == "CODE_GENERATION":
            return ("code_review", {"mode": "coder_critic"})

        # Complex planning -> Architect
        if intent == "COMPLEX_PLANNING":
            return ("standard", {"mode": "architect", "agent": "architect"})

        # Domyślny flow - standard dispatcher
        return ("standard", {"mode": "standard", "intent": intent})
