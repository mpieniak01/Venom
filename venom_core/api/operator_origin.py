"""Shared same-origin guard for local operator HTTP actions."""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request


def require_operator_origin(request: Request, code: str) -> None:
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (
        origin and urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise HTTPException(403, code)
