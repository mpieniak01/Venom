"""Thin REST adapter: fixed origin, bounded reads, no mutation retries."""

from __future__ import annotations

import base64
import hashlib
import json
import random
import time
from typing import Any

import httpx
from pydantic import SecretStr

from venom_core.infrastructure.providers.vast.models import (
    INSTANCE_FIELDS,
    offer_snapshot,
    project,
)
from venom_core.infrastructure.traffic_control.http_client import (
    TrafficControlledHttpClient,
)

ORIGIN = "https://console.vast.ai"


class VastError(RuntimeError):
    def __init__(self, code: str, status: int | None = None, ambiguous: bool = False):
        super().__init__(code)
        self.code = code
        self.status = status
        self.ambiguous = ambiguous


def ssh_fingerprint(public_key: str) -> str:
    parts = public_key.split()
    if len(parts) < 2:
        raise VastError("vast.invalid_ssh_key")
    try:
        raw = base64.b64decode(parts[1], validate=True)
    except ValueError:
        raise VastError("vast.invalid_ssh_key") from None
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip(
        "="
    )


class VastClient:
    def __init__(self, api_key: SecretStr, transport: Any = None, sleep=time.sleep):
        if not api_key.get_secret_value().strip():
            raise VastError("vast.missing_key")
        self._key = api_key
        self._http = transport or TrafficControlledHttpClient(
            provider="vast", timeout=25
        )
        self._sleep = sleep

    def close(self) -> None:
        self._http.close()

    def _request(
        self, method: str, path: str, *, mutation: bool = False, **kwargs: Any
    ) -> Any:
        # Paths are internal constants, never supplied by provider redirect/CLI.
        if not path.startswith("/api/") or "?" in path or "#" in path:
            raise VastError("vast.invalid_path")
        attempts = 1 if mutation else 3
        for attempt in range(attempts):
            try:
                response = self._http.request(
                    method,
                    ORIGIN + path,
                    headers={"Authorization": "Bearer " + self._key.get_secret_value()},
                    follow_redirects=False,
                    disable_retry=True,
                    raise_for_status=False,
                    **kwargs,
                )
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError):
                # Never include request headers, raw bodies, URLs or exception text.
                raise VastError("vast.transport_error", ambiguous=mutation) from None
            if (
                response.status_code == 429 or response.status_code >= 500
            ) and not mutation:
                if attempt + 1 < attempts:
                    self._sleep(min(2**attempt, 4) + random.uniform(0, 0.25))
                    continue
            if response.status_code >= 300:
                raise VastError(
                    "vast.http_error",
                    response.status_code,
                    ambiguous=mutation
                    and (response.status_code >= 500 or response.status_code < 400),
                )
            try:
                data = response.json()
            except ValueError:
                raise VastError("vast.invalid_response", ambiguous=mutation) from None
            if not isinstance(data, (dict, list)):
                raise VastError("vast.invalid_response", ambiguous=mutation)
            if isinstance(data, dict) and data.get("success") is False:
                raise VastError("vast.provider_rejected", response.status_code)
            return data
        raise VastError("vast.retry_exhausted")

    @staticmethod
    def _object(data: Any) -> dict:
        if not isinstance(data, dict):
            raise VastError("vast.invalid_response")
        return data

    def account(self) -> dict[str, Any]:
        data = self._request("GET", "/api/v0/users/current/")
        return project(self._object(data), ("credit", "balance"))

    def ssh_fingerprints(self) -> list[str]:
        data = self._request("GET", "/api/v0/ssh/")
        if not isinstance(data, list):
            raise VastError("vast.invalid_response")
        return [
            ssh_fingerprint(
                self._object(row).get("public_key") or self._object(row).get("key", "")
            )
            for row in data
            if not self._object(row).get("deleted_at")
        ]

    def offers(self, disk_gb: int, filters: dict[str, Any] | None = None) -> list[dict]:
        data = self._request(
            "POST",
            "/api/v0/bundles/",
            json={
                **(filters or {}),
                "type": "ondemand",
                "rentable": {"eq": True},
                "rented": {"eq": False},
                "allocated_storage": disk_gb,
                "limit": 100,
                "order": [["dph_total", "asc"]],
            },
        )
        rows = self._object(data).get("offers")
        if not isinstance(rows, list):
            raise VastError("vast.invalid_response")
        return [offer_snapshot(self._object(row)) for row in rows]

    def _pages(self, path: str, field: str, params: dict[str, Any]) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        for _ in range(100):
            data = self._request("GET", path, params=params)
            page = self._object(data).get(field)
            if not isinstance(page, list):
                raise VastError("vast.invalid_response")
            rows.extend(self._object(row) for row in page)
            cursor = data.get("next_token")
            if not cursor:
                return rows
            if not isinstance(cursor, str) or cursor in seen:
                raise VastError("vast.pagination_invalid")
            seen.add(cursor)
            params = {**params, "after_token": cursor}
        raise VastError("vast.pagination_limit")

    def instances(self) -> list[dict]:
        return [
            project(row, INSTANCE_FIELDS)
            for row in self._pages("/api/v1/instances/", "instances", {"limit": 25})
        ]

    def instance(self, instance_id: int) -> dict:
        data = self._request("GET", f"/api/v0/instances/{instance_id}/")
        row = self._object(data).get("instances")
        if not isinstance(row, dict) or row.get("id") != instance_id:
            raise VastError("vast.invalid_response")
        return project(row, INSTANCE_FIELDS)

    def create(self, offer_id: int, payload: dict) -> int:
        data = self._request(
            "PUT", f"/api/v0/asks/{offer_id}/", mutation=True, json=payload
        )
        value = data.get("new_contract") if isinstance(data, dict) else None
        if type(value) is not int or value <= 0:
            raise VastError("vast.invalid_response", ambiguous=True)
        return value

    def set_state(self, instance_id: int, state: str) -> None:
        if state not in {"running", "stopped"}:
            raise VastError("vast.invalid_state")
        self._request(
            "PUT",
            f"/api/v0/instances/{instance_id}/",
            mutation=True,
            json={"state": state},
        )

    def destroy(self, instance_id: int) -> None:
        self._request("DELETE", f"/api/v0/instances/{instance_id}/", mutation=True)

    def charges(self, start: int, end: int) -> list[dict]:
        if start >= end:
            raise VastError("vast.invalid_window")
        rows = self._pages(
            "/api/v0/charges/",
            "results",
            {
                "select_filters": json.dumps({"day": {"gte": start, "lte": end}}),
                "format": "table",
                "limit": 500,
            },
        )
        return [
            project(row, ("start", "end", "type", "source", "amount")) for row in rows
        ]

    def volumes(self) -> list[dict]:
        data = self._request("GET", "/api/v0/volumes/")
        rows = data if isinstance(data, list) else data.get("volumes")
        if not isinstance(rows, list):
            raise VastError("vast.invalid_response")
        return [
            project(
                row,
                (
                    "id",
                    "size",
                    "disk_space",
                    "host_id",
                    "status",
                    "storage_cost",
                    "storage_total_cost",
                ),
            )
            for row in rows
        ]
