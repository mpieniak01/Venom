"""Probe helpers for GPUHabitat."""

from __future__ import annotations

import subprocess
import sys
from typing import Any, Callable


def check_local_gpu_availability(*, run_cmd_fn: Callable[..., Any]) -> bool:
    try:
        run_cmd_fn(["nvidia-smi"], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def check_local_dependencies(
    *,
    enable_gpu: bool,
    import_module_fn: Callable[[str], Any],
    logger: Any,
) -> bool:
    core_packages = ["transformers", "peft", "trl", "datasets", "accelerate"]
    missing = []

    for package in core_packages:
        try:
            import_module_fn(package)
        except ImportError:
            missing.append(package)

    if missing:
        python_bin = sys.executable or "python3"
        raise RuntimeError(
            f"Brak wymaganych bibliotek do treningu: {', '.join(missing)}. "
            f"Zainstaluj je w aktywnym interpreterze ({python_bin}) komendą: "
            f"{python_bin} -m pip install {' '.join(missing)}"
        )

    try:
        import_module_fn("unsloth")
        has_unsloth = True
    except ImportError:
        has_unsloth = False

    if enable_gpu and not has_unsloth:
        logger.warning(
            "Biblioteka 'unsloth' nie jest zainstalowana. Trening zostanie uruchomiony "
            "bez optymalizacji Unsloth (wolniej/CPU fallback możliwy)."
        )

    return has_unsloth


def check_gpu_availability(
    *,
    client: Any,
    docker_cuda_image: str,
    device_request_factory: Callable[..., Any],
    image_not_found_error: type[BaseException],
    api_error: type[BaseException],
    logger: Any,
    retry_check_fn: Callable[[], bool],
) -> bool:
    try:
        client.containers.run(
            image=docker_cuda_image,
            command="nvidia-smi",
            device_requests=[device_request_factory(count=-1, capabilities=[["gpu"]])],
            remove=True,
            detach=False,
        )

        logger.info("✅ GPU i nvidia-container-toolkit są dostępne")
        return True

    except image_not_found_error:
        logger.warning(f"Obraz {docker_cuda_image} nie jest dostępny, pobieram...")
        try:
            client.images.pull(docker_cuda_image)
            return retry_check_fn()
        except Exception as exc:
            logger.error(f"Nie można pobrać obrazu {docker_cuda_image}: {exc}")
            return False

    except api_error as exc:
        logger.warning(f"GPU lub nvidia-container-toolkit nie są dostępne: {exc}")
        logger.warning("Trening będzie dostępny tylko na CPU")
        return False

    except Exception as exc:
        logger.error(f"Nieoczekiwany błąd podczas sprawdzania GPU: {exc}")
        return False
