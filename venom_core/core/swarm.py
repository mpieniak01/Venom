"""Native MAF workflow participants backed by existing Venom agents."""

from __future__ import annotations

from typing import Any

from agent_framework import Executor, Message, WorkflowContext, handler
from agent_framework_orchestrations import (
    GroupChatParticipantMessage,
    GroupChatRequestMessage,
    GroupChatResponseMessage,
)

from venom_core.agents.base import BaseAgent


class VenomAgent(Executor):
    """Reuse Venom process/policies inside MAF; never construct a second model."""

    def __init__(
        self,
        name: str,
        venom_agent: BaseAgent,
        system_message: str,
        llm_config: dict | None = None,
        **kwargs,
    ):
        super().__init__(id=name)
        self.name = name
        self.venom_agent = venom_agent
        self.system_message = system_message
        self.llm_config = llm_config or {}
        self.conversation: list[Message] = []
        self.output_messages: list[Message] = []

    @handler
    async def receive_messages(
        self,
        message: GroupChatParticipantMessage,
        ctx: WorkflowContext[GroupChatResponseMessage],
    ) -> None:
        self.conversation.extend(message.messages)

    @handler
    async def respond(
        self,
        request: GroupChatRequestMessage,
        ctx: WorkflowContext[GroupChatResponseMessage],
    ) -> None:
        transcript = "\n\n".join(
            f"[{message.author_name or message.role}]: {message.text}"
            for message in self.conversation
        )
        if request.additional_instruction:
            transcript += "\n\n" + request.additional_instruction
        # Errors and cancellation propagate to CouncilSession. No fake successful
        # participant output is generated when an underlying model/tool fails.
        result = await self.venom_agent.process(transcript)
        response = Message("assistant", [result], author_name=self.name)
        # GroupChat broadcasts a response to other participants, excluding its
        # author. Keep the author's own turn once and record Venom's transcript.
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
) -> VenomAgent:
    return VenomAgent(
        name,
        agent,
        system_message
        or str(getattr(agent, "SYSTEM_PROMPT", None) or f"Jesteś agentem {name}"),
        llm_config,
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
