"""Typed operator commands for the Academy campaign tools."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from venom_core.config import SETTINGS
from venom_core.services.training_experiments.campaign_schema import CampaignSpec

if TYPE_CHECKING:
    from venom_core.services.training_experiments.campaign import CampaignService

_ACTIONS = (
    "plan",
    "validate",
    "start",
    "status",
    "stop",
    "resume",
    "compare",
    "report",
)
_TUNING_KEYS = {"rank", "alpha", "learning_rate", "dropout"}
_MAX_COMMAND_SIZE = 32_768
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")
_DIGEST = re.compile(r"[a-f0-9]{64}")
_PREFIX = re.compile(r"^[ \t]*/academy(?:\s|$)")


@dataclass(frozen=True)
class CampaignCommand:
    """Parsed from the operator's original, authenticated chat turn."""

    action: str
    campaign_id: str = ""
    plan_sha256: str = ""
    spec: CampaignSpec | None = None


def is_campaign_command(text: str) -> bool:
    return _PREFIX.match(text) is not None


def _plan_command(action: str, argument: str) -> CampaignCommand:
    spec = CampaignSpec.model_validate_json(argument)
    if any(variant.keys() - _TUNING_KEYS for variant in spec.variants):
        raise ValueError("campaign_parameter_unsupported")
    return CampaignCommand(action, campaign_id=spec.campaign_id, spec=spec)


def parse_campaign_command(text: str) -> CampaignCommand:
    if not is_campaign_command(text) or len(text) > _MAX_COMMAND_SIZE:
        raise ValueError("campaign_command_invalid")
    tokens = text.split(maxsplit=2)
    if len(tokens) == 1:
        return CampaignCommand("help")
    action = tokens[1]
    if action not in _ACTIONS or len(tokens) != 3:
        raise ValueError("campaign_command_invalid")
    argument = tokens[2]
    if action in {"plan", "validate"}:
        return _plan_command(action, argument)
    parts = argument.split()
    if len(parts) != (2 if action == "start" else 1) or not _ID.fullmatch(parts[0]):
        raise ValueError("campaign_command_invalid")
    if action == "start" and not _DIGEST.fullmatch(parts[1]):
        raise ValueError("campaign_command_invalid")
    return CampaignCommand(action, parts[0], parts[1] if action == "start" else "")


def campaign_service() -> CampaignService:
    from venom_core.services.training_experiments.campaign import CampaignService
    from venom_core.services.training_experiments.service import ExperimentService

    return CampaignService(
        ExperimentService(Path(SETTINGS.ACADEMY_TRAINING_DIR) / "experiments")
    )


class AcademyCampaignAdapter:
    """Expose bounded operations through SkillManager to an authorized operator turn."""

    @staticmethod
    def list_tools() -> tuple[str, ...]:
        return _ACTIONS

    async def invoke_tool(self, tool_name: str, arguments: dict) -> dict:
        command = arguments.get("command")
        if (
            not isinstance(command, CampaignCommand)
            or command.action != tool_name
            or tool_name not in _ACTIONS
        ):
            raise PermissionError("campaign_operator_command_required")
        return await asyncio.to_thread(self._execute, command)

    @staticmethod
    def _execute(command: CampaignCommand) -> dict:
        if not SETTINGS.ENABLE_ACADEMY:
            raise ValueError("experiment_academy_disabled")
        service = campaign_service()
        action = command.action
        if action in {"plan", "validate"}:
            if command.spec is None:
                raise ValueError("campaign_command_invalid")
            plan = (
                service.plan(command.spec)["plan"]
                if action == "plan"
                else service.validate(command.spec)
            )
            profile = next(
                (
                    profile
                    for profile in service.experiments.profiles()
                    if profile["id"] == plan["profile_id"]
                    and profile["identity"] == plan["profile_identity"]
                ),
                {},
            )
            return {
                "plan": plan,
                "model": profile.get("model"),
                "dataset": profile.get("dataset"),
            }
        if action == "start":
            return {"state": service.start(command.campaign_id, command.plan_sha256)}
        if action == "stop":
            return {"state": service.stop(command.campaign_id)}
        if action == "resume":
            return {"state": service.resume(command.campaign_id)}
        if action in {"compare", "report"}:
            state = service.report(command.campaign_id)
            return {"state": state, "evaluations": service.evaluations(state)}
        return {"state": service.status(command.campaign_id)}


_TEXT = {
    "pl": {
        "help": "Użyj komendy Academy w czacie.",
        "failure": "Academy nie wykonała polecenia",
        "plan": "Zapisany plan",
        "validate": "Poprawny plan roboczy",
        "confirm": "Po sprawdzeniu zakresu i budżetu uruchom kampanię tym poleceniem.",
        "profile": "Profil",
        "limits": "Limity",
        "candidate_recipe": "Receptura do potwierdzenia w nowej kampanii",
        "execution": "Identyfikator wykonania",
        "state": "Stan",
        "progress": "Próby ukończone",
        "selected": "Wybrany kandydat",
        "resources": "Sekundy · aktualizacje · tokeny · ponowienia · bajty artefaktów",
        "panel": "Otwórz kampanię w Academy",
        "missing": "brak danych",
        "available": "dostępny",
        "removed": "niedostępny",
        "comparison": "Próba | Stan | Użyteczne (baza → adapter) | Krytyczne (baza → adapter) | Wniosek | Adapter",
        "improvement": "poprawa",
        "regression": "regresja",
        "unchanged": "bez różnicy",
        "uncertainty": "Wnioski opisują próbki dev. Potwierdzenie wymaga drugiego ziarna i niezależnego zestawu.",
    },
    "en": {
        "help": "Use an Academy command in chat.",
        "failure": "Academy could not run the command",
        "plan": "Saved plan",
        "validate": "Validated draft plan",
        "confirm": "Review the scope and budget, then start the campaign with this command.",
        "profile": "Profile",
        "limits": "Limits",
        "candidate_recipe": "Recipe to confirm in a new campaign",
        "execution": "Execution ID",
        "state": "State",
        "progress": "Trials processed",
        "selected": "Selected candidate",
        "resources": "Seconds · updates · tokens · retries · artifact bytes",
        "panel": "Open campaign in Academy",
        "missing": "unavailable",
        "available": "available",
        "removed": "unavailable",
        "comparison": "Trial | State | Usable (base → adapter) | Critical (base → adapter) | Result | Adapter",
        "improvement": "improvement",
        "regression": "regression",
        "unchanged": "unchanged",
        "uncertainty": "Findings describe the dev samples. Confirmation requires a second seed and an independent set.",
    },
    "de": {
        "help": "Verwende einen Academy-Befehl im Chat.",
        "failure": "Academy konnte den Befehl nicht ausführen",
        "plan": "Gespeicherter Plan",
        "validate": "Validierter Planentwurf",
        "confirm": "Prüfe Umfang und Budget und starte die Kampagne mit diesem Befehl.",
        "profile": "Profil",
        "limits": "Grenzwerte",
        "candidate_recipe": "Rezept zur Bestätigung in einer neuen Kampagne",
        "execution": "Ausführungs-ID",
        "state": "Status",
        "progress": "Bearbeitete Versuche",
        "selected": "Ausgewählter Kandidat",
        "resources": "Sekunden · Updates · Token · Wiederholungen · Artefaktbytes",
        "panel": "Kampagne in Academy öffnen",
        "missing": "keine Daten",
        "available": "verfügbar",
        "removed": "nicht verfügbar",
        "comparison": "Versuch | Status | Brauchbar (Basis → Adapter) | Kritisch (Basis → Adapter) | Ergebnis | Adapter",
        "improvement": "Verbesserung",
        "regression": "Verschlechterung",
        "unchanged": "unverändert",
        "uncertainty": "Die Ergebnisse beziehen sich auf die Dev-Stichprobe. Zur Bestätigung sind ein zweiter Seed und ein unabhängiger Datensatz erforderlich.",
    },
}


def _labels(language: str | None) -> dict[str, str]:
    return _TEXT.get(language or "pl", _TEXT["pl"])


def campaign_error(language: str | None, error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        reason = "campaign_evidence_missing"
    elif isinstance(error, PermissionError):
        reason = "campaign_operation_denied"
    else:
        detail = str(error)
        reason = (
            detail
            if re.fullmatch(r"(?:campaign|experiment)_[a-z0-9_]+", detail)
            else "campaign_command_invalid"
        )
    return f"{_labels(language)['failure']} (`{reason}`)."


def campaign_help(language: str | None) -> str:
    return (
        f"{_labels(language)['help']}\n\n"
        "`/academy validate <JSON>` · `/academy plan <JSON>`\n\n"
        "`/academy start <id> <plan_sha256>`\n\n"
        "`/academy status <id>` · `/academy stop <id>` · `/academy resume <id>`\n\n"
        "`/academy compare <id>` · `/academy report <id>`"
    )


def _plan_text(action: str, result: dict, labels: dict[str, str]) -> str:
    plan = result["plan"]
    campaign_id = plan["campaign_id"]
    digest = plan["plan_sha256"]
    details = {
        "strategy": plan.get("strategy", "fixed"),
        "objective": "dev_usable_delta",
        "model": result["model"],
        "dataset": result["dataset"],
        "review_mode": plan["review_mode"],
        "budget": plan["budget"],
        "selection": plan["selection"],
        "retention": plan["retention"],
    }
    if details["strategy"] == "optuna":
        details.update(
            base_recipe=plan["variants"][0]["recipe"],
            search_space=plan["search_space"],
            sampler_seed=plan["sampler_seed"],
        )
    else:
        details["variants"] = [row["recipe"] for row in plan["variants"]]
    text = (
        f"**{labels[action]}** `{campaign_id}`\n\n"
        f"{labels['profile']} `{plan['profile_id']}`\n\n"
        f"```json\n{json.dumps(details, ensure_ascii=False, indent=2)}\n```"
    )
    if action == "plan":
        text += (
            f"\n\n[{labels['panel']}](/academy?campaign={campaign_id})"
            f"\n\n{labels['confirm']}\n\n`/academy start {campaign_id} {digest}`"
        )
    return text


def _summary(state: dict, labels: dict[str, str]) -> str:
    campaign_id = state["campaign_id"]
    used = (
        f"{state['elapsed_seconds']:.1f} · {state['used_updates']} · "
        f"{state['used_tokens']} · {state['retries']} · {state['artifact_bytes']}"
    )
    text = (
        f"**{labels['execution']}** `{campaign_id}` · **{labels['state']}** "
        f"`{state['status']}` · {labels['progress']} "
        f"{state['trial_index']}/{len(state['trials'])}\n\n"
        f"[{labels['panel']}](/academy?campaign={campaign_id})\n\n"
        f"{labels['resources']}\n\n{used}\n\n"
        f"{labels['selected']} `{state['selected_run_id'] or labels['missing']}`"
    )
    if state.get("error"):
        text += f"\n\n`{state['error']}`"
    return text


def _comparison_row(trial: dict, data: dict, labels: dict[str, str]) -> str:
    missing = labels["missing"]
    run_id, status = trial["run_id"], trial["status"]
    artifact = data.get("adapter_available")
    available = (
        missing if artifact is None else labels["available" if artifact else "removed"]
    )
    if "base" not in data:
        return f"| `{run_id}` | `{status}` | {missing} | {missing} | {missing} | {available} |"
    base, candidate = data["base"], data["candidate"]
    n = base["n"]
    usable = f"{base['usable']}/{n} → {candidate['usable']}/{n}"
    critical = f"{base['critical']}/{n} → {candidate['critical']}/{n}"
    outcome = "unchanged"
    if candidate["critical"] > base["critical"] or candidate["usable"] < base["usable"]:
        outcome = "regression"
    elif (
        candidate["usable"] > base["usable"] or candidate["critical"] < base["critical"]
    ):
        outcome = "improvement"
    return f"| `{run_id}` | `{status}` | {usable} | {critical} | {labels[outcome]} | {available} |"


def _confirmation_recipe(state: dict, evaluations: dict) -> dict | None:
    selected = state["selected_run_id"]
    evidence = evaluations.get(selected, {})
    if not evidence.get("adapter_available"):
        return None
    base, candidate = evidence["base"], evidence["candidate"]
    if (
        candidate["usable"] <= base["usable"]
        or candidate["critical"] > base["critical"]
    ):
        return None
    for trial, variant in zip(state["trials"], state["plan"]["variants"], strict=True):
        if trial["run_id"] == selected:
            recipe = trial.get("recipe") or variant["recipe"]
            return {name: recipe[name] for name in sorted(_TUNING_KEYS & recipe.keys())}
    return None


def render_campaign_result(action: str, result: dict, language: str | None) -> str:
    labels = _labels(language)
    if "plan" in result:
        return _plan_text(action, result, labels)
    state = result["state"]
    text = _summary(state, labels)
    if "evaluations" not in result:
        return text
    evaluations = result["evaluations"]
    rows = [
        _comparison_row(trial, evaluations.get(trial["run_id"], {}), labels)
        for trial in state["trials"]
    ]
    table = [
        f"| {labels['comparison']} |",
        "| --- | --- | --- | --- | --- | --- |",
        *rows,
    ]
    if action == "report":
        text += f"\n\n**{labels['limits']}**\n\n`{json.dumps(state['plan']['budget'])}`"
    sections = [text, "\n".join(table), labels["uncertainty"]]
    recipe = _confirmation_recipe(state, evaluations)
    if recipe:
        sections.append(f"{labels['candidate_recipe']} `{json.dumps(recipe)}`")
    return "\n\n".join(sections)
