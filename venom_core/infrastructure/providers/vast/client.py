"""Thin REST adapter: fixed origin, bounded reads, no mutation retries."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any

import httpx
from pydantic import SecretStr

from venom_core.infrastructure.providers.vast.models import (
    INSTANCE_FIELDS,
    amount,
    offer_snapshot,
    project,
)
from venom_core.infrastructure.traffic_control.http_client import (
    TrafficControlledHttpClient,
)

ORIGIN = "https://console.vast.ai"
INVALID_RESPONSE = "vast.invalid_response"


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

    def _send(self, method: str, path: str, mutation: bool, **kwargs: Any):
        try:
            return self._http.request(
                method,
                ORIGIN + path,
                headers={"Authorization": "Bearer " + self._key.get_secret_value()},
                follow_redirects=False,
                disable_retry=True,
                raise_for_status=False,
                **kwargs,
            )
        except (httpx.HTTPError, RuntimeError, ValueError, TypeError):
            raise VastError("vast.transport_error", ambiguous=mutation) from None

    @staticmethod
    def _decode(response, path: str, mutation: bool) -> Any:
        if response.status_code >= 300:
            ambiguous = mutation and (
                response.status_code >= 500 or response.status_code < 400
            )
            raise VastError(
                "vast.http_error", response.status_code, ambiguous=ambiguous
            )
        try:
            data = response.json()
        except ValueError:
            raise VastError(INVALID_RESPONSE, ambiguous=mutation) from None
        if not isinstance(data, (dict, list)):
            raise VastError(INVALID_RESPONSE, ambiguous=mutation)
        if isinstance(data, dict) and data.get("success") is False:
            if (
                path == "/api/v0/charges/"
                and data.get("msg") == "Host users do not have instance charges"
            ):
                raise VastError(
                    "vast.charges_unavailable_for_host", response.status_code
                )
            raise VastError("vast.provider_rejected", response.status_code)
        return data

    def _request(
        self, method: str, path: str, *, mutation: bool = False, **kwargs: Any
    ) -> Any:
        # Internal paths only. Never follow redirects with the provider credential.
        if not path.startswith("/api/") or "?" in path or "#" in path:
            raise VastError("vast.invalid_path")
        attempts = 1 if mutation else 3
        for attempt in range(attempts):
            response = self._send(method, path, mutation, **kwargs)
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and not mutation and attempt + 1 < attempts:
                self._sleep(min(2**attempt, 4) + secrets.randbelow(250) / 1000)
                continue
            return self._decode(response, path, mutation)
        raise VastError("vast.retry_exhausted")

    @staticmethod
    def _object(data: Any) -> dict:
        if not isinstance(data, dict):
            raise VastError(INVALID_RESPONSE)
        return data

    def account(self) -> dict[str, Any]:
        data = self._request("GET", "/api/v0/users/current/")
        return project(self._object(data), ("credit", "balance"))

    def ssh_fingerprints(self) -> list[str]:
        data = self._request("GET", "/api/v0/ssh/")
        if not isinstance(data, list):
            raise VastError(INVALID_RESPONSE)
        fingerprints = []
        for row in data:
            if not isinstance(row, dict) or row.get("deleted_at"):
                continue
            key = row.get("public_key") or row.get("key")
            if not isinstance(key, str):
                continue
            try:
                fingerprints.append(ssh_fingerprint(key))
            except VastError:
                continue
        return fingerprints

    def templates(
        self, template_hash: str | None = None, recommended: bool = False
    ) -> list[dict]:
        from venom_core.infrastructure.providers.vast.templates import (
            TEMPLATE_COLUMNS,
            template_snapshot,
        )

        filters: dict[str, Any] = {"use_ssh": {"eq": True}}
        if template_hash:
            filters["hash_id"] = {"eq": template_hash}
        if recommended:
            filters["recommended"] = {"eq": True}
        data = self._object(
            self._request(
                "GET",
                "/api/v0/template/",
                params={
                    "select_filters": json.dumps(filters),
                    "select_cols": json.dumps(TEMPLATE_COLUMNS),
                },
            )
        )
        rows = data.get("templates")
        if not isinstance(rows, list):
            raise VastError(INVALID_RESPONSE)
        return [template_snapshot(self._object(row)) for row in rows]

    def benchmarks(self, machine_id: int) -> dict:
        if machine_id <= 0:
            raise VastError("vast.invalid_machine")
        fields = (
            "id",
            "contract_id",
            "machine_id",
            "model",
            "name",
            "image",
            "num_gpus",
            "score",
            "last_update",
        )
        data = self._request(
            "GET",
            "/api/v0/benchmarks/",
            params={
                "select_filters": json.dumps({"machine_id": {"eq": machine_id}}),
                "select_cols": json.dumps(fields),
            },
        )
        rows = data if isinstance(data, list) else self._object(data).get("benchmarks")
        if not isinstance(rows, list):
            raise VastError(INVALID_RESPONSE)
        selected = [
            project(self._object(row), fields)
            for row in rows
            if self._object(row).get("machine_id") == machine_id
        ]
        return {
            "source": "provider_history",
            "score_unit": "unknown",
            "results": selected,
            "status": "available" if selected else "not_available",
            "score_status": "available"
            if any(amount(row.get("score")) is not None for row in selected)
            else "not_available",
        }

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
                "order": (filters or {}).get("order", [["dph_total", "asc"]]),
            },
        )
        rows = self._object(data).get("offers")
        if not isinstance(rows, list):
            raise VastError(INVALID_RESPONSE)
        return [offer_snapshot(self._object(row)) for row in rows]

    def _pages(self, path: str, field: str, params: dict[str, Any]) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        for _ in range(100):
            data = self._request("GET", path, params=params)
            page = self._object(data).get(field)
            if not isinstance(page, list):
                raise VastError(INVALID_RESPONSE)
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
            raise VastError(INVALID_RESPONSE)
        return project(row, INSTANCE_FIELDS)

    def create(self, offer_id: int, payload: dict) -> int:
        data = self._request(
            "PUT", f"/api/v0/asks/{offer_id}/", mutation=True, json=payload
        )
        value = data.get("new_contract") if isinstance(data, dict) else None
        if type(value) is not int or value <= 0:
            raise VastError(INVALID_RESPONSE, ambiguous=True)
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
            raise VastError(INVALID_RESPONSE)
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
