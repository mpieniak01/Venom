"""Native token boundaries, loss isolation and sealed vector integrity on CPU."""

import copy
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from venom_core.services.gemma4_operator.data_release import build_release
from venom_core.services.gemma4_operator.encoding import (
    encode_release,
    validate_encoded_release,
)
from venom_core.services.gemma4_operator.material import digest
from venom_core.services.gemma4_operator.profile import (
    E4B_LOADER,
    E4B_MODEL,
    LOADER,
    MODEL,
    SNAPSHOT_FILES,
    GemmaProfile,
)
from venom_core.services.gemma4_operator.protocol import STOP_SEQUENCES


class NativeTokenizerDouble:
    """Deterministic tokenization double; real-tokenizer qualification is separate."""

    is_fast = True
    chat_template = "native-test-template"

    def __init__(self, snapshot):
        self.name_or_path = str(snapshot)
        self.backend_tokenizer = SimpleNamespace(to_str=lambda: '{"fixture":true}')
        self.special = {value: index + 1 for index, value in enumerate(STOP_SEQUENCES)}

    def __len__(self):
        return 300000

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs["tokenize"] is False
        assert kwargs["preserve_thinking"] is False
        result = "BEGIN\n"
        previous = None
        for index, message in enumerate(messages):
            body = message.get("content") or ""
            if message.get("tool_calls"):
                body += json.dumps(message["tool_calls"], sort_keys=True)
            role = message["role"]
            following = next(
                (m for m in messages[index + 1 :] if m["role"] != "tool"), None
            )
            continued = (
                role == "assistant"
                and not message.get("tool_calls")
                and following is not None
                and following["role"] == "assistant"
            )
            header = "" if role == previous == "assistant" else role + "\n"
            result += header + body + ("" if continued else "<turn|>\n")
            if role != "tool":
                previous = role
        return result

    def convert_tokens_to_ids(self, token):
        return self.special.get(token)

    def __call__(self, text, **kwargs):
        assert kwargs == {
            "add_special_tokens": False,
            "return_offsets_mapping": True,
            "truncation": False,
        }
        ids, offsets = [], []
        cursor = 0
        while cursor < len(text):
            special = next(
                (s for s in self.special if text.startswith(s, cursor)), None
            )
            length = len(special) if special else 1
            ids.append(self.special[special] if special else ord(text[cursor]) + 10)
            offsets.append((cursor, cursor + length))
            cursor += length
        return {"input_ids": ids, "offset_mapping": offsets}

    def decode(self, ids, **kwargs):
        inverse = {value: key for key, value in self.special.items()}
        return "".join(
            inverse[value] if value in inverse else chr(value - 10) for value in ids
        )


def row(split):
    return {
        "record_id": split + "-record",
        "problem_group": split + "-group",
        "language": "en",
        "split": split,
        "training_allowed": split == "train",
        "tools": [],
        "messages": [
            {"role": "user", "content": split + " independent incident"},
            {"role": "assistant", "content": "wrong response"},
            {"role": "user", "content": "Use the corrected observation"},
            {"role": "assistant", "content": "The verified correction"},
        ],
        "supervised_assistant_indices": [3],
        "context_only_assistant_indices": [1],
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA_OPERATOR_DATA_ROOT", str(tmp_path))
    snapshot = tmp_path / "native"
    snapshot.mkdir()
    files = {name: "{}" for name in SNAPSHOT_FILES}
    files.update(
        {
            "config.json": json.dumps(
                {
                    "architectures": [LOADER],
                    "text_config": {"max_position_embeddings": 4096},
                }
            ),
            "tokenizer.json": '{"fixture":true}',
            "chat_template.jinja": NativeTokenizerDouble.chat_template,
        }
    )
    for name, content in files.items():
        (snapshot / name).write_text(content)
    profile = GemmaProfile(
        model=MODEL,
        loader=LOADER,
        context=4096,
        enable_thinking=False,
        revision="a" * 40,
        files={
            name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in files.items()
        },
    )
    release = build_release(
        {name: [row(name)] for name in ("train", "validation", "holdout")}, profile
    )
    return profile, NativeTokenizerDouble(snapshot), release


def rehash(document):
    for rows in document["records"].values():
        for record in rows:
            record["sequence_sha256"] = digest(
                {
                    key: value
                    for key, value in record.items()
                    if key != "sequence_sha256"
                }
            )
    for split, rows in document["records"].items():
        document["split_summary"][split] = {
            "records": len(rows),
            "tokens": sum(len(record["input_ids"]) for record in rows),
            "supervised_tokens": sum(
                sum(value != -100 for value in record["labels"]) for record in rows
            ),
            "records_sha256": digest(rows),
        }
    document["encoded_release_sha256"] = digest(
        {
            key: value
            for key, value in document.items()
            if key != "encoded_release_sha256"
        }
    )


def test_selective_loss_preserves_exact_native_boundaries_and_stops(setup):
    profile, tokenizer, release = setup
    original = copy.deepcopy(release)
    encoded = encode_release(release, tokenizer, profile)
    assert encode_release(release, tokenizer, profile) == encoded
    assert release == original
    assert set(encoded["records"]) == {"train", "validation"}
    assert release["evaluation_reserve"]["records"] == 1
    record = encoded["records"]["train"][0]
    assert record["supervised_assistant_indices"] == [3]
    assert [span["supervised"] for span in record["assistant_token_spans"]] == [
        False,
        True,
    ]
    first, selected = record["assistant_token_spans"]
    assert set(record["labels"][first["start"] : first["end"]]) == {-100}
    assert (
        record["labels"][selected["start"] : selected["end"]]
        == record["input_ids"][selected["start"] : selected["end"]]
    )
    assert selected["stop_token_id"] in record["labels"]
    assert record["labels"][0] == -100
    assert encoded["packing"]["enabled"] is False
    assert encoded["training_ready"] is False
    assert validate_encoded_release(encoded, profile) == encoded["records"]


def test_unselected_tool_calls_and_tool_results_never_become_loss_targets(setup):
    profile, tokenizer, release = setup
    records = copy.deepcopy(release["training_payload"]["records"])
    for record in records.values():
        current = record[0]
        current["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "FileSkill-read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ]
        current["messages"][1] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "read",
                    "type": "function",
                    "function": {
                        "name": "FileSkill-read_file",
                        "arguments": {"path": "missing.txt"},
                    },
                }
            ],
        }
        current["messages"][2] = {
            "role": "tool",
            "tool_call_id": "read",
            "name": "FileSkill-read_file",
            "content": "missing",
        }
    encoded = encode_release(build_release(records, profile), tokenizer, profile)
    record = encoded["records"]["train"][0]
    targets = [token for token in record["labels"] if token != -100]
    assert "missing" not in tokenizer.decode(targets)
    assert "verified correction" in tokenizer.decode(targets)


@pytest.mark.parametrize(
    "change,error",
    [
        (
            lambda release: release.update(release_sha256="0" * 64),
            "source_release_hash_mismatch",
        ),
        (
            lambda release: release["training_payload"].update(records_sha256="0" * 64),
            "source_release_hash_mismatch",
        ),
        (
            lambda release: release.update(schema_version=True),
            "source_release_hash_mismatch",
        ),
    ],
)
def test_modified_source_release_is_rejected(setup, change, error):
    profile, tokenizer, release = setup
    change(release)
    with pytest.raises(ValueError, match=error):
        encode_release(release, tokenizer, profile)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("is_fast", False, "fast_tokenizer_required"),
        ("chat_template", "changed", "template_mismatch"),
        (
            "backend_tokenizer",
            SimpleNamespace(to_str=lambda: "{}"),
            "active_tokenizer_mismatch",
        ),
        ("name_or_path", None, "materialized_tokenizer_required"),
    ],
)
def test_active_native_identity_is_required(setup, field, value, error):
    profile, tokenizer, release = setup
    setattr(tokenizer, field, value)
    with pytest.raises(ValueError, match=error):
        encode_release(release, tokenizer, profile)


def test_over_context_rejects_instead_of_truncating(setup):
    profile, tokenizer, release = setup
    smaller = replace(profile, context=8)
    release = build_release(release["training_payload"]["records"], smaller)
    with pytest.raises(ValueError, match="sequence_exceeds_context"):
        encode_release(release, tokenizer, smaller)


def test_nonexact_decode_is_rejected(setup):
    profile, tokenizer, release = setup
    tokenizer.decode = lambda *args, **kwargs: "different"
    with pytest.raises(ValueError, match="full_decode_mismatch"):
        encode_release(release, tokenizer, profile)


def test_future_dependent_native_serialization_is_rejected(setup):
    profile, tokenizer, release = setup
    original = tokenizer.apply_chat_template
    tokenizer.apply_chat_template = lambda messages, **kwargs: str(
        len(messages)
    ) + original(messages, **kwargs)
    with pytest.raises(ValueError, match="native_prefix_unstable"):
        encode_release(release, tokenizer, profile)


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda r: r["labels"].__setitem__(0, r["input_ids"][0]), "label_leakage"),
        (lambda r: r["input_ids"].__setitem__(0, True), "token_ids_invalid"),
        (lambda r: r["attention_mask"].__setitem__(0, True), "attention_invalid"),
        (
            lambda r: r.update(supervised_assistant_indices=[1, 3]),
            "span_supervision_mismatch",
        ),
        (lambda r: r["assistant_token_spans"][1].update(start=1), "span_overlap"),
        (
            lambda r: r["assistant_token_spans"][1].update(stop_token_id=299999),
            "span_stop_invalid",
        ),
        (lambda r: r.update(supervised_assistant_indices=[-1]), "targets_invalid"),
    ],
)
def test_resealed_bad_vectors_are_still_rejected(setup, mutation, error):
    profile, tokenizer, release = setup
    encoded = encode_release(release, tokenizer, profile)
    mutation(encoded["records"]["train"][0])
    rehash(encoded)
    with pytest.raises(ValueError, match=error):
        validate_encoded_release(encoded, profile)


def test_transport_hash_and_split_summaries_are_verified(setup):
    profile, tokenizer, release = setup
    encoded = encode_release(release, tokenizer, profile)
    encoded["records"]["train"][0]["input_ids"][0] += 1
    with pytest.raises(ValueError, match="encoded_release_hash_mismatch"):
        validate_encoded_release(encoded, profile)


def test_no_holdout_or_packing_can_be_inserted(setup):
    profile, tokenizer, release = setup
    encoded = encode_release(release, tokenizer, profile)
    encoded["records"]["holdout"] = []
    rehash(encoded)
    with pytest.raises(ValueError, match="encoded_splits_invalid"):
        validate_encoded_release(encoded, profile)


def test_group_leakage_is_rechecked_after_transport(setup):
    profile, tokenizer, release = setup
    encoded = encode_release(release, tokenizer, profile)
    encoded["records"]["validation"][0]["problem_group"] = encoded["records"]["train"][
        0
    ]["problem_group"]
    rehash(encoded)
    with pytest.raises(ValueError, match="group_leakage"):
        validate_encoded_release(encoded, profile)


def test_native_model_turn_continuation_has_no_invented_eos(setup):
    profile, tokenizer, release = setup
    records = release["training_payload"]["records"]
    for rows in records.values():
        rows[0]["messages"].append(
            {"role": "assistant", "content": "Final verified result"}
        )
        rows[0]["supervised_assistant_indices"] = [3, 4]
    encoded = encode_release(build_release(records, profile), tokenizer, profile)
    record = encoded["records"]["train"][0]
    plan, final = record["assistant_token_spans"][1:]
    assert plan["native_continuation"] is True
    assert plan["stop_token"] is None
    assert final["native_continuation"] is False
    assert final["stop_token_id"] in record["labels"]
    assert plan["end"] == final["start"]


def test_tokens_crossing_native_assistant_boundary_are_rejected(setup):
    profile, tokenizer, release = setup
    original = tokenizer.__class__.__call__

    def crossing(self, text, **kwargs):
        result = original(self, text, **kwargs)
        result["offset_mapping"][1] = (0, len(text))
        return result

    tokenizer.__class__.__call__ = crossing
    try:
        with pytest.raises(ValueError, match="token_crosses_turn_boundary"):
            encode_release(release, tokenizer, profile)
    finally:
        tokenizer.__class__.__call__ = original


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("packing", {"enabled": True}, "packing_invalid"),
        ("mask_policy", "all_tokens", "mask_policy_invalid"),
        ("schema_version", True, "schema_invalid"),
    ],
)
def test_encoded_contract_fields_are_not_merely_descriptive(setup, field, value, error):
    profile, tokenizer, release = setup
    encoded = encode_release(release, tokenizer, profile)
    encoded[field] = value
    rehash(encoded)
    with pytest.raises(ValueError, match=error):
        validate_encoded_release(encoded, profile)


def test_forged_split_summary_is_rejected_even_when_outer_hash_matches(setup):
    profile, tokenizer, release = setup
    encoded = encode_release(release, tokenizer, profile)
    encoded["split_summary"]["train"]["tokens"] += 1
    encoded["encoded_release_sha256"] = digest(
        {
            key: value
            for key, value in encoded.items()
            if key != "encoded_release_sha256"
        }
    )
    with pytest.raises(ValueError, match="split_hash_mismatch"):
        validate_encoded_release(encoded, profile)


def test_encoded_release_is_bound_to_actual_variant_not_only_tool_schema(setup):
    profile, tokenizer, release = setup
    encoded = encode_release(release, tokenizer, profile)
    other = replace(profile, model=E4B_MODEL, loader=E4B_LOADER)
    with pytest.raises(ValueError, match="profile_mismatch"):
        validate_encoded_release(encoded, other)


def test_crossed_variant_material_cannot_reuse_large_tokenizer(setup):
    profile, tokenizer, release = setup
    other = replace(profile, model=E4B_MODEL, loader=E4B_LOADER)
    small_release = build_release(release["training_payload"]["records"], other)
    with pytest.raises(ValueError, match="snapshot_loader_mismatch"):
        encode_release(small_release, tokenizer, other)
