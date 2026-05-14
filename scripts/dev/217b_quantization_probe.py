#!/usr/bin/env python3
"""217B Faza 6: Probe dostępności kwantyzacji dla multi_runtime.

Sprawdza:
1. Czy bitsandbytes jest zainstalowane i importowalne.
2. Czy torch jest dostępny i jaka jest wersja.
3. Czy transformers jest dostępny i jaka jest wersja.
4. Status pól precision / quantization_backend w kontrakcie multi_runtime_profile.

Raport idzie na stdout. Exit code:
- 0 — probe zakończony (niezależnie od statusu bitsandbytes)
- 1 — błąd krytyczny (nie można załadować podstawowych zależności)
"""

from __future__ import annotations

import importlib
import sys


def _check_module(name: str) -> tuple[bool, str]:
    """Return (available, version_or_error)."""
    try:
        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", "unknown")
        return True, str(version)
    except ImportError as e:
        return False, str(e)


def main() -> int:
    print("=" * 60)
    print("217B Quantization Probe — multi_runtime")
    print("=" * 60)

    # --- torch ---
    torch_ok, torch_info = _check_module("torch")
    if torch_ok:
        try:
            import torch

            cuda_available = torch.cuda.is_available()
            print(f"[OK] torch {torch_info} — CUDA available: {cuda_available}")
        except Exception as e:
            print(f"[WARN] torch import failed at runtime: {e}")
    else:
        print(f"[WARN] torch not available: {torch_info}")

    # --- transformers ---
    tf_ok, tf_info = _check_module("transformers")
    if tf_ok:
        print(f"[OK] transformers {tf_info}")
    else:
        print(f"[WARN] transformers not available: {tf_info}")

    # --- bitsandbytes ---
    bnb_ok, bnb_info = _check_module("bitsandbytes")
    if bnb_ok:
        print(f"[OK] bitsandbytes {bnb_info} — quantization_backend AVAILABLE")
        bnb_status = "available"
    else:
        print(f"[INFO] bitsandbytes not installed: {bnb_info}")
        print(
            "       quantization_backend will remain 'unsupported' in multi_runtime_profile"
        )
        bnb_status = "unavailable"

    # --- Contract status report ---
    print()
    print("multi_runtime_profile contract status:")
    print("  precision           → apply_mode=unsupported  (loader uses dtype='auto')")
    if bnb_status == "available":
        print(
            "  quantization_backend→ bitsandbytes present, "
            "but apply_mode=unsupported until loader activates it"
        )
    else:
        print(
            "  quantization_backend→ apply_mode=unsupported "
            "(bitsandbytes not installed)"
        )
    print(
        "  device_target       → apply_mode=unsupported  (runtime selection not active)"
    )

    print()
    print("Conclusion:")
    if bnb_status == "available":
        print(
            "  bitsandbytes is installed. When the loader is updated to use it,\n"
            "  update APPLY_MATRIX['quantization_backend'] from 'unsupported' to 'hard_restart'."
        )
    else:
        print(
            "  Install bitsandbytes to enable quantization_backend in multi_runtime_profile.\n"
            "  pip install bitsandbytes"
        )

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
