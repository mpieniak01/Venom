"""
Moduł: validators - Wspólne walidatory dla API.

Wydzielony z routes/models.py dla redukcji duplikacji.
"""

import re
from typing import Any, Dict


def validate_model_name(
    name: str, max_length: int = 100, allow_slash: bool = False
) -> str:
    """
    Waliduje nazwę modelu.

    Args:
        name: Nazwa modelu do walidacji
        max_length: Maksymalna długość nazwy
        allow_slash: Czy dozwolone są ukośniki (dla HuggingFace org/model)

    Returns:
        Zwalidowana nazwa

    Raises:
        ValueError: Jeśli nazwa jest nieprawidłowa
    """
    if not name or len(name) > max_length:
        raise ValueError(f"Nazwa modelu musi mieć 1-{max_length} znaków")

    if allow_slash:
        pattern = r"^[\w\-.:\/]+$"
    else:
        pattern = r"^[\w\-.:]+$"

    if not re.match(pattern, name):
        raise ValueError("Nazwa modelu zawiera niedozwolone znaki")

    return name


def validate_huggingface_model_name(name: str) -> str:
    """
    Waliduje nazwę modelu HuggingFace (org/model format).

    Args:
        name: Nazwa modelu

    Returns:
        Zwalidowana nazwa

    Raises:
        ValueError: Jeśli format jest nieprawidłowy
    """
    if "/" not in name:
        raise ValueError("Model HuggingFace musi być w formacie 'org/model'")

    if not re.match(r"^[\w\-]+\/[\w\-.:]+$", name):
        raise ValueError("Nieprawidłowy format nazwy modelu HuggingFace")

    return name


def validate_ollama_model_name(name: str) -> str:
    """
    Waliduje nazwę modelu Ollama (bez ukośników).

    Args:
        name: Nazwa modelu

    Returns:
        Zwalidowana nazwa

    Raises:
        ValueError: Jeśli format jest nieprawidłowy
    """
    if "/" in name:
        raise ValueError("Nazwy modeli Ollama nie mogą zawierać ukośników")

    if not re.match(r"^[\w\-.:]+$", name):
        raise ValueError("Nieprawidłowy format nazwy modelu Ollama")

    return name


def validate_provider(provider: str) -> str:
    """
    Waliduje dostawcę modelu.

    Args:
        provider: Nazwa dostawcy

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
    Waliduje runtime dla modelu.

    Args:
        runtime: Nazwa runtime

    Returns:
        Zwalidowany runtime

    Raises:
        ValueError: Jeśli runtime jest nieprawidłowy
    """
    if runtime not in ["vllm", "ollama"]:
        raise ValueError("Runtime musi być 'vllm' lub 'ollama'")
    return runtime


def validate_generation_params(
    params: Dict[str, Any], schema: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Waliduje parametry generacji względem schematu.

    Args:
        params: Parametry do walidacji
        schema: Schemat walidacji (parametr -> {type, min, max, ...})

    Returns:
        Zwalidowane parametry

    Raises:
        ValueError: Jeśli parametry są nieprawidłowe
    """
    validated = {}

    for key, value in params.items():
        if key not in schema:
            raise ValueError(f"Nieznany parametr: {key}")

        param_def = schema[key]
        param_type = param_def.get("type")

        # Walidacja typu
        if param_type == "float":
            try:
                value = float(value)
            except (ValueError, TypeError):
                raise ValueError(f"Parametr {key} musi być liczbą zmiennoprzecinkową")

            # Walidacja zakresu
            if "min" in param_def and value < param_def["min"]:
                raise ValueError(
                    f"Parametr {key} musi być >= {param_def['min']}, otrzymano {value}"
                )
            if "max" in param_def and value > param_def["max"]:
                raise ValueError(
                    f"Parametr {key} musi być <= {param_def['max']}, otrzymano {value}"
                )

        elif param_type == "int":
            try:
                value = int(value)
            except (ValueError, TypeError):
                raise ValueError(f"Parametr {key} musi być liczbą całkowitą")

            # Walidacja zakresu
            if "min" in param_def and value < param_def["min"]:
                raise ValueError(
                    f"Parametr {key} musi być >= {param_def['min']}, otrzymano {value}"
                )
            if "max" in param_def and value > param_def["max"]:
                raise ValueError(
                    f"Parametr {key} musi być <= {param_def['max']}, otrzymano {value}"
                )

        elif param_type == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"Parametr {key} musi być wartością logiczną")

        elif param_type == "enum":
            options = param_def.get("options", [])
            if value not in options:
                raise ValueError(
                    f"Parametr {key} musi być jedną z wartości: {options}, otrzymano {value}"
                )

        validated[key] = value

    return validated
