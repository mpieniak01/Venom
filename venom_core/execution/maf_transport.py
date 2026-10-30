"""Bind real SDK HTTP rejections to the admission operation that sent them.

Hooks observe headers before SDK exception wrapping. Caller-supplied status
codes, old responses and an accepted/unfinished stream never prove rejection.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, Iterator, cast

import httpx
from fastapi import HTTPException
from openai import AsyncOpenAI

from venom_core.services.runtime_admission import (
    REJECTED_BEFORE_WORK_HTTP_STATUSES,
    RuntimeOperationRejection,
)


@dataclass
class _RequestEvidence:
    before_request: Callable[[], None] | None = None
    policy_denial: _MafPolicyDenial | None = None
    request: httpx.Request | None = None
    response: httpx.Response | None = None
    rejection: RuntimeOperationRejection | None = None
    uncertain_attempt: bool = False


def _completed_response(response: httpx.Response | None) -> bool:
    if (
        response is None
        or response.status_code >= 400
        or not response.is_stream_consumed
    ):
        return False
    stream = response.extensions.get("venom_maf_stream")
    if isinstance(stream, _CompletionStream):
        return stream.completed
    try:
        payload = response.json()
    except (ValueError, httpx.ResponseNotRead):
        return False
    choices = payload.get("choices") if isinstance(payload, dict) else None
    return (
        isinstance(choices, list)
        and bool(choices)
        and all(
            isinstance(choice, dict)
            and choice.get("finish_reason")
            in {"stop", "length", "tool_calls", "content_filter", "function_call"}
            for choice in choices
        )
    )


class _CompletionStream(httpx.AsyncByteStream):
    """Require an explicit end marker; TCP EOF does not establish completion."""

    def __init__(self, source: httpx.AsyncByteStream) -> None:
        self.source = source
        self.completed = False
        self.pending = b""

    def observe(self, chunk: bytes) -> None:
        self.pending += chunk
        while b"\n" in self.pending:
            line, self.pending = self.pending.split(b"\n", 1)
            if line.startswith(b"data:") and line[5:].strip() == b"[DONE]":
                self.completed = True
        # Bound evidence storage independently of model output length.
        self.pending = self.pending[-128:]

    async def __aiter__(self):
        async for chunk in self.source:
            self.observe(chunk)
            yield chunk
        self.observe(b"\n")
        if not self.completed:
            raise RuntimeError("upstream_stream_incomplete")

    async def aclose(self) -> None:
        await self.source.aclose()


_EVIDENCE: ContextVar[_RequestEvidence | None] = ContextVar(
    "maf_http_evidence", default=None
)


class _MafHttpRejection(RuntimeError, RuntimeOperationRejection):
    def __init__(self, error: Exception, proof: RuntimeOperationRejection) -> None:
        RuntimeError.__init__(self, str(error))
        self._proof = proof

    def confirms_rejection(self, operation: str | None) -> bool:
        return self._proof.confirms_rejection(operation)


def _transport_quiescent(evidence: _RequestEvidence) -> bool:
    if evidence.uncertain_attempt:
        return False
    if evidence.request is None or evidence.rejection is not None:
        return True
    return _completed_response(evidence.response)


class _MafPolicyDenial(HTTPException, RuntimeOperationRejection):
    """A local transport denial cannot hide earlier unfinished provider work."""

    def __init__(self, error: HTTPException, *, quiescent: bool) -> None:
        HTTPException.__init__(self, error.status_code, error.detail, error.headers)
        self._proof = RuntimeOperationRejection() if quiescent else None

    def confirms_rejection(self, operation: str | None) -> bool:
        return self._proof is not None and self._proof.confirms_rejection(operation)


async def _observe_request(request: httpx.Request) -> None:
    # AsyncClient awaits event hooks, even when header bookkeeping needs no I/O.
    # https://www.python-httpx.org/advanced/event-hooks/
    evidence = _EVIDENCE.get()
    if evidence is not None:
        if evidence.before_request is not None:
            try:
                evidence.before_request()
            except HTTPException as error:
                quiescent = _transport_quiescent(evidence)
                evidence.policy_denial = _MafPolicyDenial(error, quiescent=quiescent)
                raise evidence.policy_denial from error
        evidence.policy_denial = None
        # A later rejection cannot erase an earlier timeout or accepted work.
        if evidence.request is not None and evidence.rejection is None:
            evidence.uncertain_attempt |= not _completed_response(evidence.response)
        evidence.rejection = None
        evidence.response = None
        # SSE evidence is inspected before HTTPX decoding. Completion endpoints
        # must return identity encoding rather than opaque compressed bytes.
        request.headers["accept-encoding"] = "identity"
        evidence.request = (
            request
            if request.method == "POST"
            and request.url.path.rstrip("/").endswith("/chat/completions")
            else None
        )


async def _observe_response(response: httpx.Response) -> None:
    # HTTPX requires an async hook here; response observation itself is synchronous.
    evidence = _EVIDENCE.get()
    if evidence is None or evidence.request is not response.request:
        return
    evidence.response = response
    if response.status_code in REJECTED_BEFORE_WORK_HTTP_STATUSES:
        evidence.rejection = RuntimeOperationRejection()
    elif response.is_success and "text/event-stream" in response.headers.get(
        "content-type", ""
    ):
        stream = _CompletionStream(cast(httpx.AsyncByteStream, response.stream))
        response.extensions["venom_maf_stream"] = stream
        if response.is_stream_consumed:
            stream.observe(response.content + b"\n")
        else:
            response.stream = stream


def install_maf_transport_observer(client: AsyncOpenAI) -> None:
    # This is the single pinned-SDK adapter seam; keep injected HTTP transports
    # (including MockTransport) and caller hooks intact. Register once per client.
    hooks = client._client.event_hooks
    for name, observer in (
        ("request", _observe_request),
        ("response", _observe_response),
    ):
        registered = hooks.setdefault(name, [])
        if observer not in registered:
            registered.append(observer)


@contextmanager
def maf_transport_scope(
    before_request: Callable[[], None] | None = None,
) -> Iterator[None]:
    evidence = _RequestEvidence(before_request=before_request)
    context = _EVIDENCE.set(evidence)
    try:
        yield
        stream = (
            evidence.response.extensions.get("venom_maf_stream")
            if evidence.response is not None
            else None
        )
        if isinstance(stream, _CompletionStream) and not stream.completed:
            raise RuntimeError("upstream_stream_incomplete")
    except Exception as error:
        if evidence.policy_denial is not None:
            if error is evidence.policy_denial:
                raise
            raise evidence.policy_denial from error
        if evidence.rejection is not None and not evidence.uncertain_attempt:
            raise _MafHttpRejection(error, evidence.rejection) from error
        raise
    finally:
        _EVIDENCE.reset(context)
