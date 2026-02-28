"""Environment isolation and destructive-operation guard rails."""

from __future__ import annotations

from dataclasses import dataclass

from venom_core.config import SETTINGS


@dataclass(frozen=True)
class EnvironmentPolicy:
    environment_role: str
    db_schema: str
    cache_namespace: str
    queue_namespace: str
    storage_prefix: str
    allow_data_mutation: bool

    @property
    def is_preprod(self) -> bool:
        return self.environment_role == "preprod"


def _normalize_role(raw: str) -> str:
    role = (raw or "").strip().lower()
    if role in {"preprod", "pre-prod", "pre_prod", "staging", "stage"}:
        return "preprod"
    return "dev"


def get_environment_policy() -> EnvironmentPolicy:
    return EnvironmentPolicy(
        environment_role=_normalize_role(getattr(SETTINGS, "ENVIRONMENT_ROLE", "dev")),
        db_schema=(getattr(SETTINGS, "DB_SCHEMA", "") or "").strip().lower(),
        cache_namespace=(getattr(SETTINGS, "CACHE_NAMESPACE", "") or "").strip(),
        queue_namespace=(getattr(SETTINGS, "QUEUE_NAMESPACE", "") or "").strip(),
        storage_prefix=(getattr(SETTINGS, "STORAGE_PREFIX", "") or "").strip("/"),
        allow_data_mutation=bool(getattr(SETTINGS, "ALLOW_DATA_MUTATION", False)),
    )


def validate_environment_policy() -> None:
    """Fail-fast on invalid preprod isolation configuration."""
    policy = get_environment_policy()
    if not policy.is_preprod:
        return

    problems: list[str] = []
    if policy.db_schema != "preprod":
        problems.append("DB_SCHEMA musi być ustawione na 'preprod'")
    if policy.cache_namespace != "preprod":
        problems.append("CACHE_NAMESPACE musi być ustawione na 'preprod'")
    if policy.queue_namespace != "preprod":
        problems.append("QUEUE_NAMESPACE musi być ustawione na 'preprod'")
    if policy.storage_prefix != "preprod":
        problems.append("STORAGE_PREFIX musi być ustawione na 'preprod'")

    if problems:
        details = "; ".join(problems)
        raise RuntimeError(f"Niepoprawna konfiguracja pre-prod: {details}")


def ensure_data_mutation_allowed(operation_name: str) -> None:
    """Block destructive operations in preprod unless override is explicitly enabled."""
    policy = get_environment_policy()
    if policy.is_preprod and not policy.allow_data_mutation:
        raise PermissionError(
            f"Operacja '{operation_name}' jest zablokowana na pre-prod "
            "(ALLOW_DATA_MUTATION=0)."
        )
