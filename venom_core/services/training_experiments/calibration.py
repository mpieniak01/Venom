"""Shared calibration contracts for Academy dev and independent holdouts."""

from . import grounded_claims, local_semantic_judge

JUDGES = frozenset({"exact-v1", *local_semantic_judge.JUDGES})
_LEGACY_PROTOCOL = "omni-rubric-v1"


def scorer_protocol(calibration: dict | None) -> str:
    if calibration is None or calibration.get("judge") == "exact-v1":
        return _LEGACY_PROTOCOL
    judge = calibration["judge"]
    if judge in local_semantic_judge.JUDGES:
        pin = calibration["judge_qualification"]
        return f"{judge}:schema-{calibration['schema_version']}:{pin['protocol_sha256']}:{pin['result_sha256']}"
    return _LEGACY_PROTOCOL


def validate_calibration(
    calibration: dict, dataset_sha256: str, cases: list[dict] | None = None
) -> None:
    if (
        not isinstance(calibration, dict)
        or type(calibration.get("schema_version")) is not int
        or calibration["schema_version"] != 1
        or calibration.get("judge") not in JUDGES
        or calibration.get("dev_sha256") != dataset_sha256
        or not isinstance(calibration.get("reviewer"), str)
        or not calibration["reviewer"].strip()
        or not isinstance(calibration.get("cases"), dict)
    ):
        raise ValueError("experiment_calibration_invalid")
    if calibration["judge"] in local_semantic_judge.JUDGES:
        local_semantic_judge.qualification(calibration)
    if cases is not None:
        rules = calibration["cases"]
        if calibration["judge"] in local_semantic_judge.JUDGES:
            grounded_claims.validate_claim_rubrics(
                {
                    key: local_semantic_judge.claim_rubric(rule)
                    for key, rule in rules.items()
                },
                cases,
            )
        elif rules.keys() != {case["record_id"] for case in cases}:
            raise ValueError("experiment_calibration_coverage")
