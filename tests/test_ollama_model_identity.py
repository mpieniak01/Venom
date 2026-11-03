"""Observed Ollama tag identity; no model inference, activation or network."""

import copy

import pytest

from venom_core.core.model_manager_discovery import ModelManagerDiscoveryMixin
from venom_core.services.academy.trainable_catalog_service import (
    get_model_non_trainable_reason,
)
from venom_core.services.model_runtime_inventory import annotate_runtime_models
from venom_core.services.ollama_model_identity import (
    canonical_ollama_entries,
    ollama_display_name,
    resolve_ollama_model_name,
)


def item(name, digest="a" * 64, **details):
    return {
        "name": name,
        "digest": digest,
        "size": 100,
        "provider": "ollama",
        "details": {
            "family": "gemma4",
            "format": "gguf",
            "parameter_size": "8B",
            "quantization_level": "Q4_K_M",
            **details,
        },
    }


def test_only_proven_latest_duplicate_is_hidden_and_explicit_variants_survive():
    source = [
        item("gemma4:latest"),
        item("gemma4:e4b"),
        item("gemma4:12b-it-q4_K_M", "b" * 64, parameter_size="12B"),
    ]
    original = copy.deepcopy(source)
    rows = canonical_ollama_entries(source)
    assert source == original
    assert [r["name"] for r in rows] == ["gemma4:e4b", "gemma4:12b-it-q4_K_M"]
    assert [r["display_name"] for r in rows] == [
        "Gemma4 E4B IT Q4_K_M",
        "Gemma4 12B IT Q4_K_M",
    ]
    assert rows[0]["aliases"] == ["gemma4:latest"]
    assert resolve_ollama_model_name("gemma4:latest", rows) == "gemma4:e4b"


@pytest.mark.parametrize(
    "change",
    [
        {"digest": "b" * 64},
        {"digest": ""},
        {"digest": "x" * 64},
        {"details": {}},
        {"details": {"family": "gemma4"}},
    ],
)
def test_latest_without_complete_identity_proof_is_never_assigned_a_variant(change):
    latest = item("gemma4:latest")
    latest.update(change)
    rows = canonical_ollama_entries([latest, item("gemma4:e4b")])
    assert len(rows) == 2
    assert resolve_ollama_model_name("gemma4:latest", rows) == "gemma4:latest"


def test_ambiguous_same_digest_explicit_variants_are_both_preserved_without_guessing():
    rows = canonical_ollama_entries(
        [item("gemma4:latest"), item("gemma4:e4b"), item("gemma4:12b-it-q4_K_M")]
    )
    assert len(rows) == 3
    assert resolve_ollama_model_name("gemma4:latest", rows) == "gemma4:latest"


def test_stale_alias_is_not_used_when_current_latest_digest_changed():
    explicit = item("gemma4:e4b")
    explicit["aliases"] = ["gemma4:latest"]
    rows = canonical_ollama_entries([explicit, item("gemma4:latest", "b" * 64)])
    assert "gemma4:latest" not in rows[0]["aliases"]
    assert resolve_ollama_model_name("gemma4:latest", rows) == "gemma4:latest"


def test_discovery_preserves_explicit_tag_instead_of_preferring_latest_by_digest():
    manager = ModelManagerDiscoveryMixin()
    rows = manager._collect_ollama_entries(
        [
            item("gemma4:latest"),
            item("gemma4:e4b"),
            item("gemma4:12b-it-q4_K_M", "b" * 64, parameter_size="12B"),
        ]
    )
    assert {r["name"] for r in rows} == {"gemma4:e4b", "gemma4:12b-it-q4_K_M"}
    assert all(r["display_name"].startswith("Gemma4 ") for r in rows)
    annotate_runtime_models(
        rows,
        {"ollama": {"status": "online", "models": ["gemma4:latest"]}},
        "ollama",
        "gemma4:e4b",
    )
    e4b = next(r for r in rows if r["name"] == "gemma4:e4b")
    assert e4b["loaded"] is True and e4b["selected"] is True


def test_other_providers_and_names_are_not_canonicalized():
    row = item("gemma4:e4b")
    row["provider"] = "openrouter"
    row["aliases"] = ["gemma4:latest"]
    assert resolve_ollama_model_name("gemma4:latest", [row]) == "gemma4:latest"
    assert (
        resolve_ollama_model_name("qwen:latest", [item("qwen:latest")]) == "qwen:latest"
    )
    assert (
        ollama_display_name("gemma4:latest", "Q4_K_M")
        == "gemma4:latest (unresolved variant)"
    )


@pytest.mark.parametrize("model", ["google/gemma-4-E4B-it", "google/gemma-4-12B-it"])
def test_both_native_models_require_remote_qualification_in_academy(model):
    reason = get_model_non_trainable_reason(model, "huggingface")
    assert "remote host qualification" in reason


def test_runtime_catalog_propagates_explicit_display_label():
    from venom_core.api.routes.system_llm import _runtime_payload_or_audit_issue

    model = canonical_ollama_entries([item("gemma4:e4b")])[0]
    model.update(source="ollama", path="ollama://")
    payload, issue = _runtime_payload_or_audit_issue(
        model=model,
        grouped={"ollama": []},
        active_provider="ollama",
        active_model="gemma4:e4b",
    )
    assert issue is None
    assert payload["id"] == payload["name"] == "gemma4:e4b"
    assert payload["display_name"] == "Gemma4 E4B IT Q4_K_M"


def test_server_switch_resolves_only_proven_latest_to_explicit_request():
    from venom_core.api.routes.system_llm import (
        ActiveLlmServerRequest,
        _resolve_selected_model_for_switch,
    )

    rows = canonical_ollama_entries([item("gemma4:latest"), item("gemma4:e4b")])
    name, _ = _resolve_selected_model_for_switch(
        request=ActiveLlmServerRequest(server_name="ollama", model="gemma4:latest"),
        server_name="ollama",
        config={},
        models=rows,
    )
    assert name == "gemma4:e4b"


def test_flat_catalog_keeps_both_explicit_gemma_variants():
    from venom_core.api.routes.system_llm import _flatten_runtime_models

    rows = canonical_ollama_entries(
        [
            item("gemma4:latest"),
            item("gemma4:e4b"),
            item("gemma4:12b-it-q4_K_M", "b" * 64, parameter_size="12B"),
        ]
    )
    payloads = [dict(row, id=row["name"], runtime_id="ollama") for row in rows]
    flattened = _flatten_runtime_models([{"runtime_id": "ollama", "models": payloads}])
    assert {row["name"] for row in flattened} == {"gemma4:e4b", "gemma4:12b-it-q4_K_M"}


@pytest.mark.asyncio
async def test_registry_catalog_keeps_explicit_names_and_display_labels(monkeypatch):
    from venom_core.core.model_registry_providers import OllamaModelProvider

    async def tags():
        return {
            "models": [
                item("gemma4:latest"),
                item("gemma4:e4b"),
                item("gemma4:12b-it-q4_K_M", "b" * 64, parameter_size="12B"),
            ]
        }

    provider = OllamaModelProvider()
    monkeypatch.setattr(provider.client, "list_tags", tags)
    rows = await provider.list_available_models()
    assert {row.name for row in rows} == {"gemma4:e4b", "gemma4:12b-it-q4_K_M"}
    assert {row.display_name for row in rows} == {
        "Gemma4 E4B IT Q4_K_M",
        "Gemma4 12B IT Q4_K_M",
    }


def test_alias_list_without_digest_and_metadata_evidence_cannot_select_a_variant():
    explicit = item("gemma4:e4b")
    explicit["aliases"] = ["gemma4:latest"]
    assert resolve_ollama_model_name("gemma4:latest", [explicit]) == "gemma4:latest"


def test_alias_proof_becomes_invalid_if_explicit_digest_or_metadata_changes():
    rows = canonical_ollama_entries([item("gemma4:latest"), item("gemma4:e4b")])
    rows[0]["digest"] = "b" * 64
    assert resolve_ollama_model_name("gemma4:latest", rows) == "gemma4:latest"


@pytest.mark.parametrize("kind", ["missing", "ambiguous", "stale"])
def test_operator_selection_rejects_unproved_latest_instead_of_activating_it(kind):
    from fastapi import HTTPException

    from venom_core.api.routes.models_utils import resolve_ollama_selection

    rows = [item("gemma4:latest")]
    if kind == "ambiguous":
        rows += [item("gemma4:e4b"), item("gemma4:12b-it-q4_K_M")]
    if kind == "stale":
        explicit = item("gemma4:e4b", "b" * 64)
        explicit["aliases"] = ["gemma4:latest"]
        rows.append(explicit)
    # An observed unresolved active name is still representable read-only.
    assert resolve_ollama_model_name("gemma4:latest", rows) == "gemma4:latest"
    with pytest.raises(HTTPException) as error:
        resolve_ollama_selection("gemma4:latest", rows)
    assert error.value.status_code == 400
    assert "Choose gemma4:e4b" in error.value.detail["message"]


def test_strict_selection_still_accepts_proven_legacy_alias_and_other_models():
    from venom_core.api.routes.models_utils import resolve_ollama_selection

    rows = canonical_ollama_entries([item("gemma4:latest"), item("gemma4:e4b")])
    assert resolve_ollama_selection("gemma4:latest", rows) == "gemma4:e4b"
    assert resolve_ollama_selection("qwen:latest", []) == "qwen:latest"


@pytest.mark.asyncio
async def test_registry_servable_guard_rejects_unresolved_latest_before_activation(
    monkeypatch,
):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from venom_core.api.routes import models_registry_ops as ops

    async def models():
        return [item("gemma4:latest")]

    monkeypatch.setattr(
        ops, "get_model_manager", lambda: SimpleNamespace(list_local_models=models)
    )
    with pytest.raises(HTTPException) as error:
        await ops._ensure_runtime_model_is_servable(
            model_name="gemma4:latest", runtime="ollama"
        )
    assert error.value.status_code == 400
    assert "Choose" in error.value.detail["message"]


def test_unresolved_catalog_metadata_disables_selection_without_losing_observed_id():
    rows = canonical_ollama_entries([item("gemma4:latest")])
    assert rows[0]["name"] == "gemma4:latest"
    assert rows[0]["activation_supported"] is False
    assert rows[0]["selection_supported"] is False
    assert "unresolved" in rows[0]["display_name"]


def test_case_variant_cannot_bypass_strict_latest_guard_or_borrow_other_tag_proof():
    from fastapi import HTTPException

    from venom_core.api.routes.models_utils import resolve_ollama_selection

    rows = canonical_ollama_entries([item("gemma4:latest"), item("gemma4:e4b")])
    with pytest.raises(HTTPException) as error:
        resolve_ollama_selection("gemma4:Latest", rows)
    assert error.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("requested", ["gemma4:latest", None])
async def test_unresolved_requested_or_default_variant_fails_before_lifecycle(
    monkeypatch, requested
):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from venom_core.api.routes import system_llm as routes

    async def models():
        return [item("gemma4:latest")]

    controller = SimpleNamespace(
        list_servers=lambda: [{"name": "ollama"}],
        has_server=lambda name: name == "ollama",
    )
    manager = SimpleNamespace(list_local_models=models)
    monkeypatch.setattr(
        routes, "assert_runtime_switch_ownership_token", lambda token: None
    )
    monkeypatch.setattr(routes, "_ensure_server_allowed", lambda server: None)
    monkeypatch.setattr(routes, "_get_llm_controller_or_503", lambda: controller)
    monkeypatch.setattr(
        routes, "_validate_switch_dependencies", lambda: (None, manager, None)
    )
    monkeypatch.setattr(routes.system_deps, "get_request_tracer", lambda: None)
    monkeypatch.setattr(
        routes.config_manager,
        "get_config",
        lambda **kwargs: {
            "LAST_MODEL_OLLAMA": "gemma4:latest",
            "LLM_MODEL_NAME": "gemma4:latest",
        },
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "runtime lifecycle must not begin before identity acceptance"
        )

    monkeypatch.setattr(routes, "begin_runtime_switch", forbidden)
    request = routes.ActiveLlmServerRequest(server_name="ollama", model=requested)
    # Admission has its own tests. This unit verifies the guarded body before
    # any runtime switch gate, config write, shutdown or model activation.
    with pytest.raises(HTTPException) as error:
        await routes._set_active_llm_server_impl.__wrapped__(
            request=request,
            server_name="ollama",
            switch_source="test",
        )
    assert error.value.status_code == 400
    assert error.value.detail["code"] == "gemma4_variant_unresolved"


def test_saluki_is_resolved_only_from_identical_explicit_gguf_manifest_and_metadata():
    from venom_core.api.routes.models_utils import resolve_ollama_selection
    from venom_core.services.ollama_model_identity import SALUKI_ALIAS, SALUKI_GGUF

    rows = canonical_ollama_entries(
        [
            item(
                SALUKI_ALIAS,
                family="gemma3",
                parameter_size="27B",
                quantization_level="IQ2_XXS",
            ),
            item(
                SALUKI_GGUF,
                family="gemma3",
                parameter_size="27B",
                quantization_level="IQ2_XXS",
            ),
        ]
    )
    assert len(rows) == 1
    assert rows[0]["name"] == SALUKI_GGUF
    assert rows[0]["display_name"] == "Underdog Saluki 27B 1.0 IQ2-mix GGUF"
    assert resolve_ollama_selection(SALUKI_ALIAS, rows) == SALUKI_GGUF


def test_saluki_different_preset_or_projector_cannot_be_collapsed_by_filename():
    from venom_core.api.routes.models_utils import resolve_ollama_selection
    from venom_core.services.ollama_model_identity import SALUKI_ALIAS, SALUKI_GGUF

    source = [
        item(SALUKI_ALIAS, "b" * 64, family="gemma3"),
        item(SALUKI_GGUF, "a" * 64, family="gemma3"),
    ]
    before = copy.deepcopy(source)
    rows = canonical_ollama_entries(source)
    assert source == before
    assert len(rows) == 2
    unresolved = next(row for row in rows if row["name"] == SALUKI_ALIAS)
    assert unresolved["selection_supported"] is True
    assert "sha256:bbbbbbbb" in unresolved["display_name"]
    assert resolve_ollama_selection(SALUKI_ALIAS, rows) == SALUKI_ALIAS


def test_saluki_discovery_does_not_restore_old_latest_digest_preference():
    from venom_core.services.ollama_model_identity import SALUKI_ALIAS, SALUKI_GGUF

    manager = ModelManagerDiscoveryMixin()
    rows = manager._collect_ollama_entries(
        [
            item(SALUKI_ALIAS, family="gemma3"),
            item(SALUKI_GGUF, family="gemma3"),
            item("gemma4:e4b", "b" * 64),
            item("gemma4:12b-it-q4_K_M", "c" * 64),
        ]
    )
    assert {row["name"] for row in rows} == {
        SALUKI_GGUF,
        "gemma4:e4b",
        "gemma4:12b-it-q4_K_M",
    }
    assert (
        resolve_ollama_model_name(SALUKI_ALIAS, rows, require_explicit=True)
        == SALUKI_GGUF
    )


def test_saluki_missing_source_proof_and_unrelated_providers_are_kept_distinct():
    from fastapi import HTTPException

    from venom_core.api.routes.models_utils import resolve_ollama_selection
    from venom_core.services.ollama_model_identity import SALUKI_ALIAS

    unresolved = item(SALUKI_ALIAS)
    unresolved["provider"] = "openrouter"
    assert resolve_ollama_model_name(SALUKI_ALIAS, [unresolved]) == SALUKI_ALIAS
    with pytest.raises(HTTPException):
        resolve_ollama_selection(SALUKI_ALIAS, [])


def test_qwen_latest_maps_only_to_identical_explicit_tag_and_d1_keeps_observed_parent():
    from venom_core.services.ollama_model_identity import QWEN_ALIAS, QWEN_EXPLICIT

    rows = canonical_ollama_entries(
        [
            item(QWEN_ALIAS, family="qwen35", parameter_size="9B"),
            item(QWEN_EXPLICIT, family="qwen35", parameter_size="9B"),
            item(
                "d1:latest",
                "b" * 64,
                family="qwen2",
                parameter_size="2.7B",
                quantization_level="Q8_0",
                parent_model="d1:3b-q8_0",
            ),
        ]
    )
    assert {row["name"] for row in rows} == {QWEN_EXPLICIT, "d1:latest"}
    assert (
        resolve_ollama_model_name(QWEN_ALIAS, rows, require_explicit=True)
        == QWEN_EXPLICIT
    )
    d1 = next(row for row in rows if row["name"] == "d1:latest")
    assert "2.7B Q8_0" in d1["display_name"]
    assert "d1:3b-q8_0" in d1["display_name"]
    assert "sha256:bbbbbbbb" in d1["display_name"]
