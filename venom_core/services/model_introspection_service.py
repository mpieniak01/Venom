"""Utilities for building a compact model-introspection snapshot."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import anyio

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
_RUNTIME_VLLM_MANIFEST_NAME = "venom_runtime_vllm.json"
_NATIVE_RUNTIME_CONFIG_SOURCE = "native runtime config"


def _resolve_snapshot_introspection_level(
    *,
    runtime_provider: str,
    probe_health: dict[str, Any],
) -> str:
    provider = str(runtime_provider or "").strip().lower()
    if provider == "ollama":
        return "lite"
    probe_enabled = bool(probe_health.get("enabled"))
    runtime_supported = bool(probe_health.get("runtime_supported"))
    endpoint_configured = bool(probe_health.get("endpoint_configured"))
    model_whitelisted = bool(probe_health.get("model_whitelisted"))
    healthy = bool(probe_health.get("healthy"))
    if (
        probe_enabled
        and runtime_supported
        and endpoint_configured
        and model_whitelisted
        and healthy
    ):
        return "full"
    return "none"


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


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_model_id(value: Any) -> str:
    model_id = str(value or "").strip().lower()
    return model_id


def _config_matches_runtime_model(
    *,
    runtime_model: str,
    config: dict[str, Any],
    manifest: dict[str, Any],
) -> bool:
    runtime_model_normalized = _normalize_model_id(runtime_model)
    if not runtime_model_normalized:
        return True
    runtime_leaf = runtime_model_normalized.split("/")[-1]
    candidates = [
        _normalize_model_id(config.get("_name_or_path")),
        _normalize_model_id(config.get("model_name")),
        _normalize_model_id(config.get("model_type")),
        _normalize_model_id(manifest.get("base_model")),
        _normalize_model_id(manifest.get("model")),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate_leaf = candidate.split("/")[-1]
        if candidate == runtime_model_normalized or candidate_leaf == runtime_leaf:
            return True
    return False


def _append_native_candidate_if_matching(
    *,
    candidates: list[tuple[float, Path, dict[str, Any], dict[str, Any]]],
    config_path: Path,
    runtime_model: str,
) -> None:
    try:
        config = _read_json_file(config_path)
        runtime_dir = config_path.parent
        manifest_path = runtime_dir / _RUNTIME_VLLM_MANIFEST_NAME
        manifest = _read_json_file(manifest_path)
        if not _config_matches_runtime_model(
            runtime_model=runtime_model,
            config=config,
            manifest=manifest,
        ):
            return
        candidates.append((config_path.stat().st_mtime, config_path, config, manifest))
    except OSError:
        return


def _resolve_runtime_model_store(runtime_model: str) -> str:
    if "/" not in runtime_model:
        return ""
    owner, name = runtime_model.split("/", 1)
    return f"models--{owner}--{name}"


def _select_newest_native_candidate(
    candidates: list[tuple[float, Path, dict[str, Any], dict[str, Any]]],
    source_label: str,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    _, config_path, config, _manifest = max(candidates, key=lambda item: item[0])
    runtime_dir = config_path.parent
    return {
        "config_path": config_path,
        "config": config,
        "manifest_path": runtime_dir / _RUNTIME_VLLM_MANIFEST_NAME,
        "source": source_label,
    }


def _collect_hf_cache_candidates(
    *,
    candidates: list[tuple[float, Path, dict[str, Any], dict[str, Any]]],
    runtime_model: str,
    runtime_model_store: str,
) -> None:
    hf_cache_roots = [
        Path("./models_cache/hf").resolve(),
        Path("./models/cache/huggingface/hub").resolve(),
    ]
    for cache_root in hf_cache_roots:
        if not runtime_model_store:
            continue
        snapshots_root = cache_root / runtime_model_store / "snapshots"
        if not snapshots_root.exists():
            continue
        for config_path in snapshots_root.rglob("config.json"):
            _append_native_candidate_if_matching(
                candidates=candidates,
                config_path=config_path,
                runtime_model=runtime_model,
            )


def _resolve_active_adapter_source(model_manager: Any) -> dict[str, Any] | None:
    active_adapter_info = None
    get_active_adapter_info = getattr(model_manager, "get_active_adapter_info", None)
    if callable(get_active_adapter_info):
        try:
            active_adapter_info = get_active_adapter_info()
        except Exception:
            active_adapter_info = None

    active_adapter_path = str(
        (active_adapter_info or {}).get("adapter_path") or ""
    ).strip()
    if not active_adapter_path:
        return None

    adapter_path = Path(active_adapter_path).expanduser().resolve()
    runtime_config = adapter_path.parent / "runtime_vllm" / "config.json"
    if not runtime_config.exists():
        return None
    return {
        "config_path": runtime_config,
        "config": _read_json_file(runtime_config),
        "manifest_path": adapter_path.parent
        / "runtime_vllm"
        / _RUNTIME_VLLM_MANIFEST_NAME,
        "source": _NATIVE_RUNTIME_CONFIG_SOURCE,
    }


def _resolve_native_search_roots(model_manager: Any) -> list[Path]:
    models_dir = getattr(model_manager, "models_dir", None)
    search_roots: list[Path] = []
    if isinstance(models_dir, Path):
        search_roots.append(models_dir.resolve())
    default_models_dir = Path("./data/models").resolve()
    if default_models_dir not in search_roots:
        search_roots.append(default_models_dir)
    return search_roots


def _collect_runtime_vllm_candidates(
    *,
    candidates: list[tuple[float, Path, dict[str, Any], dict[str, Any]]],
    runtime_model: str,
    search_roots: list[Path],
) -> None:
    for root in search_roots:
        if not root.exists():
            continue
        for config_path in root.rglob("runtime_vllm/config.json"):
            _append_native_candidate_if_matching(
                candidates=candidates,
                config_path=config_path,
                runtime_model=runtime_model,
            )


def _resolve_native_architecture_source(
    *,
    runtime: dict[str, Any],
    model_manager: Any,
) -> dict[str, Any] | None:
    candidates: list[tuple[float, Path, dict[str, Any], dict[str, Any]]] = []
    runtime_model = str(runtime.get("model") or "").strip()
    runtime_model_store = _resolve_runtime_model_store(runtime_model)
    _collect_hf_cache_candidates(
        candidates=candidates,
        runtime_model=runtime_model,
        runtime_model_store=runtime_model_store,
    )
    hf_cache_source = _select_newest_native_candidate(
        candidates,
        "native hf cache config",
    )
    if hf_cache_source is not None:
        return hf_cache_source

    adapter_source = _resolve_active_adapter_source(model_manager)
    if adapter_source is not None:
        return adapter_source

    _collect_runtime_vllm_candidates(
        candidates=candidates,
        runtime_model=runtime_model,
        search_roots=_resolve_native_search_roots(model_manager),
    )
    return _select_newest_native_candidate(candidates, _NATIVE_RUNTIME_CONFIG_SOURCE)


def _resolve_native_architecture_section(config: dict[str, Any]) -> dict[str, Any]:
    text_config = config.get("text_config")
    if isinstance(text_config, dict):
        return text_config
    return config


def _resolve_native_layer_count(architecture_section: dict[str, Any]) -> int:
    layer_count = _safe_int(architecture_section.get("num_hidden_layers"), 0)
    if layer_count > 0:
        return layer_count
    return max(1, len(architecture_section.get("layer_types") or []))


def _resolve_native_statuses(
    *,
    missing_packages: list[str],
    model_manager: dict[str, Any],
    probe_health: dict[str, Any],
    reuse: dict[str, Any],
) -> tuple[str, str, str, str]:
    package_pressure = "degraded" if missing_packages else "ready"
    layer_status = "ready" if bool(model_manager.get("available")) else "degraded"
    probe_status = "ready" if bool(probe_health.get("healthy")) else "degraded"
    reuse_status = (
        "ready"
        if bool(reuse.get("brain", {}).get("available"))
        or bool(reuse.get("diagnostics"))
        else "unknown"
    )
    return package_pressure, layer_status, probe_status, reuse_status


def _public_source_path(path: str) -> str:
    path_obj = Path(path)
    parts = path_obj.parts
    if len(parts) >= 2:
        return str(Path(parts[-2]) / parts[-1])
    if parts:
        return parts[-1]
    return "config.json"


def _normalize_layer_types(
    layer_types: list[str] | tuple[str, ...] | None,
    layer_count: int,
) -> list[str]:
    if not layer_types:
        return ["unknown" for _ in range(layer_count)]
    normalized = [str(layer_type or "unknown") for layer_type in layer_types]
    if len(normalized) >= layer_count:
        return normalized[:layer_count]
    fallback = ["unknown" for _ in range(layer_count)]
    for index, value in enumerate(normalized):
        fallback[index] = value
    return fallback


def _build_native_architecture_graph_snapshot(
    *,
    runtime: dict[str, Any],
    missing_packages: list[str],
    model_manager: dict[str, Any],
    probe_health: dict[str, Any],
    reuse: dict[str, Any],
    architecture_source: dict[str, Any],
) -> dict[str, Any]:
    config = architecture_source["config"]
    architecture_section = _resolve_native_architecture_section(config)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    architecture_name = str((config.get("architectures") or [runtime["model"]])[0])
    model_type = str(config.get("model_type") or architecture_name or runtime["model"])
    layer_count = _resolve_native_layer_count(architecture_section)
    layer_types = _normalize_layer_types(
        architecture_section.get("layer_types"),
        layer_count,
    )
    head_count = _safe_int(architecture_section.get("num_attention_heads"), 0)
    kv_head_count = _safe_int(architecture_section.get("num_key_value_heads"), 0)
    hidden_size = _safe_int(architecture_section.get("hidden_size"), 0)
    intermediate_size = _safe_int(architecture_section.get("intermediate_size"), 0)
    head_dim = _safe_int(architecture_section.get("head_dim"), 0)
    sliding_window = _safe_int(architecture_section.get("sliding_window"), 0)
    package_pressure, layer_status, probe_status, reuse_status = (
        _resolve_native_statuses(
            missing_packages=missing_packages,
            model_manager=model_manager,
            probe_health=probe_health,
            reuse=reuse,
        )
    )
    runtime_source = str(
        architecture_source.get("source") or _NATIVE_RUNTIME_CONFIG_SOURCE
    )
    runtime_manifest = _read_json_file(architecture_source["manifest_path"])
    base_model = str(runtime_manifest.get("base_model") or runtime["model"])
    runtime_path = str(architecture_source["config_path"])
    runtime_path_public = _public_source_path(runtime_path)

    nodes: list[dict[str, Any]] = [
        {
            "id": "input",
            "label": "Prompt input",
            "kind": "input",
            "status": "ready",
            "layer_index": 0,
            "role": "input",
            "group": "entry",
            "metadata": {
                "source": runtime_source,
            },
        },
        {
            "id": "embedding",
            "label": "Token embedding",
            "kind": "embedding",
            "status": package_pressure,
            "layer_index": 0,
            "role": "embedding",
            "group": "embedding",
            "metadata": {
                "architecture": architecture_name,
                "model_type": model_type,
                "hidden_size": hidden_size,
                "source_path": runtime_path_public,
            },
        },
    ]
    for index in range(layer_count):
        layer_type = layer_types[index]
        nodes.append(
            {
                "id": f"layer_{index + 1}",
                "label": f"Layer {index + 1} ({layer_type})",
                "kind": "layer",
                "status": layer_status,
                "layer_index": index + 1,
                "role": "layer",
                "group": layer_type,
                "metadata": {
                    "architecture": architecture_name,
                    "model_type": model_type,
                    "layer_type": layer_type,
                    "hidden_size": hidden_size,
                    "intermediate_size": intermediate_size,
                    "attention_heads": head_count,
                    "key_value_heads": kv_head_count,
                    "head_dim": head_dim,
                    "sliding_window": sliding_window,
                    "source_path": runtime_path_public,
                },
            }
        )
    nodes.extend(
        [
            {
                "id": "output",
                "label": "Answer output",
                "kind": "output",
                "status": layer_status,
                "layer_index": layer_count + 1,
                "role": "output",
                "group": "exit",
                "metadata": {
                    "analysis_mode": "native",
                    "source_path": runtime_path_public,
                },
            },
            {
                "id": "mlp",
                "label": "Response synthesis",
                "kind": "mlp",
                "status": layer_status,
                "layer_index": layer_count,
                "role": "mlp",
                "group": "synthesis",
                "metadata": {
                    "architecture": architecture_name,
                    "model_type": model_type,
                    "intermediate_size": intermediate_size,
                    "head_dim": head_dim,
                    "source_path": runtime_path_public,
                },
            },
            {
                "id": "probe",
                "label": "Probe surface",
                "kind": "attention",
                "status": probe_status,
                "layer_index": layer_count,
                "role": "attention",
                "group": "probe",
                "metadata": {
                    "probe_status": probe_health.get("status"),
                    "probe_enabled": bool(probe_health.get("enabled")),
                    "source_path": runtime_path_public,
                },
            },
            {
                "id": "residual",
                "label": "Residual merge",
                "kind": "residual",
                "status": reuse_status,
                "layer_index": layer_count,
                "role": "residual",
                "group": "residual",
                "metadata": {
                    "brain_available": bool(reuse.get("brain", {}).get("available")),
                    "diagnostic_paths": len(reuse.get("diagnostics") or []),
                    "source_path": runtime_path_public,
                },
            },
        ]
    )

    edges: list[dict[str, Any]] = [
        {
            "from": "input",
            "to": "embedding",
            "label": "tokenize",
            "kind": "flow",
            "direction": "forward",
            "weight": 1.0,
        },
        {
            "from": "embedding",
            "to": "layer_1",
            "label": "enter stack",
            "kind": "flow",
            "direction": "forward",
            "weight": 1.0,
        },
    ]
    for index in range(1, layer_count):
        edges.append(
            {
                "from": f"layer_{index}",
                "to": f"layer_{index + 1}",
                "label": layer_types[index],
                "kind": layer_types[index],
                "direction": "forward",
                "weight": 1.0,
            }
        )
    edges.extend(
        [
            {
                "from": f"layer_{layer_count}",
                "to": "probe",
                "label": "probe path",
                "kind": "probe",
                "direction": "forward",
                "weight": 0.75,
            },
            {
                "from": f"layer_{layer_count}",
                "to": "mlp",
                "label": "synthesis path",
                "kind": "mlp",
                "direction": "forward",
                "weight": 0.9,
            },
            {
                "from": "mlp",
                "to": "residual",
                "label": "residual path",
                "kind": "residual",
                "direction": "forward",
                "weight": 0.85,
            },
            {
                "from": "probe",
                "to": "residual",
                "label": "merge",
                "kind": "merge",
                "direction": "forward",
                "weight": 0.7,
            },
            {
                "from": "residual",
                "to": "output",
                "label": "decode",
                "kind": "flow",
                "direction": "forward",
                "weight": 1.0,
            },
        ]
    )

    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "layer_count": layer_count,
            "block_count": layer_count,
            "hidden_size": hidden_size,
            "attention_heads": head_count,
        },
        "meta": {
            "runtime": runtime["label"],
            "model": runtime["model"],
            "provider": runtime["provider"],
            "generated_at": generated_at,
            "fidelity": "native",
            "source": runtime_source,
            "source_path": runtime_path_public,
            "base_model": base_model,
        },
    }


def _build_architecture_graph_snapshot(
    *,
    runtime: dict[str, Any],
    runtime_drift: dict[str, Any],
    available_packages: list[str],
    missing_packages: list[str],
    model_manager: dict[str, Any],
    probe_health: dict[str, Any],
    reuse: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    has_model_manager = bool(model_manager.get("available"))
    has_probe = bool(probe_health.get("healthy"))
    has_reuse_surface = bool(reuse.get("brain", {}).get("available")) or bool(
        reuse.get("diagnostics")
    )
    package_count = len(available_packages)
    package_pressure = "degraded" if missing_packages else "ready"
    layer_status = "ready" if has_model_manager else "degraded"
    probe_status = "ready" if has_probe else "degraded"
    reuse_status = "ready" if has_reuse_surface else "unknown"

    nodes = [
        {
            "id": "input",
            "label": "Prompt input",
            "kind": "input",
            "status": "ready",
            "layer_index": 0,
            "role": "input",
            "group": "entry",
            "metadata": {
                "source": "analysis_prompt",
            },
        },
        {
            "id": "embedding",
            "label": "Context packing",
            "kind": "embedding",
            "status": package_pressure,
            "layer_index": 1,
            "role": "embedding",
            "group": "preparation",
            "metadata": {
                "available_packages": package_count,
                "missing_packages": len(missing_packages),
            },
        },
        {
            "id": "layer",
            "label": runtime["model"],
            "kind": "layer",
            "status": layer_status,
            "layer_index": 2,
            "role": "layer",
            "group": "core",
            "metadata": {
                "runtime_label": runtime["label"],
                "provider": runtime["provider"],
                "drift_detected": runtime_drift["drift_detected"],
            },
        },
        {
            "id": "attention",
            "label": "Attention probe",
            "kind": "attention",
            "status": probe_status,
            "layer_index": 2,
            "role": "attention",
            "group": "probe",
            "metadata": {
                "probe_status": probe_health.get("status"),
                "probe_enabled": bool(probe_health.get("enabled")),
            },
        },
        {
            "id": "mlp",
            "label": "Response synthesis",
            "kind": "mlp",
            "status": layer_status,
            "layer_index": 3,
            "role": "mlp",
            "group": "synthesis",
            "metadata": {
                "stream_surface": "analysis_result",
            },
        },
        {
            "id": "residual",
            "label": "Reuse path",
            "kind": "residual",
            "status": reuse_status,
            "layer_index": 3,
            "role": "residual",
            "group": "reuse",
            "metadata": {
                "brain_available": bool(reuse.get("brain", {}).get("available")),
                "diagnostic_paths": len(reuse.get("diagnostics") or []),
            },
        },
        {
            "id": "output",
            "label": "Answer output",
            "kind": "output",
            "status": "ready" if has_model_manager else "degraded",
            "layer_index": 4,
            "role": "output",
            "group": "exit",
            "metadata": {
                "analysis_mode": "derived",
            },
        },
    ]
    edges = [
        {
            "from": "input",
            "to": "embedding",
            "label": "pack prompt",
            "kind": "flow",
            "direction": "forward",
            "weight": 1.0,
        },
        {
            "from": "embedding",
            "to": "layer",
            "label": "enter model",
            "kind": "flow",
            "direction": "forward",
            "weight": 0.95,
        },
        {
            "from": "layer",
            "to": "attention",
            "label": "probe path",
            "kind": "probe",
            "direction": "forward",
            "weight": 0.75,
        },
        {
            "from": "layer",
            "to": "mlp",
            "label": "synthesis path",
            "kind": "flow",
            "direction": "forward",
            "weight": 0.85,
        },
        {
            "from": "attention",
            "to": "residual",
            "label": "merge",
            "kind": "residual",
            "direction": "forward",
            "weight": 0.7,
        },
        {
            "from": "mlp",
            "to": "residual",
            "label": "merge",
            "kind": "residual",
            "direction": "forward",
            "weight": 0.7,
        },
        {
            "from": "residual",
            "to": "output",
            "label": "decode",
            "kind": "flow",
            "direction": "forward",
            "weight": 1.0,
        },
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "layer_count": 4,
            "block_count": 2,
        },
        "meta": {
            "runtime": runtime["label"],
            "model": runtime["model"],
            "provider": runtime["provider"],
            "generated_at": generated_at,
            "fidelity": "derived",
            "source": "derived snapshot",
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


async def _collect_runtime_drift(settings: Any = None) -> dict[str, Any]:
    """Run sync drift diagnostics off the event loop."""
    return await anyio.to_thread.run_sync(detect_runtime_drift, settings)


async def build_model_introspection_snapshot(
    *, model_manager: Any = None, settings: Any = None
) -> dict[str, Any]:
    """Build a read-only snapshot for model visualization and diagnostics."""

    active_runtime = get_active_llm_runtime(settings)
    runtime = active_runtime.to_payload()
    runtime_drift = await _collect_runtime_drift(settings)
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
    introspection_level = _resolve_snapshot_introspection_level(
        runtime_provider=str(runtime.get("provider") or ""),
        probe_health=probe_health,
    )

    runtime_probe_node = {
        "id": "probe",
        "label": f"probe:{probe_health['status']}",
        "kind": "probe",
        "status": "ready" if probe_health["healthy"] else "degraded",
    }
    reuse_payload = {
        "brain": {
            "path": "/brain",
            "available": True,
            "purpose": "existing rag and graph surface",
        },
        "diagnostics": [
            {"id": "217da", "purpose": "runtime lifecycle diagnostics"},
            {"id": "217db", "purpose": "runtime pipeline diagnostics"},
        ],
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

    architecture_graph = _build_architecture_graph_snapshot(
        runtime=runtime,
        runtime_drift=runtime_drift,
        available_packages=available_packages,
        missing_packages=missing_packages,
        model_manager=model_manager_snapshot,
        probe_health=probe_health,
        reuse=reuse_payload,
    )
    native_architecture_source = _resolve_native_architecture_source(
        runtime=runtime, model_manager=model_manager
    )
    if native_architecture_source is not None:
        architecture_graph = _build_native_architecture_graph_snapshot(
            runtime=runtime,
            missing_packages=missing_packages,
            model_manager=model_manager_snapshot,
            probe_health=probe_health,
            reuse=reuse_payload,
            architecture_source=native_architecture_source,
        )

    return {
        "runtime": runtime,
        "runtime_drift": runtime_drift,
        "packages": packages,
        "available_packages": available_packages,
        "missing_packages": missing_packages,
        "model_manager": model_manager_snapshot,
        "probe": probe_health,
        "introspection_level": introspection_level,
        "graph": graph_snapshot,
        "architecture_graph": architecture_graph,
        "reuse": reuse_payload,
        "summary": {
            "active_model": runtime["model"],
            "provider": runtime["provider"],
            "runtime_label": runtime["label"],
            "introspection_ready": True,
            "introspection_level": introspection_level,
        },
    }
