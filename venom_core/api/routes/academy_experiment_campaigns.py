"""Academy campaign planning, observation and protected artifact retention."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from venom_core.api.routes.academy_experiments import (
    call_experiment,
    experiment_service,
    require_experiment_access,
)
from venom_core.services.training_experiments.campaign_schema import (
    CampaignId,
    CampaignPlanReference,
    CampaignSpec,
)
from venom_core.services.training_experiments.operator import campaign_service
from venom_core.services.training_experiments.optuna_backend import require_optuna
from venom_core.services.training_experiments.quality_history import (
    analyze_record,
    list_records,
)
from venom_core.services.training_experiments.quality_schema import EvidenceId
from venom_core.services.training_experiments.remote_text import (
    RemoteTextSpec,
    remote_text_service,
)

router = APIRouter(
    prefix="/api/v1/academy/experiments/campaigns",
    tags=["academy"],
    dependencies=[Depends(require_experiment_access)],
)


def _optuna_capability() -> dict:
    try:
        require_optuna()
    except ValueError as exc:
        return {"available": False, "reason": str(exc)}
    return {"available": True}


@router.get("")
def list_campaigns() -> dict:
    return call_experiment(
        lambda: {
            "campaigns": campaign_service().list(),
            "capabilities": {"optuna": _optuna_capability()},
        }
    )


@router.get("/quality")
def quality_records() -> dict:
    return call_experiment(list_records, experiment_service())


@router.get("/quality/{record_id}/analysis")
def quality_analysis(
    record_id: EvidenceId,
    reference_id: Annotated[EvidenceId | None, Query()] = None,
) -> dict:
    return call_experiment(
        analyze_record, experiment_service(), record_id, reference_id
    )


@router.post("/plan")
def plan_campaign(spec: CampaignSpec) -> dict:
    return call_experiment(campaign_service().plan, spec)


@router.get("/{campaign_id}")
def status(campaign_id: CampaignId) -> dict:
    return call_experiment(campaign_service().status, campaign_id)


@router.post("/{campaign_id}/start")
def start(campaign_id: CampaignId, body: CampaignPlanReference) -> dict:
    return call_experiment(campaign_service().start, campaign_id, body.plan_sha256)


@router.post("/{campaign_id}/stop")
def stop(campaign_id: CampaignId) -> dict:
    return call_experiment(campaign_service().stop, campaign_id)


@router.post("/{campaign_id}/resume")
def resume(campaign_id: CampaignId) -> dict:
    return call_experiment(campaign_service().resume, campaign_id)


@router.get("/{campaign_id}/report")
def report(campaign_id: CampaignId) -> dict:
    return call_experiment(campaign_service().report, campaign_id)


@router.get("/{campaign_id}/retention")
def retention_plan(campaign_id: CampaignId) -> dict:
    return call_experiment(campaign_service().retention_plan, campaign_id)


@router.post("/{campaign_id}/retention")
def retention_apply(campaign_id: CampaignId, body: CampaignPlanReference) -> dict:
    return call_experiment(
        campaign_service().retention_apply, campaign_id, body.plan_sha256
    )


remote_router = APIRouter(prefix="/remote/text")


@remote_router.get("")
def list_remote_text() -> dict:
    return call_experiment(lambda: {"campaigns": remote_text_service().list()})


@remote_router.post("/plan")
def plan_remote_text(spec: RemoteTextSpec) -> dict:
    return call_experiment(lambda: remote_text_service().plan(spec))


@remote_router.get("/{campaign_id}")
def status_remote_text(campaign_id: CampaignId) -> dict:
    return call_experiment(lambda: remote_text_service().status(campaign_id))


@remote_router.post("/{campaign_id}/start")
def start_remote_text(campaign_id: CampaignId, body: CampaignPlanReference) -> dict:
    return call_experiment(
        lambda: remote_text_service().start(campaign_id, body.plan_sha256)
    )


@remote_router.post("/{campaign_id}/stop")
def stop_remote_text(campaign_id: CampaignId) -> dict:
    return call_experiment(lambda: remote_text_service().stop(campaign_id))


@remote_router.get("/{campaign_id}/evidence/{run_id}", response_class=FileResponse)
def download_remote_text(campaign_id: CampaignId, run_id: str) -> FileResponse:
    def locate() -> dict:
        return {"path": remote_text_service().evidence_archive(campaign_id, run_id)}

    path = call_experiment(locate)["path"]
    return FileResponse(path, media_type="application/x-tar", filename=path.name)


router.include_router(remote_router)
