"""Helpery dla routerow modeli (wspolne funkcje i walidacje)."""

import hashlib
import importlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
_SAFE_MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._/\-:]+$")


def _get_config_manager():
    models_module = importlib.import_module("venom_core.api.routes.models")
    return models_module.config_manager


def resolve_model_provider(models: List[dict], model_name: str):
    for model in models:
        if model.get("name") == model_name:
            return model.get("provider") or model.get("source")
    return None


def _normalize_model_name_for_fs(model_name: str) -> str | None:
    """Zwraca bezpieczną nazwę modelu do operacji na filesystemie."""
    if not model_name:
        return None
    if not _SAFE_MODEL_NAME_PATTERN.match(model_name):
        return None
    if ".." in model_name or model_name.startswith("/"):
        return None
    return model_name.strip()


def _redacted_input_fingerprint(value: str) -> str:
    """Zwraca bezpieczny fingerprint danych wejściowych bez logowania treści."""
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"len={len(value)},sha256={digest}"


def update_last_model(provider: str, new_model: str):
    if provider == "ollama":
        last_key = "LAST_MODEL_OLLAMA"
        prev_key = "PREVIOUS_MODEL_OLLAMA"
    else:
        last_key = "LAST_MODEL_VLLM"
        prev_key = "PREVIOUS_MODEL_VLLM"
    config = _get_config_manager().get_config(mask_secrets=False)
    current_last = config.get(last_key, "")
    if current_last and current_last != new_model:
        _get_config_manager().update_config({prev_key: current_last})
    _get_config_manager().update_config({last_key: new_model})


def load_generation_overrides() -> Dict[str, Any]:
    raw = (
        _get_config_manager()
        .get_config(mask_secrets=False)
        .get("MODEL_GENERATION_OVERRIDES", "")
    )
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception as exc:
        logger.warning(f"Nie udało się sparsować MODEL_GENERATION_OVERRIDES: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def save_generation_overrides(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _get_config_manager().update_config(
        {"MODEL_GENERATION_OVERRIDES": json.dumps(payload)}
    )


def validate_generation_params(
    params: Dict[str, Any], schema: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    validated: Dict[str, Any] = {}
    errors: List[str] = []

    for key, value in params.items():
        spec = schema.get(key)
        if spec is None:
            errors.append(f"Nieznany parametr: {key}")
            continue

        parsed_value, error = _validate_single_param(key=key, value=value, spec=spec)
        if error:
            errors.append(error)
            continue
        validated[key] = parsed_value

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    return validated


def _validate_single_param(
    *, key: str, value: Any, spec: Dict[str, Any]
) -> tuple[Any, str | None]:
    param_type = spec.get("type")
    if param_type in {"float", "int"}:
        return _parse_numeric_param(
            key=key,
            value=value,
            as_int=param_type == "int",
            min_value=spec.get("min"),
            max_value=spec.get("max"),
        )
    if param_type == "bool":
        if not isinstance(value, bool):
            return None, f"Parametr {key} musi być wartością bool"
        return value, None
    if param_type in {"list", "enum"}:
        return _validate_enum_like_param(key=key, value=value, spec=spec)
    return None, f"Nieobsługiwany typ parametru {key}"


def _validate_enum_like_param(
    *, key: str, value: Any, spec: Dict[str, Any]
) -> tuple[Any, str | None]:
    options = spec.get("options") or []
    if options and value not in options:
        return None, f"Parametr {key} musi być jedną z opcji"
    return value, None


def _parse_numeric_param(
    *,
    key: str,
    value: Any,
    as_int: bool,
    min_value: Any,
    max_value: Any,
) -> tuple[int | float | None, str | None]:
    try:
        parsed: int | float = float(value)
    except (TypeError, ValueError):
        return None, f"Parametr {key} musi być liczbą"
    if as_int:
        parsed = int(parsed)
    if min_value is not None and parsed < min_value:
        return None, f"Parametr {key} poniżej min {min_value}"
    if max_value is not None and parsed > max_value:
        return None, f"Parametr {key} powyżej max {max_value}"
    return parsed, None


def read_ollama_manifest_params(model_name: str) -> Dict[str, Any]:
    safe_model_name = _normalize_model_name_for_fs(model_name)
    if not safe_model_name:
        logger.warning(
            "Odrzucono nieprawidłową nazwę modelu (%s)",
            _redacted_input_fingerprint(model_name or ""),
        )
        return {}

    base_name, _, tag = safe_model_name.rpartition(":")
    repo = base_name if base_name else safe_model_name
    tag = tag or "latest"
    manifest_path = (
        Path("models") / "manifests" / "registry.ollama.ai" / "library" / repo / tag
    )
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as exc:
        logger.warning(f"Nie udało się wczytać manifestu Ollama: {exc}")
        return {}
    params_digest = None
    for layer in manifest.get("layers", []):
        if layer.get("mediaType") == "application/vnd.ollama.image.params":
            params_digest = layer.get("digest")
            break
    if not params_digest:
        return {}
    digest_value = params_digest.replace("sha256:", "")
    blob_path = Path("models") / "blobs" / f"sha256-{digest_value}"
    if not blob_path.exists():
        return {}
    try:
        return json.loads(blob_path.read_text())
    except Exception as exc:
        logger.warning(f"Nie udało się wczytać params Ollama: {exc}")
        return {}


def read_vllm_generation_config(model_name: str) -> Dict[str, Any]:
    candidates = []
    safe_model_name = _normalize_model_name_for_fs(model_name)
    if model_name and not safe_model_name:
        logger.warning(
            "Odrzucono nieprawidłową nazwę modelu (%s)",
            _redacted_input_fingerprint(model_name),
        )
        return {}

    if safe_model_name:
        candidates.append(Path("models") / safe_model_name)
        candidates.append(Path("models") / safe_model_name.split("/")[-1])

    vllm_path = Path(SETTINGS.VLLM_MODEL_PATH or "")
    if vllm_path.exists():
        candidates.append(vllm_path)

    for base in candidates:
        config_path = base / "generation_config.json"
        if not config_path.exists():
            continue
        try:
            return json.loads(config_path.read_text())
        except Exception as exc:
            logger.warning(f"Nie udało się wczytać generation_config: {exc}")
            return {}

    return {}
