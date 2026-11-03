"""Model-aware comparison contracts; no Torch, GPU or model execution."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.granite_operator import comparison, comparison_host, comparison_parallel
from scripts.granite_operator.comparison_support import (
    load_frozen,
    validate_case_images,
)
from venom_core.services.gemma4_operator.profile import GemmaProfile
from venom_core.services.gemma4_operator.training import GemmaTrainingRecipe
from venom_core.services.granite_operator.contract import (
    digest,
    file_digest,
    write_json,
)
from venom_core.services.remote_training import verification

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "Finish",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["status", "summary"],
            },
        },
    }
]
CALL = (
    '<|tool_call>call:Finish{status:<|"|>success<|"|>,summary:<|"|>ok<|"|>}<tool_call|>'
)


@pytest.fixture(params=["12b", "e4b"])
def selected(request):
    filename = (
        "gemma4_operator_profile.json"
        if request.param == "12b"
        else "gemma4_operator_e4b_profile.json"
    )
    profile = GemmaProfile.load(Path("config") / filename)
    files = dict(profile.files)
    files["chat_template.jinja"] = hashlib.sha256(b"fixture-template").hexdigest()
    profile = replace(profile, files=files)
    return profile, GemmaTrainingRecipe.for_profile(profile)


def test_backend_selects_the_bound_variant_without_loading_model(selected):
    profile, _ = selected
    session_type, owner, engine = verification.execution_backend(profile.model)
    assert session_type.__name__ == "GemmaSession"
    assert callable(owner)
    assert engine == "gemma-training"


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError, match="model_unsupported"):
        verification.execution_backend("gemma4:latest")


def test_gemma_generation_uses_native_renderer_and_profile_context(selected):
    profile, recipe = selected
    seen = []

    class Tokenizer:
        chat_template = "fixture-template"

        def apply_chat_template(self, messages, **options):
            seen.append(options)
            return "native " + profile.model

        def __call__(self, text, **options):
            assert text == "native " + profile.model
            assert options == {"add_special_tokens": False}
            return {"input_ids": [1, 2, 3]}

    session = SimpleNamespace(
        profile=recipe, gemma_profile=profile, tokenizer=Tokenizer()
    )
    messages = [{"role": "user", "content": "check"}]
    assert comparison.encode_prompt(session, messages, TOOLS) == [1, 2, 3]
    assert seen[0]["add_generation_prompt"] is True
    assert seen[0]["enable_thinking"] is False
    assert comparison.inference_settings(session)["context"] == profile.context
    calls = comparison.parse_calls(session, CALL, TOOLS)
    assert calls[0].arguments == {"status": "success", "summary": "ok"}


def test_scheduler_trial_proxy_preserves_native_parser_identity(selected):
    profile, recipe = selected
    session = SimpleNamespace(
        profile=recipe, gemma_profile=profile, comparison_protocol="gemma4"
    )
    scheduler = comparison_parallel.TaskScheduler(
        session,
        comparison_parallel.Execution(),
        batcher=lambda *_: [],
    )
    assert scheduler.trial_session.profile is recipe
    assert scheduler.trial_session.gemma_profile is profile
    assert (
        comparison.parse_calls(scheduler.trial_session, CALL, TOOLS)[0].name == "Finish"
    )


def test_inference_precision_does_not_change_training_recipe(selected):
    _, recipe = selected
    bf16 = comparison_host.inference_profile(recipe, "bf16")
    assert bf16.quantization == "bf16"
    assert recipe.quantization == "nf4"
    assert bf16.model == recipe.model
    assert bf16.revision == recipe.revision


@pytest.fixture
def artifact(selected, tmp_path, monkeypatch):
    from venom_core.services.gemma4_operator import encoding

    profile, recipe = selected
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    snapshot = tmp_path / recipe.revision
    snapshot.mkdir()
    (snapshot / "model.safetensors").write_bytes(b"native base")
    (adapter / "adapter_model.safetensors").write_bytes(b"adapter")
    document = {"model_profile": profile.identity(), "encoded_release_sha256": "a" * 64}
    write_json(adapter / "data-manifest.json", document)
    write_json(
        adapter / "environment.json",
        {
            "identity": {
                "weights": {
                    "model.safetensors": file_digest(snapshot / "model.safetensors")
                },
                "weights_index": None,
                "model_profile": profile.identity(),
                "recipe": recipe.identity(),
            }
        },
    )
    config = {
        "peft_type": "LORA",
        "task_type": "CAUSAL_LM",
        "r": recipe.rank,
        "lora_alpha": recipe.alpha,
        "lora_dropout": recipe.dropout,
        "bias": "none",
        "target_modules": recipe.identity()["target_modules"],
        "base_model_name_or_path": recipe.model,
    }
    write_json(adapter / "adapter_config.json", config)
    monkeypatch.setattr(GemmaProfile, "validate_snapshot", lambda *_: {})
    monkeypatch.setattr(encoding, "validate_encoded_release", lambda *_: {})
    monkeypatch.setattr(verification, "code_identity", lambda *a, **k: "b" * 64)
    monkeypatch.setattr(verification, "dependencies_identity", lambda *a, **k: "c" * 64)
    monkeypatch.setattr(
        verification, "tokenizer_identity", lambda *_: ("d" * 64, "e" * 64)
    )
    identity = {
        "model": recipe.model,
        "revision": recipe.revision,
        "profile_sha256": digest(recipe.identity()),
        "data_sha256": digest(document),
        "tokenizer_sha256": "d" * 64,
        "template_sha256": "e" * 64,
        "code_sha256": "b" * 64,
        "dependencies_sha256": "c" * 64,
        "encoding_sha256": "a" * 64,
    }
    host = {
        "snapshot": str(snapshot),
        "code_root": str(verification.native_code_root()),
    }
    return adapter, host, identity, recipe, config


def test_local_artifact_validation_accepts_correct_variant_without_activation(artifact):
    adapter, host, identity, recipe, _ = artifact
    actual, actual_recipe = verification._validate_gemma_local(
        adapter,
        host,
        identity,
        recipe.identity(),
    )
    assert actual == identity
    assert actual_recipe == recipe
    assert not (adapter / "local-verification.json").exists()


@pytest.mark.parametrize(
    "change", ["variant", "targets", "base_weights", "generation_config", "bias"]
)
def test_local_artifact_validation_rejects_wrong_native_identity(artifact, change):
    adapter, host, identity, recipe, config = artifact
    identity = copy.deepcopy(identity)
    if change == "variant":
        identity["model"] = "other-variant"
    elif change == "targets":
        config["target_modules"] = "all-linear"
        write_json(adapter / "adapter_config.json", config)
    elif change == "base_weights":
        (Path(host["snapshot"]) / "model.safetensors").write_bytes(b"changed base")
    elif change == "generation_config":
        write_json(
            Path(host["snapshot"]) / "generation_config.json", {"eos_token_id": 999}
        )
    else:
        config["bias"] = "all"
        write_json(adapter / "adapter_config.json", config)
    profile_data = recipe.identity()
    with pytest.raises(ValueError):
        verification._validate_gemma_local(adapter, host, identity, profile_data)


@pytest.fixture
def frozen_png(tmp_path):
    path = tmp_path / "square.png"
    path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8Dw"
            "HwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
        )
    )
    return path


def test_frozen_image_must_be_manifest_bound(frozen_png):
    path = frozen_png
    checksum = file_digest(path)
    case = {"images": [{"path": path.name, "sha256": checksum}]}
    validate_case_images(case, path.parent, {path.name: checksum})
    case["images"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="image_not_frozen"):
        validate_case_images(case, path.parent, {path.name: checksum})


class Payload(dict):
    def __init__(self):
        super().__init__(
            input_ids=SimpleNamespace(shape=(1, 5)),
            attention_mask="mask",
            pixel_values="pixels",
            image_position_ids="positions",
            mm_token_type_ids="types",
        )
        self.transfer = None

    def to(self, device, **options):
        self.transfer = (device, options)
        return self


def test_native_image_tensor_fields_reach_generate_on_same_adapter_model(
    selected, monkeypatch
):
    profile, recipe = selected
    payload = Payload()
    monkeypatch.setattr(comparison_parallel, "_image_payload", lambda *a: payload)
    calls = []
    disabled = []

    class Tokens(list):
        def tolist(self):
            return list(self)

    class Output:
        def __getitem__(self, selection):
            assert selection == (0, slice(5, None))
            return Tokens([10, 11])

    def generate(**kwargs):
        calls.append(kwargs)
        return Output()

    model = SimpleNamespace(
        named_parameters=lambda: [
            ("model.weight", SimpleNamespace(device=SimpleNamespace(type="cuda")))
        ],
        hf_device_map={"": 0},
        generate=generate,
        disable_adapter=lambda: disabled.append(True) or nullcontext(),
    )
    session = SimpleNamespace(
        profile=recipe,
        gemma_profile=profile,
        model=model,
        tokenizer=SimpleNamespace(
            pad_token_id=0,
            decode=lambda *a, **k: CALL,
            unk_token_id=-1,
            convert_tokens_to_ids=lambda token: {
                "<|tool_response>": 90,
                "<turn|>": 91,
                "<eos>": 92,
            }[token],
            convert_ids_to_tokens=lambda ident: {
                90: "<|tool_response>",
                91: "<turn|>",
                92: "<eos>",
            }[ident],
        ),
        torch=SimpleNamespace(
            bfloat16="bf16",
            inference_mode=nullcontext,
            cuda=SimpleNamespace(synchronize=lambda: None),
        ),
    )
    messages = [{"role": "user", "content": [{"type": "image", "path": "bound"}]}]
    result = comparison_parallel.generate_batch(
        session, [(messages, TOOLS, "base", float("inf"))]
    )
    assert len(disabled) == 1
    assert payload.transfer == ("cuda", {"dtype": "bf16"})
    assert calls[0]["eos_token_id"] == [90, 91, 92]
    assert calls[0]["pixel_values"] == "pixels"
    assert calls[0]["image_position_ids"] == "positions"
    assert calls[0]["mm_token_type_ids"] == "types"
    assert result[0]["modality"] == "image_text"
    assert result[0]["batch_size"] == 1


def test_images_are_cpu_preflighted_before_model_loading(
    selected, monkeypatch, tmp_path
):
    profile, recipe = selected
    write_json(tmp_path / "data-manifest.json", {"model_profile": profile.identity()})
    calls = []

    def prepare(probe, messages, tools):
        calls.append(messages)
        probe.processor = SimpleNamespace()
        return {"input_ids": SimpleNamespace(shape=(1, 8))}

    monkeypatch.setattr(comparison_parallel, "_image_payload", prepare)
    image = tmp_path / "square.png"
    image.write_bytes(b"fixture")
    cases = [
        {
            "system": "check",
            "prompt": "color?",
            "tools": TOOLS,
            "images": [{"path": image.name, "sha256": file_digest(image)}],
        }
    ]
    processor, evidence = comparison_host.image_preflight(
        recipe,
        tmp_path,
        tmp_path,
        cases,
        tmp_path,
    )
    assert processor is not None
    assert len(calls) == 1
    assert evidence["image_cases"] == 1
    assert evidence["gpu_qualified"] is False


def test_native_batch_overrides_unbound_eos_and_trims_at_tool_yield(selected):
    profile, recipe = selected
    calls = []
    mapping = {"<|tool_response>": 90, "<turn|>": 91, "<eos>": 92}

    class Batch(dict):
        def to(self, device):
            return self

    class Tokens(list):
        def tolist(self):
            return list(self)

    class Output:
        def __getitem__(self, selection):
            assert selection == (0, slice(2, None))
            return Tokens([7, 90, 999])

    class Tokenizer:
        chat_template = "fixture-template"
        padding_side = "right"
        pad_token_id = 0
        eos_token_id = 1
        unk_token_id = -1

        def apply_chat_template(self, messages, **kwargs):
            return "native"

        def __call__(self, text, **kwargs):
            return {"input_ids": [1, 2]}

        def convert_tokens_to_ids(self, token):
            return mapping[token]

        def convert_ids_to_tokens(self, ident):
            return next(token for token, value in mapping.items() if value == ident)

        def pad(self, *args, **kwargs):
            assert self.padding_side == "left"
            return Batch(input_ids=SimpleNamespace(shape=(1, 2)))

        def decode(self, tokens, **kwargs):
            assert tokens == [7, 90]
            return "trimmed"

    def generate(**kwargs):
        calls.append(kwargs)
        return Output()

    session = SimpleNamespace(
        profile=recipe,
        gemma_profile=profile,
        tokenizer=Tokenizer(),
        model=SimpleNamespace(
            named_parameters=lambda: [
                ("weight", SimpleNamespace(device=SimpleNamespace(type="cuda")))
            ],
            hf_device_map={"": 0},
            generation_config=SimpleNamespace(eos_token_id=[1]),
            disable_adapter=nullcontext,
            generate=generate,
        ),
        torch=SimpleNamespace(
            cuda=SimpleNamespace(synchronize=lambda: None),
            inference_mode=nullcontext,
        ),
    )
    messages = [{"role": "user", "content": "check"}]
    result = comparison_parallel.generate_batch(
        session,
        [(messages, TOOLS, "adapter", float("inf"))],
    )
    assert calls[0]["eos_token_id"] == [90, 91, 92]
    assert result[0]["tokens"] == 2
    assert result[0]["text"] == "trimmed"
    assert session.model.generation_config.eos_token_id == [1]


def test_native_stop_missing_from_bound_tokenizer_blocks_generation(selected):
    profile, recipe = selected
    session = SimpleNamespace(
        profile=recipe,
        gemma_profile=profile,
        tokenizer=SimpleNamespace(
            unk_token_id=-1,
            convert_tokens_to_ids=lambda token: -1,
            convert_ids_to_tokens=lambda ident: "<unk>",
        ),
    )
    with pytest.raises(ValueError, match="native_stop_tokens_invalid"):
        comparison.generation_options(session)


def test_image_warmup_covers_both_arms_outside_timing(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        comparison,
        "generate",
        lambda session, messages, tools, arm, deadline: calls.append((messages, arm)),
    )
    image = tmp_path / "image.png"
    image.write_bytes(b"fixture")
    case = {
        "system": "check",
        "prompt": "color?",
        "tools": TOOLS,
        "images": [{"path": image.name, "sha256": file_digest(image)}],
    }
    evidence = comparison_host.warmup_session(None, [case], tmp_path)
    assert evidence == {
        "generations": {"text": 4, "image_text": 4},
        "included_in_trial_timing": False,
    }
    assert [arm for _, arm in calls] == ["base", "adapter", "adapter", "base"] * 2
    assert isinstance(calls[4][0][1]["content"], list)


def test_remote_image_evaluation_fails_before_starting_paid_model(
    monkeypatch, tmp_path
):
    from scripts.granite_operator import remote_comparison

    monkeypatch.setattr(
        remote_comparison,
        "load_frozen",
        lambda path: ({}, [{"images": [{"path": "local.png", "sha256": "a" * 64}]}]),
    )
    created = []

    def forbidden(*args):
        created.append(True)
        raise AssertionError("remote provider must not start")

    options = SimpleNamespace(cases=tmp_path / "manifest.json")
    with pytest.raises(ValueError, match="remote_images_require_same_host_runner"):
        remote_comparison.evaluate(options, forbidden)
    assert created == []


@pytest.mark.parametrize("checksum", [None, "", "g" * 64, "a" * 63, False, "١" * 64])
def test_image_identity_rejects_invalid_hash_even_if_manifest_value_matches(
    frozen_png, checksum
):
    path = frozen_png
    case = {"images": [{"path": path.name, "sha256": checksum}]}
    with pytest.raises(ValueError, match="image_not_frozen"):
        validate_case_images(case, path.parent, {path.name: checksum})


def test_image_identity_requires_checksum_field(frozen_png):
    path = frozen_png
    case = {"images": [{"path": path.name}]}
    files = {path.name: file_digest(path)}
    with pytest.raises(ValueError, match="case_images_invalid"):
        validate_case_images(case, path.parent, files)


def test_unlisted_existing_image_with_null_hash_cannot_enter_frozen_cases(frozen_png):
    root = frozen_png.parent
    fixture = root / "fixture"
    fixture.mkdir()
    (fixture / "seed.txt").write_text("immutable", encoding="utf-8")
    case = {
        "id": "outside_image",
        "fixture": fixture.name,
        "images": [{"path": frozen_png.name, "sha256": None}],
    }
    cases = root / "cases.jsonl"
    cases.write_text(json.dumps(case) + "\n", encoding="utf-8")
    manifest = root / "manifest.json"
    write_json(
        manifest,
        {
            "cases": cases.name,
            "case_count": 1,
            "files": {
                cases.name: file_digest(cases),
                "fixture/seed.txt": file_digest(fixture / "seed.txt"),
            },
        },
    )
    with pytest.raises(ValueError, match="image_not_frozen"):
        load_frozen(manifest)
