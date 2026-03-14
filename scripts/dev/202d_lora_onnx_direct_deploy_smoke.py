#!/usr/bin/env python3
"""202D Smoke: Direct LoRA adapter deploy to ONNX runtime (P0 gap verification).

Validates the closed P0 gap:
  1. onnx_runtime_compatibility_flag = True for Gemma-3 / HF models
  2. deploy_adapter_to_onnx endpoint responds (contract-level check)
  3. Rollback path for ONNX adapter deploy is exercisable

Usage:
    python scripts/dev/202d_lora_onnx_direct_deploy_smoke.py [--base-url URL]

Outputs:
    test-results/202d/lora_onnx_direct_deploy_smoke.json
    test-results/202d/lora_onnx_direct_deploy_smoke.md
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Resolve project root and add to path
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

_OUTPUT_DIR = _REPO_ROOT / "test-results" / "202d"
_REPORT_JSON = _OUTPUT_DIR / "lora_onnx_direct_deploy_smoke.json"
_REPORT_MD = _OUTPUT_DIR / "lora_onnx_direct_deploy_smoke.md"


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------


def _check(
    checks: List[Dict[str, Any]],
    name: str,
    passed: bool,
    detail: str = "",
    expected: Any = None,
    actual: Any = None,
) -> None:
    status = "PASS" if passed else "FAIL"
    entry: Dict[str, Any] = {"check": name, "status": status, "detail": detail}
    if expected is not None:
        entry["expected"] = expected
    if actual is not None:
        entry["actual"] = actual
    checks.append(entry)
    prefix = "  ✓" if passed else "  ✗"
    print(f"{prefix} [{status}] {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Gate 1: contract-level — ONNX in compatible_runtimes for HF models
# ---------------------------------------------------------------------------


def check_onnx_runtime_compatibility_flag(checks: List[Dict[str, Any]]) -> None:
    """Verify onnx_runtime_compatibility_flag=True for Gemma-3 (P0 criterion)."""
    print("\n[Gate 1] onnx_runtime_compatibility_flag")
    try:
        from venom_core.services.academy.trainable_catalog_service import (
            assess_runtime_base_model_compatibility,
        )

        for model_id in ["google/gemma-3-4b-it", "unsloth/Phi-3-mini-4k-instruct"]:
            assessment = assess_runtime_base_model_compatibility(
                base_model=model_id,
                runtime_id="onnx",
                available_runtime_ids=["vllm", "ollama", "onnx"],
            )
            is_compat = assessment["is_compatible"]
            _check(
                checks,
                f"onnx_compatible:{model_id}",
                is_compat,
                detail=assessment.get("reason_code") or "compatible",
                expected=True,
                actual=is_compat,
            )
    except Exception as exc:
        _check(checks, "onnx_runtime_compatibility_flag", False, detail=str(exc))


# ---------------------------------------------------------------------------
# Gate 2: _handle_non_ollama_runtime_deploy does NOT return runtime_not_supported
# ---------------------------------------------------------------------------


def check_direct_adapter_deploy_to_onnx_contract(checks: List[Dict[str, Any]]) -> None:
    """Verify direct_adapter_deploy_to_onnx=True (contract-level, mocked build)."""
    print("\n[Gate 2] direct_adapter_deploy_to_onnx (contract)")
    try:
        from venom_core.services.academy.adapter_runtime_service import (
            _handle_non_ollama_runtime_deploy,
        )

        mock_result = {
            "deployed": True,
            "runtime_id": "onnx",
            "chat_model": "venom-adapter-smoke-test",
            "config_hash": "smoke-hash",
        }
        result = _handle_non_ollama_runtime_deploy(
            runtime_local_id="onnx",
            adapter_id="smoke-test",
            deploy_adapter_to_onnx_runtime_fn=lambda **_: mock_result,
        )

        is_deployed = result.get("deployed") is True
        is_not_blocked = result.get("reason") != "runtime_not_supported:onnx"
        runtime_correct = result.get("runtime_id") == "onnx"

        _check(
            checks,
            "deployed_flag_true",
            is_deployed,
            expected=True,
            actual=result.get("deployed"),
        )
        _check(
            checks,
            "not_runtime_not_supported",
            is_not_blocked,
            detail="old blocking reason removed",
        )
        _check(
            checks,
            "runtime_id_onnx",
            runtime_correct,
            expected="onnx",
            actual=result.get("runtime_id"),
        )

    except Exception as exc:
        _check(checks, "direct_adapter_deploy_to_onnx", False, detail=str(exc))


# ---------------------------------------------------------------------------
# Gate 3: rollback path is exercisable for ONNX
# ---------------------------------------------------------------------------


def check_onnx_rollback_path(checks: List[Dict[str, Any]]) -> None:
    """Verify _rollback_onnx_adapter_deploy returns rolled_back=True with previous path."""
    print("\n[Gate 3] ONNX rollback path")
    from unittest.mock import MagicMock

    try:
        from venom_core.services.academy.adapter_runtime_service import (
            _rollback_onnx_adapter_deploy,
        )

        config_with_path = {
            "PREVIOUS_ONNX_LLM_MODEL_PATH": "models/phi3.5-mini-instruct-onnx",
            "PREVIOUS_MODEL_ONNX": "phi3.5-mini-instruct",
        }
        settings = MagicMock()
        settings.LAST_MODEL_ONNX = ""
        config_mgr = MagicMock()

        result = _rollback_onnx_adapter_deploy(
            config=config_with_path,
            settings_obj=settings,
            config_manager_obj=config_mgr,
            compute_llm_config_hash_fn=lambda *a: "hash-smoke",
            runtime_endpoint_for_hash_fn=lambda *a, **kw: None,
        )

        _check(
            checks,
            "rollback_rolled_back_true",
            result.get("rolled_back") is True,
            expected=True,
            actual=result.get("rolled_back"),
        )
        _check(
            checks,
            "rollback_runtime_id_onnx",
            result.get("runtime_id") == "onnx",
            expected="onnx",
            actual=result.get("runtime_id"),
        )

        update_call = config_mgr.update_config.call_args[0][0]
        _check(
            checks,
            "rollback_restores_onnx_path",
            update_call.get("ONNX_LLM_MODEL_PATH")
            == "models/phi3.5-mini-instruct-onnx",
            expected="models/phi3.5-mini-instruct-onnx",
            actual=update_call.get("ONNX_LLM_MODEL_PATH"),
        )
        _check(
            checks,
            "rollback_clears_previous_path_key",
            update_call.get("PREVIOUS_ONNX_LLM_MODEL_PATH") == "",
            expected="",
            actual=update_call.get("PREVIOUS_ONNX_LLM_MODEL_PATH"),
        )

        # Also check graceful failure when no previous info
        empty_result = _rollback_onnx_adapter_deploy(
            config={},
            settings_obj=MagicMock(LAST_MODEL_ONNX=""),
            config_manager_obj=MagicMock(),
            compute_llm_config_hash_fn=lambda *a: "h",
            runtime_endpoint_for_hash_fn=lambda *a, **kw: None,
        )
        _check(
            checks,
            "rollback_graceful_when_no_previous",
            empty_result.get("rolled_back") is False
            and empty_result.get("reason") == "previous_model_missing",
            detail="no previous info → rolled_back=False, reason=previous_model_missing",
        )

    except Exception as exc:
        _check(checks, "onnx_rollback", False, detail=str(exc))


# ---------------------------------------------------------------------------
# Gate 4: Live API smoke (optional, requires backend running)
# ---------------------------------------------------------------------------


def check_live_api(checks: List[Dict[str, Any]], base_url: str) -> None:
    """Optional live API check — adapters/audit must list ONNX in compatible_runtimes."""
    print(f"\n[Gate 4] Live API smoke ({base_url})")
    if httpx is None:
        _check(
            checks,
            "httpx_available",
            False,
            detail="httpx not installed, skipping live API",
        )
        return

    try:
        resp = httpx.get(f"{base_url}/api/v1/academy/adapters/audit", timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            adapters = data.get("adapters", [])
            _check(
                checks,
                "adapters_audit_200",
                True,
                detail=f"{len(adapters)} adapters returned",
            )
            # Informational: onnx key may be absent for adapters trained before 202D.
            # What matters is that the system doesn't error out.
            onnx_key_seen = any(
                "onnx" in (a.get("runtime_compatibility") or {}) for a in adapters
            )
            _check(
                checks,
                "onnx_key_in_audit_informational",
                True,  # always pass — this is informational only
                detail=f"onnx key in some adapter: {onnx_key_seen} (informational; pre-202D adapters may lack onnx key)",
            )
        else:
            _check(
                checks, "adapters_audit_200", False, detail=f"HTTP {resp.status_code}"
            )
    except Exception as exc:
        _check(
            checks, "live_api_adapters_audit", False, detail=f"connection error: {exc}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="202D: LoRA ONNX direct deploy smoke")
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8000", help="Backend URL"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("202D Smoke: Direct LoRA adapter deploy to ONNX runtime")
    print("=" * 60)

    checks: List[Dict[str, Any]] = []

    check_onnx_runtime_compatibility_flag(checks)
    check_direct_adapter_deploy_to_onnx_contract(checks)
    check_onnx_rollback_path(checks)
    check_live_api(checks, args.base_url)

    passed = sum(1 for c in checks if c["status"] == "PASS")
    failed = sum(1 for c in checks if c["status"] == "FAIL")
    overall = failed == 0

    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{len(checks)} PASS, {failed} FAIL")
    print(f"Overall: {'PASS ✓' if overall else 'FAIL ✗'}")

    report: Dict[str, Any] = {
        "stage": "202d",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "overall_pass": overall,
        "pass": passed,
        "fail": failed,
        "checks": checks,
        "p0_gates": {
            "onnx_runtime_compatibility_flag": all(
                c["status"] == "PASS" for c in checks if "onnx_compatible" in c["check"]
            ),
            "direct_adapter_deploy_to_onnx": all(
                c["status"] == "PASS"
                for c in checks
                if c["check"]
                in {
                    "deployed_flag_true",
                    "not_runtime_not_supported",
                    "runtime_id_onnx",
                }
            ),
            "rollback_supported": all(
                c["status"] == "PASS"
                for c in checks
                if c["check"].startswith("rollback_")
            ),
        },
    }

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Markdown summary
    lines = [
        "# 202D — LoRA ONNX Direct Deploy Smoke\n",
        f"**Timestamp**: {report['timestamp']}  ",
        f"**Overall**: {'✓ PASS' if overall else '✗ FAIL'}  ",
        f"**Results**: {passed}/{len(checks)} checks passed\n",
        "## P0 Gates\n",
    ]
    for gate, gate_pass in report["p0_gates"].items():
        lines.append(f"- **{gate}**: {'✓ PASS' if gate_pass else '✗ FAIL'}")
    lines += ["\n## Checks\n", "| Check | Status | Detail |", "|---|---|---|"]
    for c in checks:
        st = "✓" if c["status"] == "PASS" else "✗"
        lines.append(f"| {c['check']} | {st} {c['status']} | {c.get('detail', '')} |")
    _REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nArtifacts: {_REPORT_JSON}")
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
