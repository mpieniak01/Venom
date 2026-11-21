"""Request and response formats for local Ollama text models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.config import SETTINGS
from venom_core.core.model_registry_clients import OllamaClient
from venom_core.core.ollama_runtime_capabilities import is_gemma4_model_name
from venom_core.services.ollama_audio import OMNI_MODEL_ID, is_host_ollama
from venom_core.utils.llm_runtime import LLMRuntimeInfo
from venom_core.utils.ollama_tuning import (
    build_ollama_runtime_options,
    normalize_ollama_keep_alive,
)

if TYPE_CHECKING:
    from venom_core.services.chat_policy.qualified_chat import QualifiedReply

QUALIFIED_MODEL = "gemma4:12b-it-q4_k_m"
QUALIFIED_BOLT_MODEL = "hf.co/nvidia/nvidia-nemotron-3.5-bolt-e4b-4gb:q4_k_m"


@dataclass(frozen=True)
class OllamaTextProfile:
    direct_drafts: bool
    plain_text_rewrites: bool


_QUALIFIED_PROFILES = {
    QUALIFIED_MODEL: OllamaTextProfile(direct_drafts=True, plain_text_rewrites=False),
    QUALIFIED_BOLT_MODEL: OllamaTextProfile(
        direct_drafts=False, plain_text_rewrites=True
    ),
}


def qualified_profile(model_name: str) -> OllamaTextProfile | None:
    return _QUALIFIED_PROFILES.get(model_name.casefold())


def plain_text_rewrite(model_name: str) -> bool:
    profile = qualified_profile(model_name)
    return profile is not None and profile.plain_text_rewrites


def local_direct_model(
    request: SimpleChatRequest, runtime: LLMRuntimeInfo, model_name: str
) -> Literal["omni", "gemma"] | None:
    """Select the prompt profile supported by this local model and request."""
    from venom_core.services.chat_material_payload import has_materials

    omni = model_name == OMNI_MODEL_ID
    if not omni and not is_gemma4_model_name(model_name):
        return None
    if (
        not is_host_ollama(runtime)
        or request.tools
        or request.tool_choice is not None
        or has_materials(request)
    ):
        return None
    return "omni" if omni else "gemma"


def native_chat_url(runtime: LLMRuntimeInfo) -> str:
    return f"{OllamaClient(runtime.endpoint).endpoint}/api/chat"


def native_draft_payload(
    request: SimpleChatRequest,
    messages: list[dict[str, Any]],
    reply: QualifiedReply,
    model_name: str,
) -> dict[str, Any]:
    rewrite = reply.rewrite
    native_text = rewrite is not None and plain_text_rewrite(model_name)
    default_limit = 160 if native_text else 96
    options = {
        "num_ctx": build_ollama_runtime_options(SETTINGS)["num_ctx"],
        "num_predict": request.max_tokens
        if request.max_tokens is not None
        else default_limit,
        "temperature": request.temperature if request.temperature is not None else 0,
        "seed": request.seed if request.seed is not None else 42,
        "top_k": 1,
    }
    if request.top_p is not None:
        options["top_p"] = request.top_p
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": normalize_ollama_keep_alive(SETTINGS.LLM_KEEP_ALIVE),
        "options": options,
    }
    schema = rewrite.schema(plain_text=native_text) if rewrite else reply.schema
    if schema is not None:
        payload["format"] = schema
    return payload


def completed_native_draft(data: Any) -> str:
    if (
        not isinstance(data, dict)
        or data.get("done") is not True
        or data.get("done_reason") != "stop"
    ):
        return ""
    message = data.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return content if isinstance(content, str) else ""
