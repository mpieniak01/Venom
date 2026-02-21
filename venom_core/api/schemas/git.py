"""Schemas for git API endpoints."""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class InitRepoRequest(BaseModel):
    """Payload dla inicjalizacji repozytorium."""

    url: Optional[str] = None


class GitStatusResponse(BaseModel):
    """Payload with current Git workspace status."""

    model_config = ConfigDict(extra="allow")

    status: str
    is_git_repo: bool
    message: str | None = None
    branch: str | None = None
    has_changes: bool | None = None
    modified_count: int | None = None
    status_output: str | None = None
    compare_branch: str | None = None
    compare_ref: str | None = None
    compare_status: str | None = None
    ahead_count: int | None = None
    behind_count: int | None = None
