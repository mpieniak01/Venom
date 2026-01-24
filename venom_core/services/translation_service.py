"""Serwis do tłumaczenia treści za pomocą aktywnego modelu LLM."""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Dict, Optional, TypedDict

import httpx

from venom_core.config import SETTINGS
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


_LANG_LABELS = {
    "pl": "Polish",
    "en": "English",
    "de": "German",
}


class TranslationService:
    """Lekki serwis tłumaczeń używający aktywnego runtime."""

    class _CacheEntry(TypedDict):
        value: str
        timestamp: float

    def __init__(self, cache_ttl_seconds: int = 86400, max_concurrency: int = 3):
        self._cache: Dict[str, TranslationService._CacheEntry] = {}
        self._cache_ttl_seconds = float(cache_ttl_seconds)
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def _build_cache_key(
        self, text: str, source_lang: Optional[str], target_lang: str, model: str
    ) -> str:
        payload = f"{source_lang or 'auto'}::{target_lang}::{model}::{text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _resolve_chat_endpoint(self) -> str:
        runtime = get_active_llm_runtime()
        if runtime.service_type == "openai":
            return SETTINGS.OPENAI_CHAT_COMPLETIONS_ENDPOINT
        endpoint = (SETTINGS.LLM_LOCAL_ENDPOINT or "").rstrip("/")
        if not endpoint:
            raise RuntimeError("Brak skonfigurowanego endpointu LLM do tłumaczeń.")
        if endpoint.endswith("/chat/completions"):
            return endpoint
        if endpoint.endswith("/v1"):
            return f"{endpoint}/chat/completions"
        return f"{endpoint}/v1/chat/completions"

    def _resolve_headers(self, runtime=None) -> Dict[str, str]:
        runtime = runtime or get_active_llm_runtime()
        service_type = runtime.service_type
        if service_type == "openai" and SETTINGS.OPENAI_API_KEY:
            return {"Authorization": f"Bearer {SETTINGS.OPENAI_API_KEY}"}
        if service_type == "local" and SETTINGS.LLM_LOCAL_API_KEY:
            return {"Authorization": f"Bearer {SETTINGS.LLM_LOCAL_API_KEY}"}
        return {}

    async def translate_text(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None,
        use_cache: bool = True,
        allow_fallback: bool = True,
    ) -> str:
        if not text:
            return text
        target_lang = target_lang.lower()
        if target_lang not in _LANG_LABELS:
            raise ValueError(f"Nieobsługiwany język docelowy: {target_lang}")

        try:
            model_name = SETTINGS.LLM_MODEL_NAME or ""
            if not model_name:
                raise RuntimeError("Brak ustawionego modelu do tłumaczeń.")

            cache_key = self._build_cache_key(
                text, source_lang, target_lang, model_name
            )
            now = time.time()
            if use_cache:
                cached = self._cache.get(cache_key)
                if cached and now - cached["timestamp"] < self._cache_ttl_seconds:
                    return cached["value"]

            runtime = get_active_llm_runtime()
            chat_endpoint = self._resolve_chat_endpoint()
            headers = self._resolve_headers(runtime)

            system_prompt = (
                "You are a precise translation assistant. "
                "Translate the user text to the target language. "
                "Preserve names, URLs, formatting, and technical terms. "
                "Return only the translated text without extra commentary."
            )
            source_hint = _LANG_LABELS.get(source_lang or "", "the source language")
            target_label = _LANG_LABELS[target_lang]
            user_prompt = (
                f"Translate from {source_hint} to {target_label}. Text:\n{text}"
            )

            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            }

            async with self._semaphore:
                async with httpx.AsyncClient(
                    timeout=SETTINGS.OPENAI_API_TIMEOUT
                ) as client:
                    response = await client.post(
                        chat_endpoint, headers=headers, json=payload
                    )
                    response.raise_for_status()
                    data = response.json()
                message = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                result = message or text
                if use_cache:
                    self._cache[cache_key] = {"value": result, "timestamp": now}
                return result
        except Exception as exc:
            logger.warning(f"Tłumaczenie nie powiodło się: {exc}")
            if allow_fallback:
                return text
            raise


translation_service = TranslationService()
