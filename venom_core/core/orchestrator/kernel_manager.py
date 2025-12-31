"""Zarządzanie kernelem i jego odświeżaniem."""

from typing import TYPE_CHECKING

from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

if TYPE_CHECKING:
    from venom_core.core.dispatcher import TaskDispatcher

logger = get_logger(__name__)


class KernelManager:
    """Zarządza kernelem i jego odświeżaniem przy zmianie konfiguracji LLM."""

    def __init__(
        self,
        task_dispatcher: "TaskDispatcher",
        event_broadcaster=None,
        node_manager=None,
    ):
        """
        Inicjalizacja KernelManager.

        Args:
            task_dispatcher: Dispatcher zadań (będzie aktualizowany przy odświeżeniu)
            event_broadcaster: Opcjonalny broadcaster zdarzeń
            node_manager: Opcjonalny menedżer węzłów
        """
        self.task_dispatcher = task_dispatcher
        self.event_broadcaster = event_broadcaster
        self.node_manager = node_manager
        self._kernel_config_hash = get_active_llm_runtime().config_hash

    def refresh_kernel(self, runtime_info=None) -> "TaskDispatcher":
        """
        Odtwarza kernel i agentów po zmianie konfiguracji LLM.

        Args:
            runtime_info: Informacje o runtime LLM (opcjonalne)

        Returns:
            Nowy TaskDispatcher z odświeżonym kernelem
        """
        from venom_core.core.dispatcher import TaskDispatcher

        runtime_info = runtime_info or get_active_llm_runtime()
        logger.info(
            "Odświeżam kernel po zmianie LLM (hash=%s).",
            runtime_info.config_hash,
        )
        kernel_builder = KernelBuilder()
        kernel = kernel_builder.build_kernel()
        goal_store = getattr(self.task_dispatcher, "goal_store", None)
        new_dispatcher = TaskDispatcher(
            kernel,
            event_broadcaster=self.event_broadcaster,
            node_manager=self.node_manager,
            goal_store=goal_store,
        )
        self._kernel_config_hash = runtime_info.config_hash
        self.task_dispatcher = new_dispatcher
        return new_dispatcher

    def refresh_kernel_if_needed(self) -> bool:
        """
        Sprawdza drift konfiguracji i odświeża kernel przy zmianie.

        Returns:
            True jeśli kernel został odświeżony, False w przeciwnym razie
        """
        runtime_info = get_active_llm_runtime()
        current_hash = runtime_info.config_hash
        if self._kernel_config_hash != current_hash:
            self.refresh_kernel(runtime_info)
            return True
        return False
