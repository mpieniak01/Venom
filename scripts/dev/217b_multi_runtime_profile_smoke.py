#!/usr/bin/env python3
"""217B Faza 6: Smoke test profilu multi_runtime przez API systemowe.

Sprawdza:
1. GET /api/v1/runtime/multi-runtime/profile — poprawna odpowiedź.
2. POST /api/v1/runtime/multi-runtime/profile z polami live — accepted, apply_mode=live.
3. POST z precision=int4 — odrzucone z reason=precision_not_supported_for_runtime.
4. POST z quantization_backend=bitsandbytes — odrzucone z reason=quantization_backend_unavailable.
5. Wyświetla aktywny profil i apply_matrix.

Wymaga działającego backendu Venom na API_BASE_URL.
Domyślnie: http://localhost:8000

Użycie:
  python scripts/dev/217b_multi_runtime_profile_smoke.py [API_BASE_URL]

Exit code:
  0 — wszystkie smoke testy przeszły
  1 — backend niedostępny lub błąd krytyczny
  2 — nieoczekiwana odpowiedź kontraktu
"""

from __future__ import annotations

import sys
from typing import Any

try:
    import httpx
except ImportError:
    print("[ERROR] httpx not installed. pip install httpx")
    sys.exit(1)


def _get(client: httpx.Client, url: str) -> dict[str, Any]:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.json()  # type: ignore[return-value]


def _post(client: httpx.Client, url: str, body: dict) -> dict[str, Any]:
    resp = client.post(url, json=body)
    resp.raise_for_status()
    return resp.json()  # type: ignore[return-value]


def run_smoke(api_base: str) -> int:
    profile_url = f"{api_base}/api/v1/runtime/multi-runtime/profile"
    failures: list[str] = []

    print(f"Smoke target: {profile_url}")
    print("-" * 60)

    with httpx.Client(timeout=10.0) as client:
        # 1. GET profile
        try:
            data = _get(client, profile_url)
        except httpx.ConnectError:
            print(f"[ERROR] Cannot connect to backend at {api_base}")
            return 1
        except httpx.HTTPStatusError as e:
            print(f"[ERROR] GET profile returned {e.response.status_code}")
            return 1

        runtime_id = data.get("runtime_id")
        if runtime_id != "multi_runtime":
            failures.append(
                f"GET: runtime_id={runtime_id!r} (expected 'multi_runtime')"
            )
        else:
            print(f"[OK] GET profile — runtime_id={runtime_id}")

        daemon_reachable = data.get("daemon_reachable", False)
        profile = data.get("profile", {})
        matrix = data.get("apply_matrix", {})

        print(f"     daemon_reachable={daemon_reachable}")
        print(f"     model_id={profile.get('model_id')}")
        print(f"     max_new_tokens={profile.get('max_new_tokens')}")
        print()

        # 2. Verify apply_matrix values
        expected_matrix = {
            "model_id": "hard_restart",
            "cache_implementation": "soft_reload",
            "max_new_tokens": "live",
            "precision": "unsupported",
            "quantization_backend": "unsupported",
            "device_target": "unsupported",
        }
        for field, expected_mode in expected_matrix.items():
            actual = matrix.get(field)
            if actual != expected_mode:
                failures.append(
                    f"apply_matrix[{field}]={actual!r} (expected {expected_mode!r})"
                )
            else:
                print(f"[OK] apply_matrix.{field}={actual}")
        print()

        if not daemon_reachable:
            print("[WARN] Daemon is not reachable — skipping live POST tests")
            print("       Start the multi_runtime daemon and re-run for full smoke.")
        else:
            # 3. POST with live fields
            try:
                result = _post(
                    client,
                    profile_url,
                    {"max_new_tokens": 256, "enable_thinking": False},
                )
                mode = result.get("required_apply_mode")
                applied = result.get("applied")
                rejected = result.get("rejected", [])
                if mode != "live":
                    failures.append(
                        f"POST live: required_apply_mode={mode!r} (expected 'live')"
                    )
                elif rejected:
                    failures.append(f"POST live: got rejections: {rejected}")
                else:
                    print(f"[OK] POST live fields — applied={applied}, mode={mode}")
            except httpx.HTTPStatusError as e:
                failures.append(f"POST live: HTTP {e.response.status_code}")

            # 4. POST with precision (unsupported)
            try:
                result = _post(client, profile_url, {"precision": "int4"})
                rejected = result.get("rejected", [])
                if (
                    not rejected
                    or rejected[0].get("reason")
                    != "precision_not_supported_for_runtime"
                ):
                    failures.append(
                        f"POST precision: expected rejection with precision_not_supported_for_runtime, "
                        f"got: {rejected}"
                    )
                else:
                    print(
                        f"[OK] POST precision=int4 rejected — reason={rejected[0]['reason']}"
                    )
            except httpx.HTTPStatusError as e:
                failures.append(f"POST precision: HTTP {e.response.status_code}")

            # 5. POST with quantization_backend (unsupported)
            try:
                result = _post(
                    client, profile_url, {"quantization_backend": "bitsandbytes"}
                )
                rejected = result.get("rejected", [])
                if (
                    not rejected
                    or rejected[0].get("reason") != "quantization_backend_unavailable"
                ):
                    failures.append(
                        f"POST quantization_backend: expected quantization_backend_unavailable, "
                        f"got: {rejected}"
                    )
                else:
                    print(
                        f"[OK] POST quantization_backend rejected — reason={rejected[0]['reason']}"
                    )
            except httpx.HTTPStatusError as e:
                failures.append(
                    f"POST quantization_backend: HTTP {e.response.status_code}"
                )

    print()
    print("=" * 60)
    if failures:
        print(f"FAILED — {len(failures)} check(s) failed:")
        for f in failures:
            print(f"  ✗ {f}")
        return 2

    print("PASSED — all smoke checks OK")
    return 0


if __name__ == "__main__":
    api_base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    sys.exit(run_smoke(api_base))
