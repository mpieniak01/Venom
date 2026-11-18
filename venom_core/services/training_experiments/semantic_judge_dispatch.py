"""Dispatch qualified semantic reviewers without falling back to exact matching."""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

from . import local_semantic_judge as local
from . import openrouter_semantic_judge as remote

JUDGES = frozenset({*local.JUDGES, *remote.JUDGES})
JudgePin = local.JudgePin | remote.QualificationRemote


def backend(calibration: dict) -> ModuleType:
    judge = calibration.get("judge")
    if not isinstance(judge, str):
        raise ValueError("experiment_judge_version_invalid")
    if judge in local.JUDGES:
        return local
    if judge in remote.JUDGES:
        return remote
    raise ValueError("experiment_judge_version_invalid")


def is_semantic(calibration: dict) -> bool:
    if calibration.get("judge") == "exact-v1":
        return False
    backend(calibration)
    return True


def qualification(calibration: dict) -> JudgePin:
    return backend(calibration).qualification(calibration)


def preflight(calibration: dict) -> None:
    backend(calibration).preflight(calibration)


def claim_rubric(spec: dict) -> dict:
    return local.claim_rubric(spec)


def review_bundle(
    calibration: dict,
    bundle: dict,
    run_id: str,
    seconds: float,
    *,
    check: Callable[[], None] = lambda: None,
) -> list[dict]:
    return backend(calibration).review_bundle(
        calibration, bundle, run_id, seconds, check=check
    )


def verify_review_receipt(
    pin: JudgePin, spec: dict, case: dict, answer: dict, grade: dict
) -> None:
    if isinstance(pin, remote.QualificationRemote):
        remote.verify_review_receipt(pin, spec, case, answer, grade)
    elif isinstance(pin, local.JudgePin):
        local.verify_review_receipt(pin, spec, case, answer, grade)
    else:
        raise ValueError("experiment_judge_version_invalid")


def scorer_protocol(calibration: dict) -> str:
    selected = backend(calibration)
    if selected is remote:
        return remote.scorer_protocol(calibration)
    pin = calibration["judge_qualification"]
    return (
        f"{calibration['judge']}:schema-{calibration['schema_version']}:"
        f"{pin['protocol_sha256']}:{pin['result_sha256']}"
    )
