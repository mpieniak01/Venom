"""Opt-in native Omni adapter selection for the ordinary text chat endpoint.

Selections are process-local and probe-before-commit. No global runtime setting
is rewritten: disabling the overlay restores the exact ordinary runtime path.
Catalog integrity is distinct from quality qualification; activation is explicit.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from venom_core.api.schemas.llm_simple import MAX_CHAT_HISTORY_CHARS, SimpleChatRequest
from venom_core.services import omni_native_dialogue
from venom_core.services.chat_policy.direct_calculator import (
    execute_calculator,
    plan_calculator,
)
from venom_core.services.chat_policy.direct_correction import (
    CorrectionContext,
    corrected_registration_reply,
    correction_context,
)
from venom_core.services.chat_policy.direct_drafts import reservation_confirmation_draft
from venom_core.services.chat_policy.direct_invitations import (
    exchange_title_context,
    invitation_context,
)
from venom_core.services.model_resources import model_operation
from venom_core.services.remote_training.paths import operator_path
from venom_core.services.runtime_switch_gate import runtime_request_guard
from venom_core.services.training_experiments.adapters import (
    list_adapters,
    resolve_adapter,
)
from venom_core.services.training_experiments.profiles import read_json, stable_hash
from venom_core.utils.llm_runtime import get_active_llm_runtime

RUNTIME = "omni-native-peft-text"
_LOCK = asyncio.Lock()


def _error(code: str, status: int = 409) -> HTTPException:
    return HTTPException(status, {"reason_code": code})


@dataclass(frozen=True)
class Selection:
    directory: Path
    identity: dict[str, Any]
    catalog: Path
    snapshot: Path
    python_env: Path

    @property
    def runtime_id(self) -> str:
        return (
            f"{RUNTIME}:{self.identity['adapter_id']}:{self.identity['weights_sha256']}"
        )

    def payload(self) -> dict[str, Any]:
        return {"runtime": RUNTIME, "runtime_id": self.runtime_id, **self.identity}


_ACTIVE: Selection | None = None
_PREVIOUS: Selection | None = None
_ORDINARY: dict[str, Any] | None = None


def _ordinary_identity() -> dict[str, Any]:
    from venom_core.services import openrouter_runtime
    from venom_core.services.vast_chat_runtime import is_remote

    runtime = get_active_llm_runtime()
    if (
        is_remote(runtime)
        or runtime.host_local is False
        or openrouter_runtime.selection() is not None
    ):
        raise _error("omni_native_text_runtime_conflict")
    return runtime.to_payload()


def _check_ordinary() -> dict[str, Any]:
    current = _ordinary_identity()
    if _ORDINARY is not None and current != _ORDINARY:
        raise _error("omni_native_text_runtime_changed")
    return current


def _configuration() -> tuple[Path, Path, Path]:
    try:
        paths = [
            operator_path(Path(os.environ[name]))
            for name in (
                "OMNI_NATIVE_TEXT_CATALOG_ROOT",
                "OMNI_NATIVE_SNAPSHOT",
                "OMNI_NATIVE_TEXT_ENV",
            )
        ]
        if not all(p.is_dir() for p in paths):
            raise ValueError("directory_missing")
        # The sandbox shares this known Python base, never a caller-supplied program.
        if (paths[2] / "bin/python").resolve(strict=True) != Path(
            sys.executable
        ).resolve(strict=True):
            raise ValueError("python_base_mismatch")
        return paths[0], paths[1], paths[2]
    except (KeyError, OSError, ValueError) as exc:
        raise _error("omni_native_text_not_configured", 503) from exc


def _resolve(adapter_id: str) -> Selection:
    catalog, snapshot, python_env = _configuration()
    try:
        # resolve_adapter validates the ID before joining it with the catalog.
        from venom_core.services.remote_training.lifecycle import validate_run_id

        validate_run_id(adapter_id)
        config = read_json(
            operator_path(catalog / "adapters" / adapter_id / "adapter_config.json")
        )
        selector = config["target_modules"]
        # The existing adapter validator verifies this selector and module allowlist.
        modules = selector.rsplit("(", 1)[-1].removesuffix(")").split("|")
        directory, entry = resolve_adapter(
            catalog,
            adapter_id,
            {
                "rank": config["r"],
                "alpha": config["lora_alpha"],
                "dropout": config["lora_dropout"],
                "target_modules": modules,
            },
        )
        return Selection(directory, entry, catalog, snapshot, python_env)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise _error("omni_native_text_adapter_invalid", 422) from exc


def state() -> dict[str, Any]:
    return {
        "selection": _ACTIVE.payload() if _ACTIVE else None,
        "previous": _PREVIOUS.payload() if _PREVIOUS else None,
        "persistent": False,
        "ordinary_runtime": dict(_ORDINARY) if _ORDINARY else None,
    }


def catalog() -> list[dict[str, Any]]:
    root, _, _ = _configuration()
    return list_adapters(root)


def selected() -> bool:
    return _ACTIVE is not None


async def route_response(
    request: SimpleChatRequest, *, system_context: str = ""
) -> StreamingResponse | None:
    """Claim native requests and reject stale native runtime identities."""
    if selected():
        from venom_core.services import openrouter_runtime

        if openrouter_runtime.selection() is not None:
            raise _error("omni_native_text_runtime_conflict")
        return await response(request, system_context=system_context)
    if (request.expected_runtime_id or "").startswith(f"{RUNTIME}:"):
        raise _error("omni_native_text_selection_changed")
    return None


def _verify_selection(selection: Selection) -> None:
    if _resolve(selection.identity["adapter_id"]) != selection:
        raise _error("omni_native_text_selection_changed")


async def _generate(
    selection: Selection, messages: list[dict[str, str]], max_tokens: int
) -> dict[str, Any]:
    _verify_selection(selection)
    payload = json.dumps(
        {
            "identity": selection.identity,
            "messages": messages,
            "max_tokens": max_tokens,
        },
        ensure_ascii=False,
    ).encode()
    try:
        output = await omni_native_dialogue._invoke(
            selection.snapshot,
            payload,
            adapter=selection.directory,
            python_env=selection.python_env,
        )
        result = json.loads(output)
        if (
            result.get("identity") != selection.identity
            or result.get("input_messages_sha256") != stable_hash(messages)
            or result.get("snapshot_manifest_sha256")
            != selection.identity["snapshot_sha256"]
            or not isinstance(result.get("text"), str)
            or not result["text"].strip()
            or omni_native_dialogue.contains_tool_markup(result["text"])
        ):
            raise ValueError("invalid_worker_result")
        return result
    except (
        OSError,
        ValueError,
        omni_native_dialogue.NativeDialogueError,
    ) as exc:
        raise _error("omni_native_text_generation_failed", 503) from exc


async def _switch_locked(
    adapter_id: str | None,
    expected_runtime_id: str | None,
    *,
    expected_selection: Selection | None = None,
) -> dict[str, Any]:
    global _ACTIVE, _PREVIOUS, _ORDINARY
    if expected_runtime_id != (_ACTIVE.runtime_id if _ACTIVE else None):
        raise _error("omni_native_text_selection_changed")
    ordinary = _check_ordinary()
    candidate = _resolve(adapter_id) if adapter_id is not None else None
    if expected_selection is not None and candidate != expected_selection:
        raise _error("omni_native_text_selection_changed")
    async with runtime_request_guard(
        request_kind="omni_native_text_switch", provider=RUNTIME
    ):
        failure = None
        try:
            if candidate:
                await _generate(
                    candidate, [{"role": "user", "content": "Napisz: gotowe."}], 8
                )
        except (HTTPException, asyncio.CancelledError) as exc:
            failure = exc
    if failure:
        raise failure
    if _ordinary_identity() != ordinary:
        raise _error("omni_native_text_runtime_changed")
    _PREVIOUS, _ACTIVE = _ACTIVE, candidate
    _ORDINARY = ordinary if candidate else None
    return state()


@model_operation
async def switch(
    adapter_id: str | None, *, expected_runtime_id: str | None = None
) -> dict[str, Any]:
    """Probe before atomically committing; failed/cancelled loads keep prior state."""
    global _ACTIVE, _PREVIOUS, _ORDINARY
    async with _LOCK:
        if adapter_id is None:
            if expected_runtime_id != (_ACTIVE.runtime_id if _ACTIVE else None):
                raise _error("omni_native_text_selection_changed")
            async with runtime_request_guard(
                request_kind="omni_native_text_switch", provider=RUNTIME
            ):
                _PREVIOUS, _ACTIVE, _ORDINARY = _ACTIVE, None, None
            return state()
        return await _switch_locked(adapter_id, expected_runtime_id)


@model_operation
async def rollback(*, expected_runtime_id: str | None = None) -> dict[str, Any]:
    """Select and probe the previous weights under the same atomic selection lock."""
    async with _LOCK:
        return await _switch_locked(
            _PREVIOUS.identity["adapter_id"] if _PREVIOUS else None,
            expected_runtime_id,
            expected_selection=_PREVIOUS,
        )


def _validate_request(
    request: SimpleChatRequest, selection: Selection
) -> list[dict[str, str]]:
    if request.model not in (
        None,
        selection.identity["adapter_id"],
        selection.runtime_id,
    ):
        raise _error("omni_native_text_selection_changed")
    if request.expected_runtime_id not in (None, selection.runtime_id):
        raise _error("omni_native_text_selection_changed")
    if request.expected_config_hash not in (None, selection.identity["config_sha256"]):
        raise _error("omni_native_text_selection_changed")
    if (
        request.tools
        or request.tool_choice is not None
        or request.material_ids
        or request.response_format
        or request.format
        or request.studio_normal
        or request.temperature not in (None, 0.0)
        or request.top_p not in (None, 1.0)
        or request.logprobs
        or request.top_logprobs not in (None, 0)
        or request.seed is not None
        or request.think
        or request.stream is False
    ):
        raise _error("omni_native_text_feature_unsupported", 422)
    if (
        sum(len(row.content) for row in request.history) + len(request.content)
        > MAX_CHAT_HISTORY_CHARS
    ):
        raise _error("omni_native_text_context_limit", 413)
    return [
        *[row.model_dump(include={"role", "content"}) for row in request.history],
        {"role": "user", "content": request.content},
    ]


def _calculator_reply(
    selection: Selection, messages: list[dict[str, str]]
) -> dict[str, Any] | None:
    plan = plan_calculator(messages[-1]["content"], messages[:-1])
    if plan is None:
        return None
    _verify_selection(selection)
    return execute_calculator(plan)


@model_operation
async def response(
    request: SimpleChatRequest, *, system_context: str = ""
) -> StreamingResponse:
    """Use unchanged request history, including this adapter's earlier answers."""
    async with _LOCK:
        selection = _ACTIVE
        if selection is None:
            raise _error("omni_native_text_selection_changed")
        messages = _validate_request(request, selection)
        correction, system_context = _chat_context(request, messages, system_context)
        max_tokens = _request_token_limit(request)
        ordinary = _check_ordinary()
        result = await _run_native_response(selection, messages, max_tokens, correction)
        if _ordinary_identity() != ordinary:
            raise _error("omni_native_text_runtime_changed")
        result["previous_runtime"] = ordinary
        _finalize_correction(result, correction)
    request_id = str(uuid4())
    metadata = {
        **selection.payload(),
        **{k: v for k, v in result.items() if k not in {"text", "identity"}},
    }

    async def chunks():
        for kind, value in (
            ("start", {"request_id": request_id, "model_identity": metadata}),
            ("content", {"text": result["text"]}),
            ("done", {"model_identity": metadata}),
        ):
            yield (
                "event: "
                + kind
                + "\ndata: "
                + json.dumps(value, ensure_ascii=False)
                + "\n\n"
            )

    return StreamingResponse(
        chunks(), media_type="text/event-stream", headers={"X-Request-ID": request_id}
    )


def _chat_context(
    request: SimpleChatRequest, messages: list[dict[str, str]], system_context: str
) -> tuple[CorrectionContext | None, str]:
    preceding_users = [
        message["content"] for message in messages[:-1] if message["role"] == "user"
    ]
    correction = correction_context(request.content, preceding_users)
    if correction is None:
        correction = invitation_context(request.content, messages[:-1])
    if correction is None:
        draft = reservation_confirmation_draft(request.content, preceding_users)
        if draft is not None:
            correction = CorrectionContext(
                "reservation_confirmation_draft", draft, verified_reply=draft
            )
    if correction is None:
        correction = exchange_title_context(request.content)
    if correction:
        system_context = "\n\n".join(filter(None, (system_context, correction.text)))
    if system_context:
        messages.insert(0, {"role": "system", "content": system_context})
    return correction, system_context


def _request_token_limit(request: SimpleChatRequest) -> int:
    max_tokens = request.max_tokens if request.max_tokens is not None else 256
    if type(max_tokens) is not int or not 1 <= max_tokens <= 1024:
        raise _error("omni_native_text_token_limit", 422)
    return max_tokens


async def _run_native_response(
    selection: Selection,
    messages: list[dict[str, str]],
    max_tokens: int,
    correction: CorrectionContext | None,
) -> dict[str, Any]:
    result: dict[str, Any] | None = None
    failure: BaseException | None = None
    async with runtime_request_guard(
        request_kind=RUNTIME,
        provider=RUNTIME,
        model=selection.identity["adapter_id"],
    ):
        try:
            if correction and correction.verified_reply is not None:
                _verify_selection(selection)
                result = {
                    "text": correction.verified_reply,
                    "response_source": "correction_rule",
                }
            else:
                result = _calculator_reply(selection, messages)
                if result is None:
                    result = await _generate(selection, messages, max_tokens)
        except (HTTPException, asyncio.CancelledError) as exc:
            failure = exc
    if failure is not None:
        raise failure
    if result is None:
        raise _error("omni_native_text_response_missing")
    return result


def _finalize_correction(
    result: dict[str, Any], correction: CorrectionContext | None
) -> None:
    if correction is None:
        return
    result["context_policy"] = correction.scope
    if result.get("response_source") is not None:
        return
    revised = corrected_registration_reply(correction, result["text"])
    if revised is not None:
        result["text"] = revised
        result["response_source"] = "correction_rule"
