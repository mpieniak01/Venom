"""Academy routes for the shared local experiment controller."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from venom_core.api.transport_access import is_localhost_request
from venom_core.config import SETTINGS
from venom_core.services.training_experiments.service import ExperimentService

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"


class StartExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    profile_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    recipe: dict[str, Any] | None = None


class Judgment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    record_id: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=8)
    criteria: dict[str, bool]
    polish_ok: bool
    natural_ok: bool
    critical_error: bool
    reason: str = Field(min_length=1, max_length=4000)


class SubmitJudgments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    judgments: list[Judgment] = Field(min_length=1, max_length=2048)


def require_experiment_access(request: Request) -> None:
    if not is_localhost_request(request):
        raise HTTPException(
            status_code=403, detail={"code": "experiment_localhost_required"}
        )
    if not SETTINGS.ENABLE_ACADEMY:
        raise HTTPException(
            status_code=503, detail={"code": "experiment_academy_disabled"}
        )


router = APIRouter(
    prefix="/api/v1/academy/experiments",
    tags=["academy"],
    dependencies=[Depends(require_experiment_access)],
)


def experiment_service() -> ExperimentService:
    return ExperimentService(Path(SETTINGS.ACADEMY_TRAINING_DIR) / "experiments")


def call_experiment(operation: Callable[..., dict], *args, **kwargs) -> dict:
    try:
        return operation(*args, **kwargs)
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail={"code": "experiment_mutation_denied"}
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "experiment_input_missing"}
        ) from exc
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        reason = str(exc)
        code = (
            reason
            if reason.startswith("experiment_") and reason.isidentifier()
            else "experiment_invalid_request"
        )
        raise HTTPException(status_code=409, detail={"code": code}) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503, detail={"code": "experiment_storage_unavailable"}
        ) from exc


@router.get("/profiles")
def profiles() -> dict:
    return call_experiment(lambda: {"profiles": experiment_service().profiles()})


@router.get("/runs")
def runs() -> dict:
    return call_experiment(lambda: {"runs": experiment_service().list_runs()})


@router.post("/runs")
def start_run(body: StartExperiment) -> dict:
    return call_experiment(
        experiment_service().start, body.profile_id, body.run_id, body.recipe
    )


@router.get("/runs/{run_id}")
def run_status(run_id: str) -> dict:
    return call_experiment(experiment_service().status, run_id)


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str) -> dict:
    return call_experiment(experiment_service().stop, run_id)


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: str) -> dict:
    return call_experiment(experiment_service().resume, run_id)


@router.post("/runs/{run_id}/evaluate")
def retry_evaluation(run_id: str) -> dict:
    return call_experiment(experiment_service().evaluate, run_id)


@router.get("/runs/{run_id}/logs")
def logs(run_id: str) -> dict:
    return call_experiment(experiment_service().logs, run_id)


@router.get("/runs/{run_id}/review")
def review(run_id: str) -> dict:
    return call_experiment(experiment_service().review, run_id)


@router.post("/runs/{run_id}/judgments")
def submit_judgments(run_id: str, body: SubmitJudgments) -> dict:
    return call_experiment(
        experiment_service().submit,
        run_id,
        [grade.model_dump() for grade in body.judgments],
    )


@router.get("/runs/{run_id}/report")
def report(run_id: str) -> dict:
    return call_experiment(experiment_service().report, run_id)
