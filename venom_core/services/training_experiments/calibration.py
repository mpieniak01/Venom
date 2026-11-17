"""Shared calibration contracts for Academy dev and independent holdouts."""

from . import grounded_claims, semantic_judge_dispatch

JUDGES = frozenset({"exact-v1", *semantic_judge_dispatch.JUDGES})
_LEGACY_PROTOCOL = "omni-rubric-v1"


def scorer_protocol(calibration: dict | None) -> str:
    if calibration is None or calibration.get("judge") == "exact-v1":
        return _LEGACY_PROTOCOL
    return semantic_judge_dispatch.scorer_protocol(calibration)


def validate_calibration(
    calibration: dict, dataset_sha256: str, cases: list[dict] | None = None
) -> None:
    if (
        not isinstance(calibration, dict)
        or type(calibration.get("schema_version")) is not int
        or calibration["schema_version"] != 1
        or not isinstance(calibration.get("judge"), str)
        or calibration.get("judge") not in JUDGES
        or calibration.get("dev_sha256") != dataset_sha256
        or not isinstance(calibration.get("reviewer"), str)
        or not calibration["reviewer"].strip()
        or not isinstance(calibration.get("cases"), dict)
    ):
        raise ValueError("experiment_calibration_invalid")
    if semantic_judge_dispatch.is_semantic(calibration):
        semantic_judge_dispatch.qualification(calibration)
    if cases is not None:
        rules = calibration["cases"]
        if semantic_judge_dispatch.is_semantic(calibration):
            grounded_claims.validate_claim_rubrics(
                {
                    key: semantic_judge_dispatch.claim_rubric(rule)
                    for key, rule in rules.items()
                },
                cases,
            )
        elif rules.keys() != {case["record_id"] for case in cases}:
            raise ValueError("experiment_calibration_coverage")
