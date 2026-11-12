"""Local read model combining imported and sealed Academy results."""

from __future__ import annotations

from .quality import QualityStore, analyze_quality
from .quality_native import get_record
from .service import ExperimentService


def list_records(experiments: ExperimentService) -> dict:
    records = {
        item["record_id"]: item for item in QualityStore(experiments.root).list()
    }
    for run_id in experiments.store.ids():
        if run_id in records:
            continue
        try:
            state = experiments.store.read(run_id)
            if state["status"] != "succeeded" or state["profile_id"] == "historical":
                continue
            records[run_id] = {
                "record_id": run_id,
                "split": "dev",
                "outcome": None,
                "source": {"identity": run_id},
            }
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return {
        "records": [
            {key: value for key, value in record.items() if key != "cases"}
            for record in records.values()
        ]
    }


def analyze_record(
    experiments: ExperimentService, record_id: str, reference_id: str | None
) -> dict:
    record = get_record(experiments, record_id)
    reference = get_record(experiments, reference_id) if reference_id else None
    return analyze_quality(record, reference)
