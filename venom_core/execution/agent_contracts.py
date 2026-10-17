"""Venom conversation/tool contracts, independent of the orchestration SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Iterator, TypeVar

from pydantic import BaseModel, ConfigDict


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ConversationMessage:
    role: MessageRole | str
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    native_message: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.role = MessageRole(self.role)

    def __str__(self) -> str:
        return self.content


class ConversationHistory:
    """Caller-owned history; native tool messages survive subsequent model turns."""

    def __init__(self, messages=None, system_message: str | None = None):
        self.messages: list[ConversationMessage] = list(messages or [])
        if system_message:
            self.add_system_message(system_message)

    def add_message(self, message: ConversationMessage) -> None:
        self.messages.append(message)

    def add_system_message(self, content: str) -> None:
        self.add_message(ConversationMessage(MessageRole.SYSTEM, content))

    def add_user_message(self, content: str) -> None:
        self.add_message(ConversationMessage(MessageRole.USER, content))

    def add_assistant_message(self, content: str) -> None:
        self.add_message(ConversationMessage(MessageRole.ASSISTANT, content))

    def __iter__(self) -> Iterator[ConversationMessage]:
        return iter(self.messages)

    def __len__(self) -> int:
        return len(self.messages)

    def __getitem__(self, index):
        return self.messages[index]


@dataclass(frozen=True)
class ToolPolicy:
    filters: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def Auto(cls, filters: dict[str, list[str]] | None = None):
        return cls(filters or {})


class CompletionOptions(BaseModel):
    """Mutable generation options accepted at Venom's existing agent boundary."""

    model_config = ConfigDict(extra="allow")
    service_id: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    function_choice_behavior: ToolPolicy | None = None
    extra_body: dict[str, Any] | None = None


F = TypeVar("F", bound=Callable[..., Any])


def tool_function(
    *, name: str | None = None, description: str = ""
) -> Callable[[F], F]:
    """Declare a callable tool without replacing Python method binding semantics."""

    def decorate(function: F) -> F:
        setattr(
            function,
            "__venom_tool__",
            {"name": name or function.__name__, "description": description},
        )
        return function

    return decorate
