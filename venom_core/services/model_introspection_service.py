"""Utilities for building a compact model-introspection snapshot."""

from __future__ import annotations

import importlib.metadata
import importlib.util
from typing import Any, Optional

from venom_core.services.model_introspection_probe_service import (
    build_probe_health_payload,
)
from venom_core.utils.llm_runtime import detect_runtime_drift, get_active_llm_runtime

_INTROSPECTION_PACKAGES: tuple[tuple[str, str], ...] = (
    ("transformer_lens", "transformer-lens"),
    ("captum", "captum"),
    ("circuitsvis", "circuitsvis"),
    ("torch", "torch"),
    ("transformers", "transformers"),
    ("onnxruntime", "onnxruntime-gpu"),
    ("sentence_transformers", "sentence-transformers"),
    ("graphrag", "graphrag"),
)


def _build_graph_snapshot(
    *,
    runtime: dict[str, Any],
    runtime_drift: dict[str, Any],
    available_packages: list[str],
    missing_packages: list[str],
    model_manager: dict[str, Any],
) -> dict[str, Any]:
    package_nodes = [
        {
            "id": f"package:{package_name}",
            "label": package_name,
            "kind": "package",
            "status": "available" if package_name in available_packages else "missing",
        }
        for package_name in sorted({*available_packages, *missing_packages})
    ]
    nodes = [
        {
            "id": "runtime",
            "label": runtime["label"],
            "kind": "runtime",
            "status": runtime_drift["active_server"],
        },
        {
            "id": "model",
            "label": runtime["model"],
            "kind": "model",
            "status": "active",
        },
        {
            "id": "analysis",
            "label": "live analysis",
            "kind": "analysis",
            "status": "ready" if model_manager["available"] else "read-only",
        },
        {
            "id": "manager",
            "label": "ModelManager",
            "kind": "manager",
            "status": "connected" if model_manager["available"] else "offline",
        },
        {
            "id": "brain",
            "label": "/brain",
            "kind": "reuse",
            "status": "available",
        },
        {
            "id": "diagnostics",
            "label": "runtime diagnostics",
            "kind": "reuse",
            "status": "available",
        },
        *package_nodes,
    ]
    edges = [
        {"from": "runtime", "to": "model", "label": "active model"},
        {"from": "runtime", "to": "analysis", "label": "prompt execution"},
        {"from": "runtime", "to": "manager", "label": "usage metrics"},
        {"from": "runtime", "to": "brain", "label": "reuse"},
        {"from": "runtime", "to": "diagnostics", "label": "reuse"},
        {"from": "model", "to": "package:graphrag", "label": "optional"},
        {"from": "model", "to": "package:captum", "label": "optional"},
        {"from": "model", "to": "package:transformer-lens", "label": "optional"},
    ]
    for package_name in sorted({*available_packages, *missing_packages}):
        edges.append(
            {
                "from": "analysis",
                "to": f"package:{package_name}",
                "label": "uses" if package_name in available_packages else "missing",
            }
        )
    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "available_packages": len(available_packages),
            "missing_packages": len(missing_packages),
            "drift_issues": len(runtime_drift["issues"]),
        },
    }


def _probe_package(module_name: str, package_name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    available = spec is not None
    version: Optional[str] = None
    if available:
        try:
            version = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            version = None
        except Exception:
            version = None
    return {
        "module": module_name,
        "package": package_name,
        "available": available,
        "version": version,
    }


async def _collect_model_manager_usage(model_manager: Any) -> dict[str, Any]:
    if model_manager is None:
        return {"available": False, "usage_metrics": None, "error": None}
    try:
        usage_metrics = await model_manager.get_usage_metrics()
        return {"available": True, "usage_metrics": usage_metrics, "error": None}
    except Exception as exc:
        return {
            "available": True,
            "usage_metrics": None,
            "error": str(exc),
        }


async def build_model_introspection_snapshot(
    *, model_manager: Any = None, settings: Any = None
) -> dict[str, Any]:
    """Build a read-only snapshot for model visualization and diagnostics."""

    active_runtime = get_active_llm_runtime(settings)
    runtime = active_runtime.to_payload()
    runtime_drift = detect_runtime_drift(settings)
    packages = {
        package_name: _probe_package(module_name, package_name)
        for module_name, package_name in _INTROSPECTION_PACKAGES
    }

    model_manager_snapshot = await _collect_model_manager_usage(model_manager)
    available_packages = sorted(
        package_name for package_name, probe in packages.items() if probe["available"]
    )
    missing_packages = sorted(
        package_name
        for package_name, probe in packages.items()
        if not probe["available"]
    )

    probe_health = build_probe_health_payload(active_runtime)

    runtime_probe_node = {
        "id": "probe",
        "label": f"probe:{probe_health['status']}",
        "kind": "probe",
        "status": "ready" if probe_health["healthy"] else "degraded",
    }

    graph_snapshot = _build_graph_snapshot(
        runtime=runtime,
        runtime_drift=runtime_drift,
        available_packages=available_packages,
        missing_packages=missing_packages,
        model_manager=model_manager_snapshot,
    )
    graph_snapshot["nodes"].append(runtime_probe_node)
    graph_snapshot["edges"].append(
        {"from": "analysis", "to": "probe", "label": "introspection probe"}
    )
    graph_snapshot["summary"]["nodes"] = len(graph_snapshot["nodes"])
    graph_snapshot["summary"]["edges"] = len(graph_snapshot["edges"])

    return {
        "runtime": runtime,
        "runtime_drift": runtime_drift,
        "packages": packages,
        "available_packages": available_packages,
        "missing_packages": missing_packages,
        "model_manager": model_manager_snapshot,
        "probe": probe_health,
        "graph": graph_snapshot,
        "reuse": {
            "brain": {
                "path": "/brain",
                "available": True,
                "purpose": "existing rag and graph surface",
            },
            "diagnostics": [
                {"id": "217da", "purpose": "runtime lifecycle diagnostics"},
                {"id": "217db", "purpose": "runtime pipeline diagnostics"},
            ],
        },
        "summary": {
            "active_model": runtime["model"],
            "provider": runtime["provider"],
            "runtime_label": runtime["label"],
            "introspection_ready": True,
        },
    }
