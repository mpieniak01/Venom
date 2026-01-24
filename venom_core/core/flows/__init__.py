"""Moduł: flows - Logika przepływów biznesowych."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from venom_core.core.flows.base import BaseFlow
    from venom_core.core.flows.campaign import CampaignFlow
    from venom_core.core.flows.code_review import CodeReviewLoop
    from venom_core.core.flows.council import CouncilFlow
    from venom_core.core.flows.forge import ForgeFlow
    from venom_core.core.flows.healing import HealingFlow
    from venom_core.core.flows.issue_handler import IssueHandlerFlow

__all__ = [
    "BaseFlow",
    "CampaignFlow",
    "CodeReviewLoop",
    "CouncilFlow",
    "ForgeFlow",
    "HealingFlow",
    "IssueHandlerFlow",
]


def __getattr__(name: str):
    module_map = {
        "BaseFlow": "venom_core.core.flows.base",
        "CampaignFlow": "venom_core.core.flows.campaign",
        "CodeReviewLoop": "venom_core.core.flows.code_review",
        "CouncilFlow": "venom_core.core.flows.council",
        "ForgeFlow": "venom_core.core.flows.forge",
        "HealingFlow": "venom_core.core.flows.healing",
        "IssueHandlerFlow": "venom_core.core.flows.issue_handler",
    }
    if name not in module_map:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_map[name])
    return getattr(module, name)
