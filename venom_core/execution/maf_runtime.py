"""Native Microsoft Agent Framework execution behind Venom's service contract.

No Semantic Kernel imports or fallback: tool calling is performed by MAF.
SDK imports are lazy so direct-to-LLM requests need not construct an agent.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import aclosing
from functools import wraps
from typing import TYPE_CHECKING, Any, cast

from venom_core.execution.agent_contracts import (
    CompletionOptions,
    ConversationHistory,
    ConversationMessage,
)
from venom_core.execution.maf_transport import (
    install_maf_transport_observer,
    maf_transport_scope,
)
from venom_core.services.runtime_admission import (
    admitted_operation,
    get_runtime_admission,
)
from venom_core.utils.ollama_tuning import normalize_ollama_keep_alive

if TYPE_CHECKING:
    from agent_framework import AgentResponse, ChatContext, ChatResponse, Message
    from agent_framework_openai import OpenAIChatCompletionOptions


class AgentRuntime:
    """Named model services and callable tool groups owned by one Venom runtime."""

    def __init__(self, permission_checker=None):
        self.permission_checker = permission_checker
        self.services: dict[str, MafChatService] = {}
        self.plugins: dict[str, dict[str, Any]] = {}

    def add_service(self, service: MafChatService) -> None:
        if service.service_id in self.services:
            raise ValueError("duplicate_model_service")
        self.services[service.service_id] = service

    def get_service(self, service_id: str | None = None):
        if service_id in self.services:
            return self.services[service_id]
        if service_id and service_id != "default":
            raise KeyError(service_id)
        if not self.services:
            raise LookupError("model_service_not_configured")
        return next(iter(self.services.values()))

    def add_plugin(self, plugin: Any, plugin_name: str) -> dict[str, Any]:
        functions = {}
        for _, method in inspect.getmembers(plugin, callable):
            metadata = getattr(method, "__venom_tool__", None)
            if metadata:
                functions[metadata["name"]] = method
        if not functions:
            raise ValueError("tool_group_has_no_functions")
        # Build every schema before publishing any replacement callable.
        for name, method in functions.items():
            self._native_tool(plugin_name, name, method).parameters()
        self.plugins[plugin_name] = functions
        return functions

    def _native_tool(self, group: str, name: str, method: Any):
        from agent_framework import FunctionTool

        return FunctionTool(
            name=f"{group}-{name}",
            description=method.__venom_tool__["description"],
            func=self._guarded_tool(method),
        )

    def _guarded_tool(self, method):
        owner = (
            type(method.__self__).__name__
            if hasattr(method, "__self__")
            else method.__name__
        )
        # Policy belongs to core, never to metadata supplied by a custom tool.
        action_permissions = {
            (
                "venom_core.execution.skills.file_skill",
                "FileSkill",
                name,
            ): "FileReadSkill"
            for name in ("read_file", "list_files", "file_exists")
        }
        action_permissions.update(
            {
                (
                    "venom_core.memory.memory_skill",
                    "MemorySkill",
                    name,
                ): "MemoryRecallSkill"
                for name in ("recall", "memory_search")
            }
        )
        action_permissions[
            ("venom_core.memory.memory_skill", "MemorySkill", "memorize")
        ] = "FileWriteSkill"
        policy_name = action_permissions.get(
            (method.__module__, owner, method.__name__), owner
        )

        def check_permission():
            checker = self.permission_checker
            if checker is None:
                from venom_core.core.permission_guard import permission_guard

                checker = permission_guard.check_permission
            if not checker(policy_name):
                raise PermissionError("tool_permission_denied")

        if inspect.iscoroutinefunction(method):

            @wraps(method)
            async def invoke(*args, **kwargs):
                check_permission()
                return await method(*args, **kwargs)
        else:

            @wraps(method)
            def invoke(*args, **kwargs):
                check_permission()
                return method(*args, **kwargs)

        return invoke

    def native_tools(self, filters: dict[str, list[str]] | None = None):
        filters = filters or {}
        tools = []
        for group, functions in self.plugins.items():
            included = filters.get("included_plugins")
            if (included is not None and group not in included) or group in filters.get(
                "excluded_plugins", []
            ):
                continue
            for name, method in functions.items():
                full_name = f"{group}-{name}"
                included_functions = filters.get("included_functions")
                if (
                    included_functions is not None
                    and full_name not in included_functions
                ):
                    continue
                if full_name in filters.get("excluded_functions", []):
                    continue
                tools.append(self._native_tool(group, name, method))
        return tools

    async def aclose(self) -> None:
        for service in self.services.values():
            await service.aclose()


class MafChatService:
    """Chat-completions client for local/OpenAI-compatible endpoints using MAF."""

    def __init__(
        self,
        service_id: str,
        ai_model_id: str,
        *,
        async_client=None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        from agent_framework_openai import OpenAIChatCompletionClient
        from openai import AsyncOpenAI

        self.service_id = service_id
        self.ai_model_id = ai_model_id
        async_client = async_client or AsyncOpenAI(api_key=api_key, base_url=base_url)
        install_maf_transport_observer(async_client)
        self.client = OpenAIChatCompletionClient(
            model=ai_model_id,
            async_client=async_client,
            api_key=api_key,
            base_url=base_url,
        )
        self.client.function_invocation_configuration.update(
            {
                "max_iterations": 5,
                "max_function_calls": 20,
                "max_duration_seconds": 30.0,
                "allow_concurrent_invocation": False,
                "terminate_on_unknown_calls": True,
                "include_detailed_errors": False,
            }
        )
        self._owned_client = async_client

    @staticmethod
    def _messages(history: ConversationHistory):
        from agent_framework import Message

        return [
            message.native_message
            if message.native_message is not None
            else Message(
                getattr(message.role, "value", message.role), [message.content]
            )
            for message in history
        ]

    @staticmethod
    def _options(settings: CompletionOptions | None) -> OpenAIChatCompletionOptions:
        settings = settings or CompletionOptions()
        options = settings.model_dump(
            exclude_none=True,
            exclude={"service_id", "function_choice_behavior", "extra_body"},
        )
        standard = {
            "max_tokens",
            "temperature",
            "top_p",
            "stop",
            "seed",
            "presence_penalty",
            "frequency_penalty",
            "logit_bias",
            "response_format",
            "reasoning_effort",
            "max_completion_tokens",
            "logprobs",
            "top_logprobs",
            "user",
        }
        # Venom uses provider-native aliases internally, while this boundary
        # always targets Chat Completions (including local engines).
        for alias in ("max_new_tokens", "num_predict"):
            value = options.pop(alias, None)
            if value is not None:
                options.setdefault("max_tokens", value)
        extensions = {
            key: options.pop(key) for key in options.copy() if key not in standard
        }
        extensions.update(settings.extra_body or {})
        if "keep_alive" in extensions:
            extensions["keep_alive"] = normalize_ollama_keep_alive(
                extensions["keep_alive"]
            )
        if set(extensions) & {
            "model",
            "messages",
            "tools",
            "stream",
            "api_key",
            "base_url",
        }:
            raise ValueError("generation_options_cannot_override_transport")
        if "max_tokens" in options and "max_completion_tokens" not in options:
            # MAF's generic option is translated to max_completion_tokens. Local
            # Chat Completions servers in Venom still expose max_tokens. Use the
            # SDK's public extra_body mechanism to retain that wire contract.
            extensions["max_tokens"] = options.pop("max_tokens")
        if extensions:
            options["extra_body"] = extensions
        return cast("OpenAIChatCompletionOptions", options)

    operator_provider: str | None = None

    def _assert_operator_provider_enabled(self) -> None:
        if self.operator_provider is not None:
            from venom_core.services.remote_provider_control import assert_enabled

            assert_enabled(self.operator_provider)

    async def get_chat_message_content(
        self,
        *,
        chat_history: ConversationHistory,
        settings: CompletionOptions | None = None,
        kernel: AgentRuntime | None = None,
    ):
        # This phase only builds local request data; it cannot start daemon work.
        # Check ownership first, and never quarantine a rejected local option.
        with get_runtime_admission().operation(
            kind="maf_validation", confirm_quiescent=lambda: True
        ):
            self._assert_operator_provider_enabled()
            messages = self._messages(chat_history)
            options = self._options(settings)
        return await self._generate(
            chat_history=chat_history,
            settings=settings,
            kernel=kernel,
            messages=messages,
            options=options,
        )

    @admitted_operation("maf_generation", mutation=False)
    async def _generate(
        self,
        *,
        chat_history: ConversationHistory,
        settings: CompletionOptions | None,
        kernel: AgentRuntime | None,
        messages: list[Any],
        options: OpenAIChatCompletionOptions,
    ):
        with maf_transport_scope():
            response: AgentResponse[Any] | ChatResponse[Any]
            if (
                settings is not None
                and settings.function_choice_behavior is not None
                and kernel is not None
            ):
                from agent_framework import chat_middleware

                tools = kernel.native_tools(settings.function_choice_behavior.filters)
                input_count = len(messages)
                recorded_count = 0

                def record_intermediate(native_messages: Sequence[Message]) -> None:
                    nonlocal recorded_count
                    for message in native_messages[recorded_count:]:
                        chat_history.add_message(
                            ConversationMessage(
                                message.role, message.text, native_message=message
                            )
                        )
                    recorded_count = len(native_messages)

                @chat_middleware
                async def preserve_tool_history(
                    context: ChatContext, call_next: Callable[[], Awaitable[None]]
                ) -> None:
                    # Each call contains the generated prefix after the original inputs.
                    # Save completed tool results before another provider await can fail.
                    record_intermediate(context.messages[input_count:])
                    await call_next()

                response = await self.client.as_agent(
                    tools=tools, middleware=[preserve_tool_history]
                ).run(messages, options=options)
                # The caller still owns persistence of the final assistant response.
                record_intermediate(response.messages[:-1])
            else:
                response = await self.client.get_response(messages, options=options)
            return ConversationMessage(
                "assistant",
                response.text,
                native_message=response.messages[-1] if response.messages else None,
            )

    async def get_chat_message_contents(self, **kwargs):
        return [await self.get_chat_message_content(**kwargs)]

    async def get_streaming_chat_message_contents(
        self,
        *,
        chat_history: ConversationHistory,
        settings: CompletionOptions | None = None,
        **kwargs,
    ) -> AsyncIterator[list[ConversationMessage]]:
        # This phase only builds local request data; it cannot start daemon work.
        # Check ownership first, and never quarantine a rejected local option.
        with get_runtime_admission().operation(
            kind="maf_validation", confirm_quiescent=lambda: True
        ):
            self._assert_operator_provider_enabled()
            messages = self._messages(chat_history)
            options = self._options(settings)
        async with aclosing(self._stream(messages, options)) as stream:
            async for chunk in stream:
                yield chunk

    @admitted_operation("maf_stream", mutation=False)
    async def _stream(
        self, messages: list[Any], options: OpenAIChatCompletionOptions
    ) -> AsyncIterator[list[ConversationMessage]]:
        with maf_transport_scope():
            async for update in self.client.get_response(
                messages,
                stream=True,
                options=options,
            ):
                if update.text:
                    yield [ConversationMessage("assistant", update.text)]

    async def aclose(self) -> None:
        if self._owned_client is not None:
            await self._owned_client.close()
