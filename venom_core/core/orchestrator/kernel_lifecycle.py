"""Moduł: kernel_lifecycle - lifecycle kernel i dispatcherów."""

from __future__ import annotations

from venom_core.core.dispatcher import TaskDispatcher

from .kernel_manager import KernelManager


class KernelLifecycleManager:
    """Warstwa nad KernelManager z jasnym API lifecycle."""

    def __init__(
        self,
        task_dispatcher: TaskDispatcher,
        event_broadcaster=None,
        node_manager=None,
    ):
        self._kernel_manager = KernelManager(
            task_dispatcher=task_dispatcher,
            event_broadcaster=event_broadcaster,
            node_manager=node_manager,
        )

    @property
    def task_dispatcher(self) -> TaskDispatcher:
        return self._kernel_manager.task_dispatcher

    def refresh_kernel(self, runtime_info=None) -> TaskDispatcher:
        return self._kernel_manager.refresh_kernel(runtime_info)

    def refresh_kernel_if_needed(self) -> bool:
        return self._kernel_manager.refresh_kernel_if_needed()
