"""Wspólne walidatory dla modeli AI."""

import re


def validate_model_name_basic(name: str, max_length: int = 100) -> str:
    """
    Podstawowa walidacja nazwy modelu.

    Args:
        name: Nazwa modelu
        max_length: Maksymalna długość nazwy

    Returns:
        Zwalidowana nazwa

    Raises:
        ValueError: Jeśli nazwa jest nieprawidłowa
    """
    if not name or len(name) > max_length:
        raise ValueError(f"Nazwa modelu musi mieć 1-{max_length} znaków")
    if not re.match(r"^[\w\-.:]+$", name):
        raise ValueError("Nazwa modelu zawiera niedozwolone znaki")
    return name


def validate_model_name_extended(name: str, max_length: int = 200) -> str:
    """
    Rozszerzona walidacja nazwy modelu (z dozwolonymi slashami).

    Args:
        name: Nazwa modelu
        max_length: Maksymalna długość nazwy

    Returns:
        Zwalidowana nazwa

    Raises:
        ValueError: Jeśli nazwa jest nieprawidłowa
    """
    if not name or len(name) > max_length:
        raise ValueError(f"Nazwa modelu musi mieć 1-{max_length} znaków")
    if not re.match(r"^[\w\-.:\/]+$", name):
        raise ValueError("Nazwa modelu zawiera niedozwolone znaki")
    return name


def validate_huggingface_model_name(name: str) -> str:
    """
    Walidacja nazwy modelu HuggingFace.

    Args:
        name: Nazwa modelu

    Returns:
        Zwalidowana nazwa

    Raises:
        ValueError: Jeśli nazwa jest nieprawidłowa
    """
    if "/" not in name:
        raise ValueError("HuggingFace model must be in 'org/model' format")
    if not re.match(r"^[\w\-]+\/[\w\-.:]+$", name):
        raise ValueError("Invalid HuggingFace model name format")
    return name


def validate_ollama_model_name(name: str) -> str:
    """
    Walidacja nazwy modelu Ollama.

    Args:
        name: Nazwa modelu

    Returns:
        Zwalidowana nazwa

    Raises:
        ValueError: Jeśli nazwa jest nieprawidłowa
    """
    if "/" in name:
        raise ValueError("Ollama model names cannot contain forward slashes")
    if not re.match(r"^[\w\-.:]+$", name):
        raise ValueError("Invalid Ollama model name format")
    return name


def validate_provider(provider: str) -> str:
    """
    Walidacja providera modelu.

    Args:
        provider: Nazwa providera

    Returns:
        Zwalidowany provider

    Raises:
        ValueError: Jeśli provider jest nieprawidłowy
    """
    if provider not in ["huggingface", "ollama"]:
        raise ValueError("Provider musi być 'huggingface' lub 'ollama'")
    return provider


def validate_runtime(runtime: str) -> str:
    """
    Walidacja runtime.

    Args:
        runtime: Nazwa runtime

    Returns:
        Zwalidowany runtime

    Raises:
        ValueError: Jeśli runtime jest nieprawidłowy
    """
    if runtime not in ["vllm", "ollama", "onnx"]:
        raise ValueError("Runtime musi być 'vllm', 'ollama' lub 'onnx'")
    return runtime
