from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from venom_core.services import gemma4_audio_models as models


def _settings(
    tmp_path: Path, *, cache_dir: str, repo_root: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        GEMMA4_AUDIO_CACHE_DIR=cache_dir,
        REPO_ROOT=str(repo_root or tmp_path),
    )


def test_resolve_cache_root_uses_absolute_cache_dir(tmp_path: Path) -> None:
    absolute_cache = tmp_path / "abs-cache"
    settings = _settings(tmp_path, cache_dir=str(absolute_cache))
    assert models._resolve_cache_root(settings_obj=settings) == absolute_cache.resolve()  # noqa: SLF001


def test_resolve_cache_root_uses_repo_root_for_relative_cache_dir(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    settings = _settings(
        tmp_path, cache_dir="models_cache/hf", repo_root=str(repo_root)
    )
    assert (
        models._resolve_cache_root(settings_obj=settings)
        == (repo_root / "models_cache/hf").resolve()
    )  # noqa: SLF001


def test_resolve_repo_snapshot_dir_rejects_invalid_model_id() -> None:
    assert models._resolve_repo_snapshot_dir("invalid-model-id") == Path("__invalid__")  # noqa: SLF001


def test_gemma4_audio_model_has_snapshot_false_when_snapshots_missing(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, cache_dir=str(tmp_path / "hf"))
    assert (
        models.gemma4_audio_model_has_snapshot(
            "google/gemma-4-E2B-it", settings_obj=settings
        )
        is False
    )


def test_gemma4_audio_model_has_snapshot_true_with_config_json(tmp_path: Path) -> None:
    cache_root = tmp_path / "hf"
    snapshot_dir = (
        cache_root / "models--google--gemma-4-E2B-it" / "snapshots" / "snapshot-1"
    )
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "config.json").write_text("{}", encoding="utf-8")
    settings = _settings(tmp_path, cache_dir=str(cache_root))

    assert (
        models.gemma4_audio_model_has_snapshot(
            "google/gemma-4-E2B-it", settings_obj=settings
        )
        is True
    )


def test_gemma4_audio_available_models_filters_by_role_and_cache(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "hf"
    target_snapshot = (
        cache_root / "models--google--gemma-4-E2B-it" / "snapshots" / "target"
    )
    assistant_snapshot = (
        cache_root
        / "models--google--gemma-4-E2B-it-assistant"
        / "snapshots"
        / "assistant"
    )
    target_snapshot.mkdir(parents=True)
    assistant_snapshot.mkdir(parents=True)
    (target_snapshot / "config.json").write_text("{}", encoding="utf-8")
    (assistant_snapshot / "config.json").write_text("{}", encoding="utf-8")
    settings = _settings(tmp_path, cache_dir=str(cache_root))

    assert models.gemma4_audio_available_models(
        role="target", settings_obj=settings
    ) == ["google/gemma-4-E2B-it"]
    assert models.gemma4_audio_available_models(
        role="assistant", settings_obj=settings
    ) == ["google/gemma-4-E2B-it-assistant"]
