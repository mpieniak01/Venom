"""Explicit OpenRouter test zero: authentication, cheapest fixed endpoint, one reply.

Default mode reads metadata only. --live requires an explicit USD cap; no retries,
application configuration changes, secret persistence or automatic paid fallback.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx

BASE = "https://openrouter.ai/api/v1"
MARKER = "VENOM_TEST_ZERO_OK"
PROMPT = "Reply with only this exact text: " + MARKER
OUTPUT = 128


class TestZeroError(ValueError):
    pass


def get_json(client, path):
    response = client.get(BASE + path)
    if response.status_code != 200:
        raise TestZeroError("metadata_http_" + str(response.status_code))
    value = response.json()
    if not isinstance(value, dict) or "data" not in value:
        raise TestZeroError("metadata_invalid")
    return value["data"]


def free_tariff(row):
    """An explicit catalog :free entry supplies a documented zero-cost contract."""
    prices = dict(row.get("pricing", {}))
    if str(row.get("model_id", row.get("id", ""))).endswith(":free"):
        if prices.get("prompt") == "0" and prices.get("completion") == "0":
            prices.setdefault("request", "0")
    return prices


def ranked_models(rows, core, cap):
    candidates = []
    for row in rows:
        try:
            model = row["id"]
            architecture = row["architecture"]
            if architecture.get("input_modalities") != ["text"] or architecture.get(
                "output_modalities"
            ) != ["text"]:
                continue
            if (
                model.startswith("openrouter/")
                or model.endswith("-latest")
                or model.rsplit("/", 1)[-1] in {"auto", "latest"}
            ):
                continue
            prices = core.strict_prices(free_tariff(row))
            amount = prices.estimate(len(PROMPT.encode()) + 512, OUTPUT)
            if amount <= cap and {"max_tokens", "temperature"} <= set(
                row.get("supported_parameters", [])
            ):
                candidates.append((amount, model))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(candidates)


def choose_endpoint(client, core, ranked, cap):
    if not ranked:
        raise TestZeroError("no_model_within_budget")
    # One model is selected deterministically. No generation fallback is attempted.
    _, model = ranked[0]
    data = get_json(client, "/models/" + quote(model, safe="/:") + "/endpoints")
    options = []
    for row in data.get("endpoints", []):
        try:
            if row.get("status") != 0 or not {"max_tokens", "temperature"} <= set(
                row.get("supported_parameters", [])
            ):
                continue
            prices = core.strict_prices(free_tariff(row))
            amount = prices.estimate(len(PROMPT.encode()) + 512, OUTPUT)
            provider = row.get("tag") or row.get("provider_name")
            if amount <= cap and isinstance(provider, str) and provider:
                options.append((amount, provider, prices))
        except (TypeError, ValueError):
            continue
    if not options:
        raise TestZeroError("no_endpoint_within_budget")
    amount, provider, prices = min(options, key=lambda x: (x[0], x[1]))
    return {
        "model": model,
        "provider": provider,
        "estimate": amount,
        "prices": prices,
        "reasoning_disabled": "reasoning"
        in next(
            x
            for x in data["endpoints"]
            if (x.get("tag") or x.get("provider_name")) == provider
        ).get("supported_parameters", []),
    }


def generation_payload(core, candidate):
    spec = core.ModelSpec(
        candidate["model"], candidate["prices"], 8192, OUTPUT, candidate["provider"]
    )
    request = core.ChatRequest(
        model=spec,
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=OUTPUT,
        temperature=0,
        request_id=uuid4().hex,
    )
    payload = core.build_chat_payload(request)
    payload["provider"] = {
        "order": [candidate["provider"]],
        "allow_fallbacks": False,
        "require_parameters": True,
        "max_price": {"prompt": 0, "completion": 0},
    }
    if candidate["reasoning_disabled"]:
        payload["reasoning"] = {"enabled": False}
    return payload


async def generate(
    core, key, candidate, client_factory=httpx.AsyncClient, payload=None
):
    payload = payload if payload is not None else generation_payload(core, candidate)
    state = {
        "text": "",
        "done": False,
        "usage": {},
        "generation_id": None,
        "confirmed_model": None,
        "confirmed_provider": None,
    }
    decoder = core.SSEDecoder()
    async with (
        asyncio.timeout(60),
        client_factory(timeout=30, follow_redirects=False) as client,
    ):
        async with client.stream(
            "POST",
            BASE + "/chat/completions",
            headers={"Authorization": "Bearer " + key},
            json=payload,
        ) as response:
            if response.status_code != 200:
                raise TestZeroError("generation_http_" + str(response.status_code))
            async for raw in response.aiter_bytes():
                apply_events(decoder.feed(raw), state)
                if state["done"]:
                    break
    apply_events(decoder.finish(), state)
    if not state["done"] or not state["text"].strip():
        raise TestZeroError("no_completed_text_answer")
    if MARKER not in state["text"]:
        raise TestZeroError("answer_marker_missing")
    allowed = {candidate["model"], candidate["model"].removesuffix(":free")}
    if state["confirmed_model"] not in allowed:
        raise TestZeroError("model_identity_mismatch")
    actual = core.usage_cost(state["usage"])
    if actual is not None and actual > candidate["estimate"]:
        raise TestZeroError("reported_cost_exceeds_reservation")
    return {
        "completed": True,
        "answered": True,
        "marker_matched": True,
        "generation_id": state["generation_id"],
        "confirmed_model": state["confirmed_model"],
        "confirmed_provider": state["confirmed_provider"],
        "reported_usd": str(actual) if actual is not None else None,
        "accounting": "settled" if actual is not None else "pending",
    }


def apply_events(items, state):
    """Apply normalized events in order before deciding whether the socket is complete."""
    for item in items:
        apply_event(item, state)


def apply_event(item, state):
    kind = item["type"]
    if kind == "error":
        raise TestZeroError("stream_error")
    if kind == "text":
        state["text"] += item["text"]
        if len(state["text"]) > 4096:
            raise TestZeroError("response_too_large")
    elif kind == "done":
        state["done"] = True
    elif kind == "usage":
        state["usage"] = item["usage"]
    elif kind == "metadata":
        for source, target in [
            ("generation_id", "generation_id"),
            ("model", "confirmed_model"),
            ("provider", "confirmed_provider"),
        ]:
            if source in item:
                state[target] = item[source]


def run(
    key,
    core,
    *,
    live=False,
    max_cost=Decimal("0"),
    client_factory=httpx.Client,
    async_factory=httpx.AsyncClient,
):
    if not key or not max_cost.is_finite() or max_cost != 0:
        raise TestZeroError("credentials_or_budget_missing")
    with client_factory(
        timeout=20, follow_redirects=False, headers={"Authorization": "Bearer " + key}
    ) as client:
        key_status = get_json(client, "/key")
        if not isinstance(key_status, dict):
            raise TestZeroError("authentication_invalid")
        rows = get_json(client, "/models")
        if not isinstance(rows, list):
            raise TestZeroError("catalog_invalid")
        ranked = ranked_models(rows, core, max_cost)
        candidate = choose_endpoint(client, core, ranked, max_cost)
    report = {
        "scope": "provider_connection_and_shared_core_not_cockpit",
        "authenticated": True,
        "models_visible": len(rows),
        "selected_model": candidate["model"],
        "provider_endpoint": candidate["provider"],
        "estimated_usd": str(candidate["estimate"]),
        "maximum_usd": str(max_cost),
        "pricing_checked_at": datetime.now(timezone.utc).isoformat(),
        "generation_requests": 0,
        "response_confirmed": False,
        "status": "preflight_passed",
    }
    if live:
        try:
            payload = generation_payload(core, candidate)
        except ValueError:
            return {**report, "status": "failed", "reason": "local_request_invalid"}
        report["generation_requests"] = 1
        try:
            report.update(
                asyncio.run(generate(core, key, candidate, async_factory, payload))
            )
        except TestZeroError as exc:
            return {**report, "status": "failed", "reason": str(exc)}
        report["response_confirmed"] = True
        report["status"] = "passed"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-cost-usd", type=Decimal, default=Decimal("0"))
    parser.add_argument("--key-stdin", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise TestZeroError("new_output_path_required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    key = (
        sys.stdin.read(4097).strip()
        if args.key_stdin
        else os.environ.get("OPENROUTER_API_KEY", "")
    )
    try:
        core = importlib.import_module("agent_execution_core")
        report = run(key, core, live=args.live, max_cost=args.max_cost_usd)
    except TestZeroError as exc:
        report = {"status": "failed", "response_confirmed": False, "reason": str(exc)}
    except (ValueError, httpx.HTTPError, TimeoutError, ImportError):
        report = {
            "status": "failed",
            "response_confirmed": False,
            "reason": "test_zero_failed",
            "generation_requests": "unknown_if_dispatched",
        }
    with args.output.open("x") as target:
        json.dump(report, target, indent=2)
    print(json.dumps(report))
    return 0 if report["status"] in {"passed", "preflight_passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
