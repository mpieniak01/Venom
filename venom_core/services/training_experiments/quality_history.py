"""Local read model combining imported and sealed Academy results."""

from __future__ import annotations

from .checkpoint_evaluation import RESULT_SEAL, step_directory
from .quality import QualityStore, analyze_quality
from .quality_native import HISTORY_PREFIX, get_record
from .service import ExperimentService


def list_records(experiments: ExperimentService) -> dict:
    imported, unavailable = QualityStore(experiments.root).list()
    records = [
        {**item, "record_id": HISTORY_PREFIX + item["record_id"]} for item in imported
    ]
    for run_id in experiments.store.ids():
        try:
            state = experiments.store.read(run_id)
            sealed = experiments.run_dir(run_id) / "result-seal.json"
            if state["profile_id"] == "historical" or not sealed.is_file():
                continue
            directory = experiments.run_dir(run_id)
            steps = state.get("checkpoint_steps")
            ids = (
                [
                    f"checkpoint:{run_id}:{step}"
                    for step in steps
                    if (step_directory(directory, step) / RESULT_SEAL).is_file()
                ]
                if steps is not None
                else [run_id]
            )
            records.extend(
                {
                    "record_id": record_id,
                    "split": "dev",
                    "outcome": None,
                    "source": {"identity": record_id},
                }
                for record_id in ids
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return {
        "records": [
            {key: value for key, value in record.items() if key != "cases"}
            for record in records
        ],
        "unavailable_record_ids": [HISTORY_PREFIX + key for key in unavailable],
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
