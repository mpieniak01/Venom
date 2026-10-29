"""One bounded OpenRouter request per Direct turn, using the installed shared core."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import aclosing
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from venom_core.services import openrouter_runtime as runtime
from venom_core.services.runtime_switch_gate import runtime_request_guard

_ACTIVE = asyncio.Lock()
client_factory = httpx.AsyncClient


def event(kind: str, value: dict[str, Any]) -> str:
    return "event: " + kind + "\ndata: " + json.dumps(value, ensure_ascii=True) + "\n\n"


def _request_limit(request, row):
    """Reject unsupported features and enforce the selected model output bound."""
    if request.stream is False or any(
        getattr(request, k, None) is not None
        for k in (
            "tools",
            "tool_choice",
            "response_format",
            "format",
            "logprobs",
            "top_logprobs",
            "think",
        )
    ):
        raise HTTPException(400, "openrouter_text_chat_only")
    if not request.session_id or len(request.session_id) > 256:
        raise HTTPException(400, "openrouter_session_required")
    maximum = (
        request.max_tokens
        if request.max_tokens is not None
        else min(1024, row["max_output_tokens"])
    )
    if type(maximum) is not int or not 0 < maximum <= row["max_output_tokens"]:
        raise HTTPException(400, "openrouter_output_limit")
    return maximum


def prepare(request) -> dict[str, Any]:
    """Freeze the destination and reserve the entire conservative request estimate."""
    row = runtime.assert_identity(request)
    maximum = _request_limit(request, row)
    from venom_core.config import SETTINGS

    messages = []
    if SETTINGS.SIMPLE_MODE_SYSTEM_PROMPT:
        messages.append(
            {"role": "system", "content": SETTINGS.SIMPLE_MODE_SYSTEM_PROMPT}
        )
    messages.extend(v.model_dump() for v in request.history)
    messages.append({"role": "user", "content": request.content})
    # UTF-8 bytes plus framing is deliberately conservative; this is not usage.
    input_bound = sum(len(v["content"].encode("utf-8")) + 128 for v in messages) + 256
    if input_bound + maximum > row["context_length"]:
        raise HTTPException(400, "openrouter_context_limit")
    core = runtime.library()
    prices = core.strict_prices(row["pricing"])
    amount = prices.estimate(input_bound, maximum)
    request_id = uuid4().hex
    conversation = json.dumps(
        ["openrouter", row["id"], request.session_id], separators=(",", ":")
    )
    try:
        payload = core.build_chat_payload(
            core.ChatRequest(
                model=core.ModelSpec(
                    row["id"],
                    prices,
                    row["context_length"],
                    row["max_output_tokens"],
                    row["provider_endpoint"],
                ),
                messages=messages,
                max_tokens=maximum,
                temperature=request.temperature
                if request.temperature is not None
                else 0.7,
                request_id=request_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(400, "openrouter_request_invalid") from exc
    for field in ("seed", "top_p"):
        if getattr(request, field, None) is not None:
            payload[field] = getattr(request, field)
    payload["provider"] = {
        "order": [row["provider_endpoint"]],
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "deny",
    }
    if row["id"].endswith(":free"):
        payload["provider"]["max_price"] = {"prompt": 0, "completion": 0, "request": 0}
    return {
        "id": request_id,
        "model": row["id"],
        "payload": payload,
        "core": core,
        "estimated": str(amount),
        "reserved_usd": "0",
        "credential": runtime.credential(),
        "runtime_id": request.expected_runtime_id,
        "config_hash": request.expected_config_hash,
        "conversation": conversation,
        "input_bound": input_bound,
        "context_length": row["context_length"],
    }


def quote_hash(turn):
    payload = {
        k: v for k, v in turn["payload"].items() if k not in {"request_id", "user"}
    }
    value = {
        "payload": payload,
        "config_hash": turn["config_hash"],
        "conversation": turn["conversation"],
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def quote(request):
    turn = prepare(request)
    return {
        "estimated_usd": turn["estimated"],
        "reserved_usd": "0",
        "currency": "USD",
        "max_output_tokens": turn["payload"]["max_tokens"],
        "input_token_upper_bound": turn["input_bound"],
        "context_length": turn["context_length"],
        "config_hash": turn["config_hash"],
        "quote_hash": quote_hash(turn),
    }


def _conversation_cost(turn):
    value = {
        "conversation_reported_usd": None,
        "conversation_reserved_usd": None,
        "conversation_state": "unknown",
    }
    if "ledger" not in turn:
        return value
    snapshot = turn["ledger"].snapshot(conversation_id=turn["conversation"])
    if not isinstance(snapshot, dict):
        return value
    rows = snapshot["reservations"]
    amount = turn["core"].decimal_amount
    reported = sum(
        (amount(row["cost"]) for row in rows if row["status"] == "settled"),
        start=amount(0),
    )
    held = sum(
        (amount(row["amount"]) for row in rows if row["status"] != "settled"),
        start=amount(0),
    )
    pending = any(row["status"] != "settled" for row in rows)
    return {
        "conversation_reported_usd": str(reported),
        "conversation_reserved_usd": str(held),
        "conversation_state": "pending" if pending else "settled",
    }


def cost(turn, actual, state):
    reserved = turn.get("reserved_usd", "0")
    if not turn.get("reservation_created", False) and actual is None:
        actual = turn["core"].decimal_amount(0)
        state = "settled"
    return {
        "estimated_usd": turn["estimated"],
        "reserved_usd": reserved,
        "reported_usd": str(actual) if actual is not None else None,
        "state": state,
        "currency": "USD",
        **_conversation_cost(turn),
    }


def _apply_metadata(item, turn, state):
    state["metadata"].update(
        {
            out: item[key]
            for key, out in (
                ("generation_id", "generation_id"),
                ("model", "confirmed_model"),
                ("provider", "confirmed_provider"),
            )
            if key in item
        }
    )
    allowed = {None, turn["model"]}
    if turn["model"].endswith(":free"):
        allowed.add(turn["model"].removesuffix(":free"))
    if state["metadata"]["confirmed_model"] not in allowed:
        raise ValueError("model_mismatch")


def _handle_packet(item, turn, state):
    kind = item["type"]
    if kind == "metadata":
        _apply_metadata(item, turn, state)
    elif kind == "text":
        return event("content", {"text": item["text"]})
    elif kind == "usage":
        state["usage"] = item["usage"]
        state["actual"] = turn["core"].usage_cost(state["usage"])
    elif kind == "error":
        raise ValueError("upstream_stream_error")
    elif kind == "done":
        state["complete"] = True
    return None


async def _upstream(turn, state):
    decoder = turn["core"].SSEDecoder()
    async with (
        asyncio.timeout(90),
        client_factory(
            timeout=httpx.Timeout(90.0, connect=10.0), follow_redirects=False
        ) as client,
    ):
        async with client.stream(
            "POST",
            runtime.ENDPOINT,
            headers={
                "Authorization": "Bearer " + turn["credential"],
                "Content-Type": "application/json",
            },
            json=turn["payload"],
        ) as response:
            if response.status_code != 200:
                raise HTTPException(502, "openrouter_http_" + str(response.status_code))
            async for data in response.aiter_bytes():
                for item in decoder.feed(data):
                    output = _handle_packet(item, turn, state)
                    if output is not None:
                        yield output
                if state["complete"]:
                    break
    for item in decoder.finish():
        output = _handle_packet(item, turn, state)
        if output is not None:
            yield output
    if not state["complete"]:
        raise ValueError("upstream_stream_incomplete")


def _reserve(turn):
    turn["ledger"] = turn["core"].BudgetLedger(runtime._STATE / "budget.sqlite")
    try:
        turn["execution"] = turn["core"].Execution(
            turn["ledger"],
            turn["id"],
            turn["conversation"],
            turn["estimated"],
            **runtime.limits(),
        )
        turn["execution"].reserve()
    except ValueError as exc:
        raise HTTPException(429, "openrouter_budget_exceeded") from exc
    turn["reservation_created"] = True
    turn["reserved_usd"] = turn["estimated"]


def _done(turn, state):
    usage = {
        k: v
        for k, v in state["usage"].items()
        if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
        and type(v) is int
        and v >= 0
    }
    actual = state["actual"]
    charge = cost(turn, actual, "settled" if actual is not None else "pending")
    return [
        event("cost", charge),
        event(
            "done",
            {
                "usage": usage,
                "usage_source": "upstream" if usage else "unknown",
                **state["metadata"],
                "cost": charge,
            },
        ),
    ]


def _record_receipt(turn, state, settled):
    """Persist only IDs, counters and accounting so cancelled turns remain reconcilable."""
    value = {
        "request_id": turn["id"],
        "runtime_id": turn["runtime_id"],
        "config_hash": turn["config_hash"],
        "quote_hash": quote_hash(turn),
        **state["metadata"],
        "estimated_usd": turn["estimated"],
        "reserved_usd": turn["reserved_usd"],
        "reported_usd": str(state["actual"])
        if settled and state["actual"] is not None
        else None,
        "state": "settled" if settled and state["actual"] is not None else "pending",
    }
    try:
        runtime.save_request_receipt(turn["id"], value)
    except OSError:
        # The durable reservation remains authoritative if an auxiliary receipt cannot be written.
        from venom_core.utils.logger import get_logger

        get_logger(__name__).warning("openrouter_accounting_receipt_unavailable")


async def stream(request, turn):
    """Never retry a paid POST; uncertainty and cancellation retain reservations."""
    state = {
        "actual": None,
        "usage": {},
        "complete": False,
        "metadata": {
            "requested_model": turn["model"],
            "confirmed_model": None,
            "confirmed_provider": None,
            "generation_id": None,
        },
    }
    reserved = settled = False
    try:
        if _ACTIVE.locked():
            raise HTTPException(409, "openrouter_busy")
        async with (
            _ACTIVE,
            runtime_request_guard(
                request_kind="simple_chat", provider="openrouter", model=turn["model"]
            ),
        ):
            runtime.assert_identity(request)
            _reserve(turn)
            reserved = True
            yield event("cost", cost(turn, None, "pending"))
            yield event(
                "start",
                {
                    "request_id": turn["id"],
                    "provider": "openrouter",
                    **state["metadata"],
                    "runtime_id": turn["runtime_id"],
                    "config_hash": turn["config_hash"],
                    "cost": cost(turn, None, "pending"),
                },
            )
            async with aclosing(_upstream(turn, state)) as upstream:
                async for output in upstream:
                    yield output
            turn["execution"].settle(state["actual"])
            settled = True
            for output in _done(turn, state):
                yield output
    except (httpx.HTTPError, ValueError, HTTPException, TimeoutError) as exc:
        code = (
            str(exc.detail)
            if isinstance(exc, HTTPException)
            else "openrouter_request_failed"
        )
        yield event("error", {"code": code, "cost": cost(turn, None, "pending")})
    finally:
        if reserved:
            try:
                if not settled:
                    turn["execution"].pending()
            finally:
                _record_receipt(turn, state, settled)


async def response(request):
    if _ACTIVE.locked():
        raise HTTPException(409, "openrouter_busy")
    turn = prepare(request)
    if request.expected_quote_hash != quote_hash(turn):
        raise HTTPException(409, "openrouter_quote_changed")
    return StreamingResponse(
        stream(request, turn),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Request-Id": turn["id"]},
    )
