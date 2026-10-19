"""Native MAF workflow participants backed by existing Venom agents."""

from __future__ import annotations

from typing import Any, Literal

from agent_framework import Executor, Message, WorkflowContext, handler
from agent_framework_orchestrations import (
    GroupChatParticipantMessage,
    GroupChatRequestMessage,
    GroupChatResponseMessage,
)
from pydantic import BaseModel, ConfigDict

from venom_core.agents.base import BaseAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class _CriticReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["APPROVED", "REVISE", "REPLAN"]
    feedback: str


class _GuardianReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["APPROVED", "REVISE"]
    feedback: str


class VenomAgent(Executor):
    """Reuse Venom process/policies inside MAF; never construct a second model."""

    def __init__(
        self,
        name: str,
        venom_agent: BaseAgent,
        system_message: str,
        llm_config: dict | None = None,
        deliberation: bool = False,
        **kwargs,
    ):
        super().__init__(id=name)
        self.name = name
        self.venom_agent = venom_agent
        self.system_message = system_message
        self.llm_config = llm_config or {}
        self.deliberation = deliberation
        self.generation_params: dict[str, Any] = {}
        self.conversation: list[Message] = []
        self.output_messages: list[Message] = []

    def _turn_messages(self) -> list[Message]:
        """Keep an auditable full transcript, but give each role its actual inputs."""
        role_inputs = {
            "Architect": {"User", "Critic"},
            "Coder": {"User", "Architect", "Coder", "Critic", "Guardian"},
            "Critic": {"User", "Coder"},
            "Guardian": {"User", "Coder", "Critic"},
        }
        if not self.deliberation or self.name not in role_inputs:
            return self.conversation
        latest = {
            message.author_name: index
            for index, message in enumerate(self.conversation)
            if message.author_name in role_inputs[self.name]
        }
        return [self.conversation[index] for index in sorted(latest.values())]

    @handler
    async def receive_messages(
        self,
        message: GroupChatParticipantMessage,
        ctx: WorkflowContext[GroupChatResponseMessage],
    ) -> None:
        self.conversation.extend(message.messages)

    def _build_turn_transcript(self, request: GroupChatRequestMessage) -> str:
        transcript = "\n\n".join(
            f"[{message.author_name or message.role}]: {message.text}"
            for message in self._turn_messages()
        )
        if request.additional_instruction:
            transcript += "\n\n" + request.additional_instruction
        if self.deliberation:
            transcript += f"\n\nTeraz wyłącznie tura {self.name}. Wykonaj swoją rolę względem zadania [User]."
        return transcript

    def _deliberation_candidate(self, transcript: str) -> str:
        if self.name != "Critic":
            return transcript
        candidates = [
            message for message in self.conversation if message.author_name == "Coder"
        ]
        if not candidates:
            raise ValueError("council_critic_missing_coder_candidate")
        return candidates[-1].text

    def _format_deliberation_review(
        self,
        result: str,
        review_type: type[_CriticReview] | type[_GuardianReview] | None,
    ) -> str:
        if review_type is None:
            return result
        review = review_type.model_validate_json(result)
        if self.name == "Guardian":
            final_line = "TERMINATE" if review.decision == "APPROVED" else "REVISE"
            return f"{review.feedback}\n{final_line}"
        return f"{review.decision}\n{review.feedback}"

    async def _deliberate_turn(self, transcript: str) -> str:
        candidate = self._deliberation_candidate(transcript)
        blocked, policy_report = self.venom_agent.validate_deliberation_input(candidate)
        logger.info(f"Council turn started: {self.name}; policy_blocked={blocked}")
        if blocked:
            result = policy_report
        else:
            review_types: dict[str, type[_CriticReview] | type[_GuardianReview]] = {
                "Critic": _CriticReview,
                "Guardian": _GuardianReview,
            }
            review_type = review_types.get(self.name)
            response_format = None
            if review_type is not None:
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": f"council_{self.name.lower()}_review",
                        "strict": True,
                        "schema": review_type.model_json_schema(),
                    },
                }
            result = await self.venom_agent.deliberate(
                transcript,
                system_message=self.system_message,
                generation_params=self.generation_params,
                enable_functions=self.name in {"Coder", "Guardian"},
                response_format=response_format,
            )
            result = self._format_deliberation_review(result, review_type)
            if policy_report:
                result = f"{policy_report}\n\nDODATKOWE UWAGI LLM:\n{result}"
        logger.info(f"Council turn finished: {self.name}")
        return result

    @handler
    async def respond(
        self,
        request: GroupChatRequestMessage,
        ctx: WorkflowContext[GroupChatResponseMessage],
    ) -> None:
        transcript = self._build_turn_transcript(request)
        # Errors and cancellation propagate; failed participants never become success.
        if self.deliberation:
            result = await self._deliberate_turn(transcript)
        else:
            result = await self.venom_agent.process(transcript)
        response = Message("assistant", [result], author_name=self.name)
        # GroupChat excludes the author from broadcasts: record its own turn once.
        self.conversation.append(response)
        self.output_messages.append(response)
        await ctx.send_message(GroupChatResponseMessage(response))

    async def a_process_venom(self, message: str) -> str:
        """Existing direct wrapper entry point, outside a group workflow."""
        try:
            return await self.venom_agent.process(message)
        except Exception as exc:
            return f"Błąd podczas przetwarzania przez {self.name}: {exc}"


def create_venom_agent_wrapper(
    agent: BaseAgent,
    name: str,
    system_message: str | None = None,
    llm_config: dict | None = None,
    deliberation: bool = False,
) -> VenomAgent:
    return VenomAgent(
        name,
        agent,
        system_message
        or str(getattr(agent, "SYSTEM_PROMPT", None) or f"Jesteś agentem {name}"),
        llm_config,
        deliberation=deliberation,
    )


def extract_venom_tools(agent: BaseAgent) -> list[dict[str, Any]]:
    """Export actual native schemas; permission enforcement remains in runtime."""
    runtime = getattr(agent, "kernel", None)
    if runtime is None:
        return []
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters(),
            },
        }
        for tool in runtime.native_tools()
    ]
