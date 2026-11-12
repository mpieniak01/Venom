"""Local read model combining imported and sealed Academy results."""

from __future__ import annotations

from .quality import QualityStore, analyze_quality
from .quality_native import HISTORY_PREFIX, get_record
from .service import ExperimentService


def list_records(experiments: ExperimentService) -> dict:
    records = [
        {**item, "record_id": HISTORY_PREFIX + item["record_id"]}
        for item in QualityStore(experiments.root).list()
    ]
    for run_id in experiments.store.ids():
        try:
            state = experiments.store.read(run_id)
            sealed = experiments.run_dir(run_id) / "result-seal.json"
            if state["profile_id"] == "historical" or not sealed.is_file():
                continue
            records.append(
                {
                    "record_id": run_id,
                    "split": "dev",
                    "outcome": None,
                    "source": {"identity": run_id},
                }
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return {
        "records": [
            {key: value for key, value in record.items() if key != "cases"}
            for record in records
        ]
    }


def analyze_record(
    experiments: ExperimentService, record_id: str, reference_id: str | None
) -> dict:
    record = get_record(experiments, record_id)
    reference = get_record(experiments, reference_id) if reference_id else None
    result = analyze_quality(record, reference)
    result["record"]["record_id"] = record_id
    result["reference_id"] = reference_id
    if result["proposal"]["reference_id"] is not None:
        result["proposal"]["reference_id"] = reference_id
    return result
