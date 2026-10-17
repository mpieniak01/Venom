"""Side-effect-free inventory composition; no hardware or cloud probes on GET."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from venom_core.api.schemas.connection_status import ConnectionStatus
from venom_core.api.schemas.integrations import IntegrationEntry, IntegrationResource
from venom_core.services.integration_catalog import core_catalog
from venom_core.services.integration_hooks import apply_module_observations
from venom_core.services.module_observations import module_candidates
from venom_core.services.vast_observation import apply_vast_observation


def _api_id(label: str) -> str:
    return "api:" + hashlib.sha256(label.encode()).hexdigest()[:16]


def _api_entries(connections, settings) -> list[IntegrationEntry]:
    entries = []
    for conn in connections:
        disabled = conn.target_component == "Nodes API" and not getattr(
            settings, "ENABLE_NEXUS", False
        )
        measured = conn.status != ConnectionStatus.UNKNOWN and not disabled
        entries.append(
            IntegrationEntry(
                resource_support="supported"
                if conn.target_component == "Nodes API"
                else "not_applicable",
                id=_api_id(conn.target_component),
                label=conn.target_component,
                scope="internal",
                location="local",
                kind="api",
                configuration="not_required",
                activation="disabled" if disabled else "enabled",
                state="disabled"
                if disabled
                else "connected"
                if conn.status == ConnectionStatus.OK
                else "unavailable"
                if conn.status == ConnectionStatus.DOWN
                else "degraded"
                if measured
                else "unverified",
                connectivity=conn.status if not disabled else ConnectionStatus.UNKNOWN,
                source="service_monitor" if measured else "route_registration",
                observed_at=conn.observed_at if measured else None,
                reason_code="feature_disabled"
                if disabled
                else "service_observation"
                if measured
                else "route_only",
                access=["api"],
            )
        )
    return entries


def _nexus_resources(entries, settings, manager):
    if not getattr(settings, "ENABLE_NEXUS", False):
        return
    item = next((entry for entry in entries if entry.label == "Nodes API"), None)
    if item is None:
        return
    if manager is None:
        item.state, item.reason_code = "unavailable", "manager_unavailable"
        return
    try:
        workers = manager.list_nodes()
        item.resources = [
            IntegrationResource(
                id="nexus:" + node.node_id,
                label=node.node_name[:120],
                kind="worker",
                state="connected" if node.is_online else "offline",
                observed_at=node.last_heartbeat.astimezone(timezone.utc).isoformat(),
            )
            for node in workers[:64]
        ]
        item.resources_complete = len(workers) <= 64
        item.source, item.reason_code = "heartbeat", "registered_workers"
        item.state, item.connectivity = "connected", ConnectionStatus.OK
        _totals(item)
    except Exception:
        item.reason_code, item.state = "source_unavailable", "unavailable"


def _totals(item: IntegrationEntry):
    if item.resources_complete:
        item.resource_count = len(item.resources)
        item.active_resource_count = sum(r.state == "connected" for r in item.resources)


def _local_vast_records(item: IntegrationEntry):
    """Reuse the Vast journal contract without creating directories or calling API."""
    root = Path(".venom_runtime/vast")
    if not root.is_dir():
        return
    from venom_core.services.vast_environments.store import Journal

    journal = Journal(root)
    resources: dict[str, IntegrationResource] = {}
    for path in sorted(root.glob("*.record.json"))[:64]:
        if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            record = journal.record(path.name.removesuffix(".record.json"))
        except Exception:
            continue
        if record.instance_id is None:
            continue
        key = "vast:" + str(record.instance_id)
        current = resources.get(key)
        observed = record.observed_at.isoformat()
        if current is None or (current.observed_at or "") < observed:
            resources[key] = IntegrationResource(
                id=key,
                label=str(record.instance_id),
                kind="instance",
                state="stale",
                observed_at=observed,
            )
    if resources:
        item.resources = list(resources.values())
        item.source, item.reason_code = "local_record", "local_records_only"
        # Journal contents cannot establish the current provider-wide total.


def _module_entries(app: Any, settings) -> list[IntegrationEntry]:
    records = getattr(app.state, "optional_module_diagnostics", None)
    if records is None:
        records = [record for _, record in module_candidates(settings)]
    registry = getattr(app.state, "conversation_providers", None)
    failures = getattr(registry, "failures", {}) or {}
    entries = []
    for record in records:
        state = record["state"]
        item = IntegrationEntry(
            id="module:"
            + record["module_id"]
            + (
                ":" + record.get("entry_id", "")
                if record["reason_code"] == "duplicate_module"
                else ""
            ),
            label=record["display_name"],
            scope="internal",
            location="local",
            kind="module",
            configuration="configured",
            activation="enabled"
            if state == "loaded"
            else "disabled"
            if state == "disabled"
            else "unavailable"
            if state == "unavailable"
            else "unknown",
            state="available" if state == "loaded" else state,
            source="module_activation",
            observed_at=record["observed_at"],
            reason_code=record["reason_code"],
            access=["api"] if state == "loaded" else [],
            # A registered backend does not establish frontend activation.
            panel_path=record.get("nav_path") if state == "loaded" else None,
        )
        error = record.get("conversation_error") or failures.get(record["module_id"])
        if error:
            item.reason_code, item.state = error, "degraded"
        elif state == "loaded":
            item.reason_code = "observation_provider_absent"
        entries.append(item)
    return entries


async def integration_overview(
    app, response, settings, node_manager=None
) -> list[IntegrationEntry]:
    entries = _api_entries(response.internal_connections, settings)
    _nexus_resources(entries, settings, node_manager)
    catalog = core_catalog(settings)
    by_label = {conn.target_component: conn for conn in response.external_connections}
    for item in catalog:
        conn = by_label.get(item.label)
        if (
            conn is not None
            and conn.status != ConnectionStatus.UNKNOWN
            and item.activation == "enabled"
        ):
            item.connectivity, item.source = conn.status, "service_monitor"
            item.observed_at = conn.observed_at
            item.state = (
                "connected"
                if conn.status == ConnectionStatus.OK
                else "unavailable"
                if conn.status == ConnectionStatus.DOWN
                else "degraded"
            )
            item.reason_code = "service_observation"
        if item.id == "core:vast":
            try:
                _local_vast_records(item)
                apply_vast_observation(app, item, settings)
            except (OSError, ValueError):
                item.reason_code = "source_unavailable"
    local = next(
        (
            conn
            for conn in response.external_connections
            if conn.target_component.startswith("Local LLM")
        ),
        None,
    )
    if local:
        entries.append(
            IntegrationEntry(
                id="core:local-runtime",
                label=local.target_component,
                scope="internal",
                location="local",
                kind="runtime",
                state="configured",
                configuration="configured",
                activation="enabled",
                connectivity=local.status,
                panel_path="/models",
                access=["panel", "api"],
                capabilities=["model_inference"],
                reason_code="runtime_configuration",
            )
        )
    entries.extend(catalog)
    entries.extend(_module_entries(app, settings))
    await apply_module_observations(app, entries)
    for item in entries:
        if item.source != "service_monitor" or not item.observed_at:
            continue
        try:
            observed = datetime.fromisoformat(item.observed_at.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - observed).total_seconds()
            if age > 60 or age < -5:
                item.state, item.reason_code = "stale", "observation_stale"
                item.connectivity = ConnectionStatus.UNKNOWN
        except (TypeError, ValueError):
            item.observed_at = None
    return entries
