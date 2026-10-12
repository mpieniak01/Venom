"""Optional conversation extensions with host-owned turn context.

Correlation identifiers and actor categories carry no operator authorization.
Providers live outside the kernel so a model refresh does not recreate them.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import math
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

Actor = Literal["chat", "voice"]
Language = Literal["pl", "en", "de"]


@dataclass(frozen=True, slots=True)
class ConversationContext:
    task_id: str
    conversation_id: str
    actor: Actor
    created_at: float = field(default_factory=time.monotonic)
    deadline: float | None = None
    language: Language = "pl"
    target_device_id: str | None = None

    def __post_init__(self) -> None:
        if self.actor not in {"chat", "voice"} or self.language not in {
            "pl",
            "en",
            "de",
        }:
            raise ValueError("invalid_conversation_context")
        if not self.task_id or not self.conversation_id:
            raise ValueError("invalid_conversation_context")
        if not math.isfinite(self.created_at):
            raise ValueError("invalid_conversation_context")
        if self.deadline is None:
            object.__setattr__(self, "deadline", self.created_at + 30.0)
        elif not math.isfinite(self.deadline) or self.deadline < self.created_at:
            raise ValueError("invalid_conversation_context")


_context: ContextVar[ConversationContext | None] = ContextVar(
    "conversation_context", default=None
)
_default_registry: ConversationProviderRegistry | None = None


def current_conversation_context() -> ConversationContext | None:
    return _context.get()


@contextmanager
def conversation_turn(context: ConversationContext):
    token = _context.set(context)
    try:
        yield context
    finally:
        _context.reset(token)


def create_conversation_context(
    actor: Actor,
    *,
    task_id: str | None = None,
    conversation_id: str | None = None,
    language: str | None = None,
    timeout_s: float = 30.0,
) -> ConversationContext:
    now = time.monotonic()
    selected_language: Language = (
        "en" if language == "en" else "de" if language == "de" else "pl"
    )
    return ConversationContext(
        task_id=task_id or uuid4().hex,
        conversation_id=conversation_id or uuid4().hex,
        actor=actor,
        created_at=now,
        deadline=now + timeout_s,
        language=selected_language,
    )


def get_conversation_registry() -> ConversationProviderRegistry | None:
    return _default_registry


def set_conversation_registry(
    registry: ConversationProviderRegistry | None,
) -> ConversationProviderRegistry | None:
    global _default_registry
    previous, _default_registry = _default_registry, registry
    return previous


class ConversationProviderError(RuntimeError):
    def __init__(self, code: str, module_id: str | None = None):
        super().__init__(code)
        self.code, self.module_id = code, module_id


class ConversationProviderRegistry:
    def __init__(
        self,
        app: Any,
        factories: Callable[[], Mapping[str, Callable[[Any], Any]]] | None = None,
    ):
        self.app = app
        self.factories = factories
        self.providers: dict[str, Any] = {}
        self._registered_factories: dict[str, Callable[[Any], Any]] = {}
        self._refresh_lock = asyncio.Lock()
        self._active: dict[asyncio.Task[Any], str] = {}
        self._prepared: dict[ConversationContext, dict[str, Any]] = {}
        self.closed = False

    async def refresh(self) -> None:
        if self.closed or self.factories is None:
            return
        async with self._refresh_lock:
            if self.closed:
                return
            desired = dict(self.factories())
            for module_id in list(self.providers):
                if self._registered_factories.get(module_id) is not desired.get(
                    module_id
                ):
                    await self.unregister(module_id)
            for module_id, factory in desired.items():
                if module_id in self.providers:
                    continue
                provider = factory(self.app)
                if inspect.isawaitable(provider):
                    provider = await provider
                if self.closed:
                    await self._close_provider(module_id, provider)
                    return
                await self.register(module_id, provider)
                self._registered_factories[module_id] = factory

    async def register(self, module_id: str, provider: Any) -> None:
        if self.closed:
            raise ConversationProviderError("conversation_registry_closed")
        if not module_id or not inspect.iscoroutinefunction(
            getattr(provider, "handle", None)
        ):
            raise ConversationProviderError("conversation_provider_invalid", module_id)
        if module_id in self.providers:
            await self.unregister(module_id)
        self.providers[module_id] = provider

    async def unregister(self, module_id: str) -> None:
        provider = self.providers.pop(module_id, None)
        self._registered_factories.pop(module_id, None)
        if provider is None:
            return
        for task, owner in list(self._active.items()):
            if owner == module_id:
                task.cancel()
        for prepared in self._prepared.values():
            prepared.pop(module_id, None)
        await self._close_provider(module_id, provider)

    @staticmethod
    async def _close_provider(module_id: str, provider: Any) -> None:
        close = getattr(provider, "close", None)
        if callable(close):
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                raise ConversationProviderError(
                    "conversation_provider_close_failed", module_id
                ) from exc

    async def list_tools(self) -> dict[str, list[dict[str, Any]]]:
        """Expose provider-owned schemas, without global kernel plugin sharing."""
        if self.closed:
            return {}
        await self.refresh()
        catalog = {}
        for module_id, provider in list(self.providers.items()):
            getter = getattr(provider, "list_tools", None)
            if not callable(getter):
                continue
            tools = getter()
            if inspect.isawaitable(tools):
                tools = await tools
            if (
                not isinstance(tools, list)
                or len(tools) > 64
                or any(not isinstance(tool, dict) for tool in tools)
            ):
                raise ConversationProviderError(
                    "conversation_invalid_tool_catalog", module_id
                )
            try:
                payload = json.dumps(tools, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise ConversationProviderError(
                    "conversation_invalid_tool_catalog", module_id
                ) from exc
            if len(payload) > 256 * 1024:
                raise ConversationProviderError(
                    "conversation_invalid_tool_catalog", module_id
                )
            if self.providers.get(module_id) is provider:
                catalog[module_id] = copy.deepcopy(tools)
        return catalog

    @staticmethod
    def _validate_context(context: ConversationContext) -> None:
        if not isinstance(context, ConversationContext):
            raise ConversationProviderError("conversation_context_required")
        assert context.deadline is not None

    async def prepare(self, text: str, context: ConversationContext) -> None:
        """Bind optional provider scope before classification or other planning."""
        if self.closed:
            raise ConversationProviderError("conversation_registry_closed")
        self._validate_context(context)
        await self.refresh()
        if context in self._prepared:
            return
        providers = dict(self.providers)
        self._prepared[context] = providers
        with conversation_turn(context):
            for module_id, provider in list(providers.items()):
                if callable(getattr(provider, "prepare", None)):
                    await self._invoke(module_id, provider, "prepare", context, text)

    async def finish(self, context: ConversationContext) -> None:
        """Always release prepared scopes, including expired or cancelled turns."""
        self._validate_context(context)
        providers = self._prepared.pop(context, {})
        failure = None
        with conversation_turn(context):
            for module_id, provider in list(providers.items()):
                if not callable(getattr(provider, "finish", None)):
                    continue
                try:
                    await self._invoke(
                        module_id, provider, "finish", context, cleanup=True
                    )
                except ConversationProviderError as exc:
                    failure = failure or exc
        if failure is not None:
            raise failure

    async def _invoke(
        self,
        module_id: str,
        provider: Any,
        operation: str,
        context: ConversationContext,
        *args: Any,
        cleanup: bool = False,
    ) -> Any:
        assert context.deadline is not None
        remaining = 5.0 if cleanup else context.deadline - time.monotonic()
        if remaining <= 0:
            raise ConversationProviderError("conversation_deadline", module_id)
        method = getattr(provider, operation)
        if not inspect.iscoroutinefunction(method):
            raise ConversationProviderError("conversation_provider_invalid", module_id)
        task = asyncio.create_task(method(*args, context))
        self._active[task] = module_id
        try:
            result = await asyncio.wait_for(task, timeout=remaining)
        except TimeoutError as exc:
            raise ConversationProviderError("conversation_deadline", module_id) from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise ConversationProviderError(
                "conversation_provider_failed", module_id
            ) from exc
        finally:
            self._active.pop(task, None)
        if not cleanup:
            if self.closed or self.providers.get(module_id) is not provider:
                raise ConversationProviderError(
                    "conversation_provider_disabled", module_id
                )
            if time.monotonic() > context.deadline:
                raise ConversationProviderError("conversation_deadline", module_id)
        return result

    async def _route(
        self, operation: str, text: str, context: ConversationContext
    ) -> str | None:
        if self.closed:
            raise ConversationProviderError("conversation_registry_closed")
        self._validate_context(context)
        await self.refresh()
        with conversation_turn(context):
            for module_id, provider in list(self.providers.items()):
                if not callable(getattr(provider, operation, None)):
                    continue
                result = await self._invoke(
                    module_id, provider, operation, context, text
                )
                if result is not None:
                    if not isinstance(result, str) or len(result) > 32_768:
                        raise ConversationProviderError(
                            "conversation_invalid_output", module_id
                        )
                    return result
        return None

    async def handle(self, text: str, context: ConversationContext) -> str | None:
        return await self._route("handle", text, context)

    async def urgent(self, text: str, context: ConversationContext) -> str | None:
        """Optional safety-only route; ordinary handling remains after policy."""
        return await self._route("urgent", text, context)

    async def close(self) -> None:
        self.closed = True
        failure = None
        async with self._refresh_lock:
            for module_id in list(self.providers):
                try:
                    await self.unregister(module_id)
                except ConversationProviderError as exc:
                    failure = failure or exc
            self._prepared.clear()
        if failure is not None:
            raise failure


async def handle_conversation_turn(
    text: str, context: ConversationContext
) -> str | None:
    """Common host entrypoint; absent extensions leave ordinary chat intact."""
    registry = get_conversation_registry()
    if registry is None:
        return None
    return await registry.handle(text, context)


async def prepare_conversation_turn(text: str, context: ConversationContext) -> None:
    registry = get_conversation_registry()
    if registry is not None:
        await registry.prepare(text, context)


async def finish_conversation_turn(context: ConversationContext) -> None:
    registry = get_conversation_registry()
    if registry is not None:
        await registry.finish(context)


async def urgent_conversation_turn(
    text: str, context: ConversationContext
) -> str | None:
    registry = get_conversation_registry()
    if registry is None:
        return None
    return await registry.urgent(text, context)
