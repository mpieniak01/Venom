"""Kanoniczne nazwy publiczne runtime LLM i helper normalizacji.

Ten moduł jest jedynym miejscem definiującym publiczne identyfikatory runtime.
Wszystkie porównania runtime_id w backendzie, API i testach mają przechodzić
przez is_multi_runtime() lub normalize_runtime_id() zamiast porównywać
twardo do literału "gemma4_audio".
"""

from __future__ import annotations

# Publiczny identyfikator runtime Gemma 4 multimodalnego (audio + obraz + tekst).
MULTI_RUNTIME_ID = "multi_runtime"

# Stara nazwa — zachowana wyłącznie do normalizacji wejścia (konfiguracja, stare klienty).
_LEGACY_RUNTIME_ID = "gemma4_audio"


def is_multi_runtime(runtime_id: str | None) -> bool:
    """Zwraca True dla każdego identyfikatora odnoszącego się do multi_runtime."""
    normalized = str(runtime_id or "").strip().lower()
    return normalized in {
        MULTI_RUNTIME_ID,
        _LEGACY_RUNTIME_ID,
    } or normalized.startswith((f"{MULTI_RUNTIME_ID}@", f"{_LEGACY_RUNTIME_ID}@"))


def normalize_runtime_id(runtime_id: str | None) -> str:
    """Przepisuje stary identyfikator gemma4_audio na kanoniczną nazwę multi_runtime.

    Identyfikatory z sufiksem (np. 'gemma4_audio@localhost:8014') są przepisywane
    z zachowaniem sufiksu ('multi_runtime@localhost:8014').
    Wszystkie inne nazwy są zwracane bez zmian (lowercase).
    """
    raw = str(runtime_id or "").strip().lower()
    if raw == _LEGACY_RUNTIME_ID:
        return MULTI_RUNTIME_ID
    if raw.startswith(f"{_LEGACY_RUNTIME_ID}@"):
        return MULTI_RUNTIME_ID + raw[len(_LEGACY_RUNTIME_ID) :]
    return raw
