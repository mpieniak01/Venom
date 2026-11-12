"""Academy campaign planning, observation and protected artifact retention."""

from fastapi import APIRouter, Depends

from venom_core.api.routes.academy_experiments import (
    call_experiment,
    require_experiment_access,
)
from venom_core.services.training_experiments.campaign_schema import (
    CampaignId,
    CampaignPlanReference,
    CampaignSpec,
)
from venom_core.services.training_experiments.operator import campaign_service
from venom_core.services.training_experiments.optuna_backend import require_optuna

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
