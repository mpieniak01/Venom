"""Moduł: routes/models - Endpointy API dla zarządzania modelami AI."""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, field_validator

from venom_core.config import SETTINGS
from venom_core.core import metrics as metrics_module
from venom_core.core.generation_params_adapter import GenerationParamsAdapter
from venom_core.core.model_manager import DEFAULT_MODEL_SIZE_GB
from venom_core.services.config_manager import config_manager
from venom_core.services.translation_service import translation_service
from venom_core.utils.llm_runtime import (
    compute_llm_config_hash,
    get_active_llm_runtime,
    probe_runtime_status,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])

# Dependencies - będą ustawione w main.py
_model_manager = None
_model_registry = None


class ModelInstallRequest(BaseModel):
    """Request do instalacji modelu."""

    name: str

    @field_validator("name")
    def validate_name(cls, v):
        if not v or len(v) > 100:
            raise ValueError("Nazwa modelu musi mieć 1-100 znaków")
        if not re.match(r"^[\w\-.:]+$", v):
            raise ValueError("Nazwa modelu zawiera niedozwolone znaki")
        return v


class ModelSwitchRequest(BaseModel):
    """Request do zmiany aktywnego modelu."""

    name: str
    role: Optional[str] = (
        None  # Opcjonalnie: dla jakiej roli (np. "reasoning", "creative")
    )

    @field_validator("name")
    def validate_name(cls, v):
        if not v or len(v) > 100:
            raise ValueError("Nazwa modelu musi mieć 1-100 znaków")
        if not re.match(r"^[\w\-.:]+$", v):
            raise ValueError("Nazwa modelu zawiera niedozwolone znaki")
        return v


class ModelRegistryInstallRequest(BaseModel):
    """Request do instalacji modelu przez ModelRegistry."""

    name: str
    provider: str  # "huggingface" lub "ollama"
    runtime: str = "vllm"  # "vllm" lub "ollama"

    @field_validator("name")
    def validate_name(cls, v):
        if not v or len(v) > 200:
            raise ValueError("Nazwa modelu musi mieć 1-200 znaków")
        # Generic validation - specific validation happens per provider
        if not re.match(r"^[\w\-.:\/]+$", v):
            raise ValueError("Nazwa modelu zawiera niedozwolone znaki")
        return v

    @field_validator("provider")
    def validate_provider(cls, v):
        if v not in ["huggingface", "ollama"]:
            raise ValueError("Provider musi być 'huggingface' lub 'ollama'")
        return v

    def model_post_init(self, __context):
        """Validate model name format based on provider."""
        if self.provider == "huggingface":
            # HF models should have org/model format
            if "/" not in self.name:
                raise ValueError("HuggingFace model must be in 'org/model' format")
            if not re.match(r"^[\w\-]+\/[\w\-.:]+$", self.name):
                raise ValueError("Invalid HuggingFace model name format")
        elif self.provider == "ollama":
            # Ollama models don't support forward slashes
            if "/" in self.name:
                raise ValueError("Ollama model names cannot contain forward slashes")
            if not re.match(r"^[\w\-.:]+$", self.name):
                raise ValueError("Invalid Ollama model name format")
            if self.runtime != "ollama":
                raise ValueError("Runtime dla Ollama musi być 'ollama'")
        if self.provider == "huggingface" and self.runtime != "vllm":
            raise ValueError("Runtime dla HuggingFace musi być 'vllm'")

    @field_validator("runtime")
    def validate_runtime(cls, v):
        if v not in ["vllm", "ollama"]:
            raise ValueError("Runtime musi być 'vllm' lub 'ollama'")
        return v


class ModelActivateRequest(BaseModel):
    """Request do aktywacji modelu."""

    name: str
    runtime: str

    @field_validator("name")
    def validate_name(cls, v):
        if not v or len(v) > 200:
            raise ValueError("Nazwa modelu musi mieć 1-200 znaków")
        if not re.match(r"^[\w\-.:\/]+$", v):
            raise ValueError("Nazwa modelu zawiera niedozwolone znaki")
        return v

    @field_validator("runtime")
    def validate_runtime(cls, v):
        if v not in ["vllm", "ollama"]:
            raise ValueError("Runtime musi być 'vllm' lub 'ollama'")
        return v


class TranslationRequest(BaseModel):
    """Request do tłumaczenia tekstu."""

    text: str
    target_lang: str = "pl"
    source_lang: Optional[str] = None
    use_cache: bool = True


class ModelConfigUpdateRequest(BaseModel):
    """Request do aktualizacji parametrów generacji modelu."""

    runtime: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


def set_dependencies(model_manager, model_registry=None):
    """Ustaw zależności dla routera."""
    global _model_manager, _model_registry
    _model_manager = model_manager
    _model_registry = model_registry


def _resolve_model_provider(models: List[dict], model_name: str) -> Optional[str]:
    for model in models:
        if model.get("name") == model_name:
            return model.get("provider") or model.get("source")
    return None


def _update_last_model(provider: str, new_model: str):
    if provider == "ollama":
        last_key = "LAST_MODEL_OLLAMA"
        prev_key = "PREVIOUS_MODEL_OLLAMA"
    else:
        last_key = "LAST_MODEL_VLLM"
        prev_key = "PREVIOUS_MODEL_VLLM"
    config = config_manager.get_config(mask_secrets=False)
    current_last = config.get(last_key, "")
    if current_last and current_last != new_model:
        config_manager.update_config({prev_key: current_last})
    config_manager.update_config({last_key: new_model})


def _load_generation_overrides() -> Dict[str, Any]:
    raw = config_manager.get_config(mask_secrets=False).get(
        "MODEL_GENERATION_OVERRIDES", ""
    )
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception as exc:
        logger.warning(f"Nie udało się sparsować MODEL_GENERATION_OVERRIDES: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_generation_overrides(payload: Dict[str, Any]) -> Dict[str, Any]:
    return config_manager.update_config(
        {"MODEL_GENERATION_OVERRIDES": json.dumps(payload)}
    )


def _validate_generation_params(
    params: Dict[str, Any], schema: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    validated: Dict[str, Any] = {}
    errors: List[str] = []

    for key, value in params.items():
        if key not in schema:
            errors.append(f"Nieznany parametr: {key}")
            continue

        spec = schema[key]
        param_type = spec.get("type")
        min_value = spec.get("min")
        max_value = spec.get("max")
        options = spec.get("options") or []

        if param_type in ["float", "int"]:
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                errors.append(f"Parametr {key} musi być liczbą")
                continue
            if param_type == "int":
                parsed = int(parsed)
            if min_value is not None and parsed < min_value:
                errors.append(f"Parametr {key} poniżej min {min_value}")
                continue
            if max_value is not None and parsed > max_value:
                errors.append(f"Parametr {key} powyżej max {max_value}")
                continue
            validated[key] = parsed
            continue

        if param_type == "bool":
            if not isinstance(value, bool):
                errors.append(f"Parametr {key} musi być wartością bool")
                continue
            validated[key] = value
            continue

        if param_type in ["list", "enum"]:
            if options and value not in options:
                errors.append(f"Parametr {key} musi być jedną z opcji")
                continue
            validated[key] = value
            continue

        errors.append(f"Nieobsługiwany typ parametru {key}")

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    return validated


def _read_ollama_manifest_params(model_name: str) -> Dict[str, Any]:
    base_name, _, tag = model_name.rpartition(":")
    repo = base_name if base_name else model_name
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


def _read_vllm_generation_config(model_name: str) -> Dict[str, Any]:
    candidates = []
    if model_name:
        model_path = Path(model_name)
        if model_path.exists():
            candidates.append(model_path)
        candidates.append(Path("models") / model_name)
        candidates.append(Path("models") / model_name.split("/")[-1])

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


@router.get("/models")
async def list_models():
    """
    Zwraca listę modeli wraz z ich statusem.

    Returns:
        Lista modeli z metadanymi

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:
        models = await _model_manager.list_local_models()
        provider_buckets: Dict[str, List[dict]] = {}

        def resolve_provider(model: dict) -> str:
            provider = model.get("provider")
            if isinstance(provider, str) and provider:
                return provider
            if model.get("source") == "ollama":
                return "ollama"
            return "vllm"

        runtime_info = get_active_llm_runtime()
        runtime_status, runtime_error = await probe_runtime_status(runtime_info)
        runtime_payload = runtime_info.to_payload()
        runtime_payload["status"] = runtime_status
        if runtime_error:
            runtime_payload["error"] = runtime_error
        runtime_payload["configured_models"] = {
            "local": SETTINGS.LLM_MODEL_NAME,
            "hybrid_local": getattr(SETTINGS, "HYBRID_LOCAL_MODEL", None),
            "cloud": getattr(SETTINGS, "HYBRID_CLOUD_MODEL", None),
        }

        active_names = {
            SETTINGS.LLM_MODEL_NAME,
            getattr(SETTINGS, "HYBRID_LOCAL_MODEL", None),
        }
        active_names = {name for name in active_names if name}  # usuń None
        active_names.update({Path(name).name for name in list(active_names)})

        for model in models:
            candidate_names = {model.get("name")}
            path_value = model.get("path")
            if path_value:
                candidate_names.add(Path(path_value).name)
            if any(name in active_names for name in candidate_names if name):
                model["active"] = True
                model.setdefault("source", runtime_info.provider)
            provider = resolve_provider(model)
            model.setdefault("provider", provider)
            provider_buckets.setdefault(provider, []).append(model)
        return {
            "success": True,
            "models": models,
            "count": len(models),
            "active": runtime_payload,
            "providers": provider_buckets,
        }
    except Exception as e:
        logger.error(f"Błąd podczas listowania modeli: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/install")
async def install_model(
    request: ModelInstallRequest, background_tasks: BackgroundTasks
):
    """
    Uruchamia pobieranie modelu w tle.

    Args:
        request: Żądanie z nazwą modelu
        background_tasks: Mechanizm zadań w tle FastAPI

    Returns:
        Status rozpoczęcia pobierania

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
        HTTPException: 400 jeśli brak miejsca na dysku (Resource Guard)
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    # Sprawdź Resource Guard przed rozpoczęciem
    if not _model_manager.check_storage_quota(additional_size_gb=DEFAULT_MODEL_SIZE_GB):
        raise HTTPException(
            status_code=400,
            detail="Brak miejsca na dysku. Usuń nieużywane modele lub zwiększ limit.",
        )

    try:

        async def pull_task():
            """Zadanie w tle - pobieranie modelu."""
            logger.info(f"Rozpoczynam pobieranie modelu w tle: {request.name}")
            success = await _model_manager.pull_model(request.name)
            if success:
                logger.info(f"✅ Model {request.name} pobrany pomyślnie")
            else:
                logger.error(f"❌ Nie udało się pobrać modelu {request.name}")

        # Dodaj zadanie do tła
        background_tasks.add_task(pull_task)

        return {
            "success": True,
            "message": f"Pobieranie modelu {request.name} rozpoczęte w tle",
            "model_name": request.name,
        }
    except Exception as e:
        logger.error(f"Błąd podczas inicjalizacji pobierania modelu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/switch")
async def switch_model(request: ModelSwitchRequest):
    """
    Zmienia aktywny model dla określonej roli.

    Args:
        request: Żądanie z nazwą modelu i opcjonalną rolą

    Returns:
        Status zmiany modelu

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
        HTTPException: 404 jeśli model nie istnieje
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:
        # Sprawdź czy model istnieje
        models = await _model_manager.list_local_models()
        model_exists = any(m["name"] == request.name for m in models)

        if not model_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Model {request.name} nie znaleziony",
            )

        # Blokuj zmianę jeśli model nie pasuje do aktywnego runtime
        runtime_info = get_active_llm_runtime()
        active_provider = runtime_info.provider
        model_provider = _resolve_model_provider(models, request.name)
        if active_provider in {"ollama", "vllm"} and model_provider:
            if model_provider != active_provider:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Model {request.name} należy do {model_provider}, "
                        f"ale aktywny runtime to {active_provider}"
                    ),
                )

        # Aktywuj model (używając istniejącej metody activate_version)
        # Jeśli model nie jest zarejestrowany jako wersja, zarejestruj go
        if request.name not in _model_manager.versions:
            _model_manager.register_version(
                version_id=request.name,
                base_model=request.name,
            )

        success = _model_manager.activate_version(request.name)

        if success:
            # Zaktualizuj runtime config in-memory i w .env
            try:
                SETTINGS.LLM_MODEL_NAME = request.name
                SETTINGS.HYBRID_LOCAL_MODEL = request.name
                SETTINGS.LLM_SERVICE_TYPE = "local"
            except Exception:
                logger.warning("Nie udało się zaktualizować SETTINGS w pamięci.")
            config_manager.update_config(
                {
                    "LLM_MODEL_NAME": request.name,
                    "HYBRID_LOCAL_MODEL": request.name,
                    "LLM_SERVICE_TYPE": "local",
                }
            )
            config_hash = compute_llm_config_hash(
                active_provider, SETTINGS.LLM_LOCAL_ENDPOINT, request.name
            )
            config_manager.update_config({"LLM_CONFIG_HASH": config_hash})
            try:
                SETTINGS.LLM_CONFIG_HASH = config_hash
            except Exception:
                logger.warning(
                    "Nie udało się zaktualizować LLM_CONFIG_HASH w SETTINGS."
                )
            if model_provider:
                _update_last_model(model_provider, request.name)
            return {
                "success": True,
                "message": f"Model {request.name} został aktywowany",
                "active_model": request.name,
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Nie udało się aktywować modelu",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas zmiany modelu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.delete("/models/{model_name}")
async def delete_model(model_name: str):
    """
    Usuwa model z dysku.

    Args:
        model_name: Nazwa modelu do usunięcia

    Returns:
        Status usunięcia

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
        HTTPException: 400 jeśli model jest aktywny (Safety Check) lub nieprawidłowa nazwa
        HTTPException: 404 jeśli model nie istnieje
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    # Walidacja nazwy modelu
    if (
        not model_name
        or len(model_name) > 100
        or not re.match(r"^[\w\-.:]+$", model_name)
    ):
        raise HTTPException(status_code=400, detail="Nieprawidłowa nazwa modelu")

    try:
        success = await _model_manager.delete_model(model_name)

        if success:
            return {
                "success": True,
                "message": f"Model {model_name} został usunięty",
            }
        else:
            # Sprawdź czy to problem z aktywnym modelem
            if (
                _model_manager.active_version
                and model_name == _model_manager.active_version
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Nie można usunąć aktywnego modelu. Najpierw zmień model.",
                )
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_name} nie znaleziony lub nie można usunąć",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas usuwania modelu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/usage")
async def get_models_usage():
    """
    Zwraca metryki użycia: zajętość dysku (GB) oraz użycie VRAM.

    Returns:
        Słownik z metrykami

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:
        metrics = await _model_manager.get_usage_metrics()
        return {
            "success": True,
            "usage": metrics,
        }
    except Exception as e:
        logger.error(f"Błąd podczas pobierania metryk: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/unload-all")
async def unload_all_models():
    """
    Panic Button - wymusza zwolnienie pamięci VRAM/RAM.

    Returns:
        Status operacji

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:
        success = await _model_manager.unload_all()

        if success:
            return {
                "success": True,
                "message": "Wszystkie zasoby modeli zostały zwolnione",
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Nie udało się zwolnić zasobów",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas zwalniania zasobów: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


# ===== Nowe endpointy ModelRegistry =====


@router.get("/models/providers")
async def list_model_providers(provider: Optional[str] = None, limit: int = 20):
    """
    Lista dostępnych modeli ze wszystkich providerów.

    Args:
        provider: Opcjonalny filtr po providerze (huggingface, ollama)

    Returns:
        Lista modeli dostępnych do instalacji

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        from venom_core.core.model_registry import ModelProvider

        provider_enum = None
        if provider:
            try:
                provider_enum = ModelProvider(provider.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Nieprawidłowy provider: {provider}"
                )

        providers_to_query = (
            [provider_enum]
            if provider_enum
            else [ModelProvider.OLLAMA, ModelProvider.HUGGINGFACE]
        )

        all_models: List[dict] = []
        stale = False
        errors: List[str] = []

        for prov in providers_to_query:
            result = await _model_registry.list_catalog_models(prov, limit=limit)
            all_models.extend(result.get("models", []))
            stale = stale or bool(result.get("stale"))
            if result.get("error"):
                errors.append(result["error"])

        return {
            "success": True,
            "models": all_models,
            "count": len(all_models),
            "stale": stale,
            "error": "; ".join(errors) if errors else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas listowania providerów: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/trending")
async def list_trending_models(provider: str, limit: int = 12):
    """
    Lista trendujących modeli z zewnętrznych providerów.

    Args:
        provider: Provider (huggingface, ollama)
        limit: Limit wyników

    Returns:
        Lista trendujących modeli

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        from venom_core.core.model_registry import ModelProvider

        try:
            provider_enum = ModelProvider(provider.lower())
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Nieprawidłowy provider: {provider}"
            )

        result = await _model_registry.list_trending_models(
            provider=provider_enum, limit=limit
        )
        models = result.get("models", [])

        return {
            "success": True,
            "provider": provider_enum.value,
            "models": models,
            "count": len(models),
            "stale": bool(result.get("stale")),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas listowania trendów: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/news")
async def list_model_news(
    provider: str = "huggingface",
    limit: int = 5,
    type: str = "blog",
    month: str = "",
    lang: str = "en",
):
    """
    Lista newsów dla providerów (obecnie tylko HuggingFace).

    Args:
        provider: Provider (huggingface)
        limit: Limit wyników

    Returns:
        Lista newsów
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        from venom_core.core.model_registry import ModelProvider

        try:
            provider_enum = ModelProvider(provider.lower())
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Nieprawidłowy provider: {provider}"
            )

        result = await _model_registry.list_news(
            provider=provider_enum,
            limit=limit,
            kind=type,
            month=month or None,
        )
        items = result.get("items", [])
        target_lang = (lang or "en").lower()
        if target_lang not in ["pl", "en", "de"]:
            raise HTTPException(
                status_code=400,
                detail="Obsługiwane języki: pl, en, de",
            )

        if type == "papers" and items:
            max_summary_chars = SETTINGS.NEWS_SUMMARY_MAX_CHARS
            for item in items:
                summary = item.get("summary")
                if summary and len(summary) > max_summary_chars:
                    trimmed = summary[:max_summary_chars].rstrip()
                    item["summary"] = f"{trimmed}..."

        translation_error = None
        if target_lang != "en" and items:
            try:
                translated_items = []
                for item in items:
                    title = item.get("title")
                    summary = item.get("summary")
                    if title:
                        try:
                            translated_title = await asyncio.wait_for(
                                translation_service.translate_text(
                                    title,
                                    target_lang=target_lang,
                                    source_lang="en",
                                    allow_fallback=True,
                                ),
                                timeout=SETTINGS.TRANSLATION_TIMEOUT_NEWS,
                            )
                        except asyncio.TimeoutError:
                            translated_title = title
                    else:
                        translated_title = title

                    if summary:
                        try:
                            translated_summary = await asyncio.wait_for(
                                translation_service.translate_text(
                                    summary,
                                    target_lang=target_lang,
                                    source_lang="en",
                                    allow_fallback=True,
                                ),
                                timeout=SETTINGS.TRANSLATION_TIMEOUT_PAPERS,
                            )
                        except asyncio.TimeoutError:
                            translated_summary = summary
                    else:
                        translated_summary = summary
                    translated_item = dict(item)
                    translated_item["title"] = translated_title
                    translated_item["summary"] = translated_summary
                    translated_items.append(translated_item)
                items = translated_items
            except Exception as exc:
                translation_error = str(exc)
                logger.warning(f"Nie udało się przetłumaczyć newsów: {exc}")

        base_error = result.get("error")
        if translation_error:
            error_message = (
                f"{base_error}; translation: {translation_error}"
                if base_error
                else f"translation: {translation_error}"
            )
        else:
            error_message = base_error

        return {
            "success": True,
            "provider": provider_enum.value,
            "items": items,
            "count": len(items),
            "stale": bool(result.get("stale")),
            "error": error_message,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas listowania newsów: {e}")
        return {
            "success": False,
            "provider": provider,
            "items": [],
            "count": 0,
            "stale": True,
            "error": str(e),
        }


@router.post("/translate")
async def translate_text_endpoint(request: TranslationRequest):
    """
    Uniwersalny endpoint do tłumaczenia treści z użyciem aktywnego modelu.
    """
    try:
        if request.target_lang not in ["pl", "en", "de"]:
            raise HTTPException(
                status_code=400, detail="Obsługiwane języki: pl, en, de"
            )
        translated = await translation_service.translate_text(
            request.text,
            target_lang=request.target_lang,
            source_lang=request.source_lang,
            use_cache=request.use_cache,
            allow_fallback=False,
        )
        return {
            "success": True,
            "translated_text": translated,
            "target_lang": request.target_lang,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Błąd tłumaczenia: {exc}")
        raise HTTPException(status_code=500, detail="Błąd serwera podczas tłumaczenia")


@router.post("/models/registry/install")
async def install_model_registry(request: ModelRegistryInstallRequest):
    """
    Instaluje model przez ModelRegistry (HuggingFace lub Ollama).

    Args:
        request: Żądanie z nazwą modelu, providerem i runtime

    Returns:
        operation_id do sprawdzania statusu instalacji

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 400 jeśli nieprawidłowe dane wejściowe
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        from venom_core.core.model_registry import ModelProvider

        provider_enum = ModelProvider(request.provider.lower())

        logger.info(
            "Install registry model: %s provider=%s runtime=%s",
            request.name,
            request.provider,
            request.runtime,
        )
        operation_id = await _model_registry.install_model(
            model_name=request.name,
            provider=provider_enum,
            runtime=request.runtime,
        )

        return {
            "success": True,
            "operation_id": operation_id,
            "message": f"Instalacja modelu {request.name} rozpoczęta",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Błąd podczas rozpoczynania instalacji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.delete("/models/registry/{model_name}")
async def remove_model_registry(model_name: str):
    """
    Usuwa model przez ModelRegistry.

    Args:
        model_name: Nazwa modelu do usunięcia

    Returns:
        operation_id do sprawdzania statusu usuwania

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 404 jeśli model nie znaleziony
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        logger.info("Remove registry model: %s", model_name)
        operation_id = await _model_registry.remove_model(model_name)

        return {
            "success": True,
            "operation_id": operation_id,
            "message": f"Usuwanie modelu {model_name} rozpoczęte",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Błąd podczas usuwania modelu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/activate")
async def activate_model_endpoint(request: ModelActivateRequest):
    """
    Aktywuje model dla danego runtime.

    Args:
        request: Żądanie z nazwą modelu i runtime

    Returns:
        Status aktywacji

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 404 jeśli model nie znaleziony
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        logger.info(
            "Activate model: %s runtime=%s",
            request.name,
            request.runtime,
        )
        success = await _model_registry.activate_model(
            model_name=request.name, runtime=request.runtime
        )

        if success:
            return {
                "success": True,
                "message": f"Model {request.name} aktywowany dla runtime {request.runtime}",
            }
        else:
            raise HTTPException(
                status_code=500, detail="Nie udało się aktywować modelu"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas aktywacji modelu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/operations")
async def list_model_operations(limit: int = 10):
    """
    Lista ostatnich operacji na modelach.

    Args:
        limit: Maksymalna liczba operacji do zwrócenia

    Returns:
        Lista operacji z ich statusami

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        operations = _model_registry.list_operations(limit=limit)

        return {
            "success": True,
            "operations": [op.to_dict() for op in operations],
            "count": len(operations),
        }
    except Exception as e:
        logger.error(f"Błąd podczas listowania operacji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/operations/{operation_id}")
async def get_operation_status_endpoint(operation_id: str):
    """
    Pobiera status operacji.

    Args:
        operation_id: ID operacji

    Returns:
        Status operacji

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 404 jeśli operacja nie znaleziona
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        operation = _model_registry.get_operation_status(operation_id)

        if operation is None:
            raise HTTPException(status_code=404, detail="Operacja nie znaleziona")

        return {
            "success": True,
            "operation": operation.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas pobierania statusu operacji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/{model_name}/capabilities")
async def get_model_capabilities_endpoint(model_name: str):
    """
    Pobiera capabilities modelu (wsparcie ról, templaty, etc.).

    Args:
        model_name: Nazwa modelu

    Returns:
        Capabilities modelu

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 404 jeśli model nie znaleziony
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        capabilities = _model_registry.get_model_capabilities(model_name)

        if capabilities is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_name} nie znaleziony w manifeście",
            )

        capabilities_dict = {
            "supports_system_role": capabilities.supports_system_role,
            "supports_function_calling": capabilities.supports_function_calling,
            "allowed_roles": capabilities.allowed_roles,
            "prompt_template": capabilities.prompt_template,
            "max_context_length": capabilities.max_context_length,
            "quantization": capabilities.quantization,
        }

        if capabilities.generation_schema:
            capabilities_dict["generation_schema"] = {
                key: param.to_dict()
                for key, param in capabilities.generation_schema.items()
            }

        return {
            "success": True,
            "model_name": model_name,
            "capabilities": capabilities_dict,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas pobierania capabilities: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/{model_name}/config")
async def get_model_config_endpoint(model_name: str, runtime: Optional[str] = None):
    """
    Pobiera schemat parametrów generacji dla modelu (generation_schema).

    Ten endpoint zwraca dynamiczną konfigurację parametrów dostępnych dla danego modelu,
    takich jak temperature, max_tokens, top_p, etc.

    Args:
        model_name: Nazwa modelu

    Returns:
        Słownik z konfiguracją parametrów generacji (wewnętrzny format aplikacji)

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 404 jeśli model nie znaleziony lub nie ma schematu
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        capabilities = _model_registry.get_model_capabilities(model_name)

        if capabilities is None or capabilities.generation_schema is None:
            from venom_core.core.model_registry import _create_default_generation_schema

            logger.warning(
                "Brak schematu w manifestcie, używam domyślnego: model=%s",
                model_name,
            )
            generation_schema = _create_default_generation_schema()
        else:
            generation_schema = capabilities.generation_schema

        schema = {key: param.to_dict() for key, param in generation_schema.items()}
        runtime_info = get_active_llm_runtime()
        runtime_key = (
            GenerationParamsAdapter.normalize_provider(runtime)
            if runtime
            else GenerationParamsAdapter.normalize_provider(runtime_info.provider)
        )
        if runtime_key == "ollama":
            manifest_params = _read_ollama_manifest_params(model_name)
            mapped = {
                "temperature": manifest_params.get("temperature"),
                "top_p": manifest_params.get("top_p"),
                "top_k": manifest_params.get("top_k"),
                "repeat_penalty": manifest_params.get("repeat_penalty"),
            }
            num_predict = manifest_params.get("num_predict")
            num_ctx = manifest_params.get("num_ctx")
            if num_predict is not None:
                mapped["max_tokens"] = num_predict
            elif num_ctx is not None:
                mapped["max_tokens"] = num_ctx
            for key, value in mapped.items():
                if key in schema and value is not None:
                    schema[key]["default"] = value
        if runtime_key == "vllm":
            gen_config = _read_vllm_generation_config(model_name)
            mapped = {
                "temperature": gen_config.get("temperature"),
                "top_p": gen_config.get("top_p"),
                "top_k": gen_config.get("top_k"),
                "repeat_penalty": gen_config.get("repetition_penalty"),
            }
            max_new_tokens = gen_config.get("max_new_tokens")
            if max_new_tokens is not None:
                mapped["max_tokens"] = max_new_tokens
            for key, value in mapped.items():
                if key in schema and value is not None:
                    schema[key]["default"] = value
        defaults = {key: spec.get("default") for key, spec in schema.items()}
        overrides = (
            _load_generation_overrides().get(runtime_key, {}).get(model_name, {})
        )
        current_values = {**defaults, **overrides}

        return {
            "success": True,
            "model_name": model_name,
            "generation_schema": schema,
            "current_values": current_values,
            "runtime": runtime_key,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas pobierania config: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/{model_name}/config")
async def update_model_config_endpoint(
    model_name: str, request: ModelConfigUpdateRequest
):
    """
    Aktualizuje parametry generacji dla modelu (per runtime).
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        capabilities = _model_registry.get_model_capabilities(model_name)
        generation_schema = None
        if capabilities and capabilities.generation_schema is not None:
            generation_schema = capabilities.generation_schema
        else:
            from venom_core.core.model_registry import _create_default_generation_schema

            logger.warning(
                "Brak schematu w manifestcie podczas zapisu, używam domyślnego: model=%s",
                model_name,
            )
            generation_schema = _create_default_generation_schema()

        runtime_info = get_active_llm_runtime()
        runtime_key = (
            GenerationParamsAdapter.normalize_provider(request.runtime)
            if request.runtime
            else GenerationParamsAdapter.normalize_provider(runtime_info.provider)
        )

        schema = {key: param.to_dict() for key, param in generation_schema.items()}

        if request.params:
            validated = _validate_generation_params(request.params, schema)
        else:
            validated = {}

        overrides = _load_generation_overrides()
        overrides.setdefault(runtime_key, {})

        if not validated:
            overrides.get(runtime_key, {}).pop(model_name, None)
        else:
            overrides[runtime_key][model_name] = validated

        update_result = _save_generation_overrides(overrides)
        if not update_result.get("success"):
            raise HTTPException(status_code=500, detail=update_result.get("message"))

        logger.info(
            "Zapisano parametry generacji: model=%s runtime=%s keys=%s",
            model_name,
            runtime_key,
            list(validated.keys()),
        )
        collector = metrics_module.metrics_collector
        if collector:
            collector.increment_model_params_update()

        return {
            "success": True,
            "model_name": model_name,
            "runtime": runtime_key,
            "params": validated,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas zapisu config: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")
