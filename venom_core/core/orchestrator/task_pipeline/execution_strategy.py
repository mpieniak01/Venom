from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from venom_core.core.flows.campaign import CampaignFlow
from venom_core.core.models import TaskRequest
from venom_core.utils.logger import get_logger

if TYPE_CHECKING:
    from venom_core.core.orchestrator.orchestrator_core import Orchestrator

logger = get_logger(__name__)


class ExecutionStrategy:
    """Handles task execution logic based on intent."""

    def __init__(self, orch: "Orchestrator"):
        self.orch = orch

    async def execute(
        self, task_id: UUID, intent: str, context: str, request: TaskRequest
    ) -> Any:
        # Perf test check should be handled before strategy or inside?
        # In dispatch it is checked early. I will assume it is handled by the caller or passed here.

        if intent == "START_CAMPAIGN":
            return await self._execute_campaign(task_id)

        elif intent == "HELP_REQUEST":
            return await self._execute_help(task_id)

        elif self.orch._should_use_council(request.content, intent):
            return await self._execute_council(task_id, context, intent)

        elif intent == "CODE_GENERATION":
            return await self._execute_code_generation(task_id, context, intent)

        elif intent == "COMPLEX_PLANNING":
            return await self._execute_complex_planning(
                task_id, context, intent, request
            )

        else:
            return await self._execute_default(task_id, context, intent, request)

    async def _execute_campaign(self, task_id: UUID) -> Any:
        self.orch.state_manager.add_log(
            task_id, "🚀 Uruchamiam Tryb Kampanii (Campaign Mode)"
        )
        if self.orch.request_tracer:
            self.orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "route_campaign",
                status="ok",
                details="🚀 Routing to Campaign Mode",
            )
        if self.orch._campaign_flow is None:
            self.orch._campaign_flow = CampaignFlow(
                state_manager=self.orch.state_manager,
                orchestrator_submit_task=self.orch.submit_task,
                event_broadcaster=self.orch.event_broadcaster,
            )
        campaign_result = await self.orch._campaign_flow.execute(
            goal_store=self.orch.task_dispatcher.goal_store
        )
        return campaign_result.get("summary", str(campaign_result))

    async def _execute_help(self, task_id: UUID) -> Any:
        self.orch.state_manager.add_log(task_id, "❓ Generuję informacje pomocy")
        if self.orch.request_tracer:
            self.orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "route_help",
                status="ok",
                details="❓ Routing to Help System",
            )
        return await self.orch._generate_help_response(task_id)

    async def _execute_council(self, task_id: UUID, context: str, intent: str) -> Any:
        self.orch.state_manager.add_log(
            task_id,
            "🏛️ Zadanie wymaga współpracy - aktywuję The Council",
        )
        if self.orch.request_tracer:
            self.orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "select_council_mode",
                status="ok",
                details=f"🏛️ Complex task detected (intent={intent}) -> Council Mode",
            )
        self.orch._trace_llm_start(task_id, intent)
        return await self.orch.run_council(task_id, context)

    async def _execute_code_generation(
        self, task_id: UUID, context: str, intent: str
    ) -> Any:
        if self.orch.request_tracer:
            self.orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "select_code_review_loop",
                status="ok",
                details="💻 Routing to Coder-Critic Review Loop",
            )
        self.orch._trace_llm_start(task_id, intent)
        return await self.orch._code_generation_with_review(task_id, context)

    async def _execute_complex_planning(
        self, task_id: UUID, context: str, intent: str, request: TaskRequest
    ) -> Any:
        self.orch.state_manager.add_log(
            task_id,
            "Zadanie sklasyfikowane jako COMPLEX_PLANNING - delegacja do Architekta",
        )
        if self.orch.request_tracer:
            self.orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "route_to_architect",
                status="ok",
                details="🏗️ Routing to Architect for Complex Planning",
            )
        await self.orch._broadcast_event(
            event_type="AGENT_ACTION",
            message="Przekazuję zadanie do Architekta (Complex Planning)",
            agent="Architect",
            data={"task_id": str(task_id)},
        )
        self.orch._trace_llm_start(task_id, intent)
        if request.generation_params:
            return await self.orch.task_dispatcher.dispatch(
                intent,
                context,
                generation_params=request.generation_params,
            )
        else:
            return await self.orch.task_dispatcher.dispatch(intent, context)

    async def _execute_default(
        self, task_id: UUID, context: str, intent: str, request: TaskRequest
    ) -> Any:
        if self.orch.request_tracer:
            agent = self.orch.task_dispatcher.agent_map.get(intent)
            agent_name = agent.__class__.__name__ if agent else "UnknownAgent"
            self.orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "route_to_agent",
                status="ok",
                details=f"📤 Routing to {agent_name} (intent={intent})",
            )
        self.orch._trace_llm_start(task_id, intent)

        if request.generation_params:
            return await self.orch.task_dispatcher.dispatch(
                intent,
                context,
                generation_params=request.generation_params,
            )
        else:
            return await self.orch.task_dispatcher.dispatch(intent, context)
